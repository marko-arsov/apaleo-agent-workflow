#!/usr/bin/env python3
"""Deterministic metadata, routing, violation, promotion, and pruning for rules."""

from __future__ import annotations

import argparse
import calendar
import json
import re
import sys
from datetime import date, datetime
from pathlib import Path

from common import find_root


REQUIRED = ("id", "tier", "added", "source", "statement", "violations", "last_violation")
SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


class RuleError(RuntimeError):
    pass


def _scalar(raw: str):
    value = raw.strip()
    if value == "null":
        return None
    if re.fullmatch(r"-?\d+", value):
        return int(value)
    if value.startswith('"'):
        try:
            return json.loads(value)
        except json.JSONDecodeError as exc:
            raise RuleError(f"invalid quoted YAML scalar: {value}") from exc
    return value


def read_metadata(path: Path) -> dict:
    values: dict = {}
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip() or line.lstrip().startswith("#"):
            continue
        match = re.fullmatch(r"([a-z_]+):\s*(.*)", line)
        if not match:
            raise RuleError(f"{path}:{number}: metadata must use one scalar key per line")
        values[match.group(1)] = _scalar(match.group(2))
    validate_metadata(values, path)
    return values


def validate_metadata(rule: dict, path: Path | None = None) -> None:
    label = str(path or rule.get("id") or "rule")
    missing = [key for key in REQUIRED if key not in rule]
    if missing:
        raise RuleError(f"{label}: missing metadata: {', '.join(missing)}")
    if not isinstance(rule["id"], str) or not SLUG.fullmatch(rule["id"]):
        raise RuleError(f"{label}: id must be a lowercase kebab-case slug")
    if rule["tier"] not in {1, 2, 3}:
        raise RuleError(f"{label}: tier must be 1, 2, or 3")
    if not isinstance(rule["violations"], int) or rule["violations"] < 0:
        raise RuleError(f"{label}: violations must be a non-negative integer")
    if not isinstance(rule["statement"], str) or not rule["statement"].strip():
        raise RuleError(f"{label}: statement is required")
    if not isinstance(rule["source"], str) or not rule["source"].strip():
        raise RuleError(f"{label}: source is required")
    for key in ("added", "last_violation"):
        value = rule[key]
        if value is None and key == "last_violation":
            continue
        try:
            date.fromisoformat(str(value))
        except ValueError as exc:
            raise RuleError(f"{label}: {key} must be YYYY-MM-DD or null") from exc
    if rule["violations"] == 0 and rule["last_violation"] is not None:
        raise RuleError(f"{label}: last_violation must be null when violations=0")
    if rule["violations"] > 0 and rule["last_violation"] is None:
        raise RuleError(f"{label}: last_violation is required when violations>0")


def _yaml_scalar(value) -> str:
    if value is None:
        return "null"
    if isinstance(value, int):
        return str(value)
    return json.dumps(str(value), ensure_ascii=False)


def write_metadata(path: Path, rule: dict) -> None:
    validate_metadata(rule, path)
    path.parent.mkdir(parents=True, exist_ok=True)
    ordered = [*REQUIRED, *sorted(key for key in rule if key not in REQUIRED)]
    path.write_text(
        "\n".join(f"{key}: {_yaml_scalar(rule[key])}" for key in ordered) + "\n",
        encoding="utf-8",
    )


def rules_dir(root: Path) -> Path:
    return root / ".claude" / "conventions" / "rules"


def load_rules(root: Path) -> dict[str, tuple[Path, dict]]:
    result: dict[str, tuple[Path, dict]] = {}
    for path in sorted(rules_dir(root).glob("*.yml")):
        rule = read_metadata(path)
        if rule["id"] in result:
            raise RuleError(f"duplicate rule metadata id: {rule['id']}")
        result[rule["id"]] = (path, rule)
    return result


def route_tier(*, checkable: bool, always_wrong: bool) -> int:
    if not checkable:
        return 3
    return 1 if always_wrong else 2


def register(
    root: Path,
    *,
    rule_id: str,
    statement: str,
    source: str,
    checkable: bool,
    always_wrong: bool,
    added: str,
) -> dict:
    rules = load_rules(root)
    if rule_id in rules:
        raise RuleError(f"rule already exists: {rule_id}; record a violation or promote it")
    tier = route_tier(checkable=checkable, always_wrong=always_wrong)
    rule = {
        "id": rule_id,
        "tier": tier,
        "added": added,
        "source": source,
        "statement": statement.strip(),
        "violations": 0,
        "last_violation": None,
    }
    path = rules_dir(root) / f"{rule_id}.yml"
    write_metadata(path, rule)
    return rule


def record_violation(root: Path, rule_id: str, source: str, when: str) -> dict:
    rules = load_rules(root)
    if rule_id not in rules:
        raise RuleError(f"unknown rule id: {rule_id}; use /add-rule to propose it")
    path, rule = rules[rule_id]
    log = root / ".claude" / "conventions" / "violations.jsonl"
    if log.is_file():
        for line in log.read_text(encoding="utf-8", errors="replace").splitlines():
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if event.get("rule") == rule_id and event.get("source") == source:
                rule["duplicate"] = True
                rule["escalation_required"] = rule["tier"] == 3 and rule["violations"] >= 2
                return rule
    rule["violations"] += 1
    rule["last_violation"] = when
    write_metadata(path, rule)
    with log.open("a", encoding="utf-8") as handle:
        handle.write(
            json.dumps({"rule": rule_id, "source": source, "date": when}, separators=(",", ":")) + "\n"
        )
    rule["escalation_required"] = rule["tier"] == 3 and rule["violations"] >= 2
    return rule


def promote(root: Path, rule_id: str, *, checkable: bool, always_wrong: bool) -> dict:
    rules = load_rules(root)
    if rule_id not in rules:
        raise RuleError(f"unknown rule id: {rule_id}")
    path, rule = rules[rule_id]
    target = route_tier(checkable=checkable, always_wrong=always_wrong)
    if target == 3:
        raise RuleError("promotion requires a mechanically checkable diff signal; Tier 3 cannot be forced")
    if target >= rule["tier"]:
        raise RuleError(f"promotion must strengthen the rule; current tier={rule['tier']}, derived tier={target}")
    rule["tier"] = target
    write_metadata(path, rule)
    return rule


def candidates(root: Path, *, as_of: str, months: int = 6) -> dict[str, list[dict]]:
    today = date.fromisoformat(as_of)
    if months < 1:
        raise RuleError("months must be at least 1")
    total_months = today.year * 12 + today.month - 1 - months
    cutoff_year, cutoff_month_index = divmod(total_months, 12)
    cutoff_month = cutoff_month_index + 1
    cutoff = date(
        cutoff_year,
        cutoff_month,
        min(today.day, calendar.monthrange(cutoff_year, cutoff_month)[1]),
    )
    deletion: list[dict] = []
    escalation: list[dict] = []
    for _path, rule in load_rules(root).values():
        if rule["violations"] == 0 and date.fromisoformat(rule["added"]) <= cutoff:
            deletion.append(rule)
        if rule["tier"] == 3 and rule["violations"] >= 2:
            escalation.append(rule)
    return {"deletion": deletion, "escalation": escalation}


def _yes_no(value: str) -> bool:
    normalized = value.strip().lower()
    if normalized in {"yes", "true", "1"}:
        return True
    if normalized in {"no", "false", "0"}:
        return False
    raise argparse.ArgumentTypeError("expected yes or no")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default="")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("validate")
    route = sub.add_parser("route")
    route.add_argument("--checkable", type=_yes_no, required=True)
    route.add_argument("--always-wrong", type=_yes_no, required=True)
    create = sub.add_parser("register")
    create.add_argument("--id", required=True)
    create.add_argument("--statement", required=True)
    create.add_argument("--source", default="manual")
    create.add_argument("--checkable", type=_yes_no, required=True)
    create.add_argument("--always-wrong", type=_yes_no, required=True)
    create.add_argument("--date", default=date.today().isoformat())
    violation = sub.add_parser("record-violation")
    violation.add_argument("--id", required=True)
    violation.add_argument("--source", required=True)
    violation.add_argument("--date", default=date.today().isoformat())
    promotion = sub.add_parser("promote")
    promotion.add_argument("--id", required=True)
    promotion.add_argument("--checkable", type=_yes_no, required=True)
    promotion.add_argument("--always-wrong", type=_yes_no, required=True)
    prune = sub.add_parser("candidates")
    prune.add_argument("--as-of", default=date.today().isoformat())
    prune.add_argument("--months", type=int, default=6)
    args = parser.parse_args()
    root = Path(args.root).resolve() if args.root else find_root()
    try:
        if args.command == "validate":
            values = load_rules(root)
            print(f"OK {len(values)} rule metadata file(s)")
            return 0
        if args.command == "route":
            print(route_tier(checkable=args.checkable, always_wrong=args.always_wrong))
            return 0
        if args.command == "register":
            value = register(
                root,
                rule_id=args.id,
                statement=args.statement,
                source=args.source,
                checkable=args.checkable,
                always_wrong=args.always_wrong,
                added=args.date,
            )
        elif args.command == "record-violation":
            value = record_violation(root, args.id, args.source, args.date)
        elif args.command == "promote":
            value = promote(
                root,
                args.id,
                checkable=args.checkable,
                always_wrong=args.always_wrong,
            )
        else:
            value = candidates(root, as_of=args.as_of, months=args.months)
        print(json.dumps(value, indent=2))
        return 3 if isinstance(value, dict) and value.get("escalation_required") else 0
    except (RuleError, OSError, ValueError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
