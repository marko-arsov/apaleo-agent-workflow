"""Pure, deterministic route selection; no IO, network or model calls."""
from __future__ import annotations
from copy import deepcopy
import hashlib
import json
import re
from . import VERSION

PROVIDERS = {"codex", "claude", "cursor"}
EFFORTS = {"none", "minimal", "low", "medium", "high", "xhigh", "max", "ultra"}
BANDS = {"fast": 0, "strong": 1, "deep": 2}
MECHANICAL = {"commit-and-push", "draft-pr", "commit", "push"}


def fingerprint(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def route_key(route):
    return route["provider"] + ":" + route["model"]


def validate_route(route):
    if not isinstance(route, dict) or set(route) - {"provider", "model", "reasoning"}:
        raise ValueError("Route fields are provider, model and optional reasoning")
    if route.get("provider") not in PROVIDERS or not isinstance(route.get("model"), str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/+-]{0,199}", route["model"]):
        raise ValueError("Route needs a supported provider and exact model ID or documented alias")
    if "reasoning" in route and (route["reasoning"] not in EFFORTS or route["provider"] == "cursor"):
        raise ValueError("Unsupported reasoning value; Cursor encodes effort in its exact model ID")


def validate_entry(entry):
    validate_route({k: entry[k] for k in ("provider", "model") if k in entry})
    if entry.get("band") not in BANDS or not isinstance(entry.get("family"), str) or not entry["family"]:
        raise ValueError("Registry entry requires band and model family")
    if not isinstance(entry.get("stages"), list) or not entry["stages"] or not all(isinstance(s, str) for s in entry["stages"]):
        raise ValueError("Registry entry requires suitable stages")
    if not isinstance(entry.get("rank"), int) or entry["rank"] < 0:
        raise ValueError("Registry entry requires a nonnegative reviewed preference rank")
    if not entry.get("sources") or not all(isinstance(s, str) and s.startswith("https://") for s in entry["sources"]):
        raise ValueError("Registry assessments require source URLs")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", entry.get("reviewed_at", "")):
        raise ValueError("Registry assessments require reviewed_at (YYYY-MM-DD)")
    if entry.get("confidence") not in {"reviewed", "provisional"}:
        raise ValueError("Registry confidence must be reviewed or provisional")
    if not isinstance(entry.get("efforts", {}), dict) or set(entry.get("efforts", {})) - {"simple", "balanced", "demanding"}:
        raise ValueError("Effort mappings use simple, balanced, demanding")
    if any(e not in EFFORTS for e in entry.get("efforts", {}).values()):
        raise ValueError("Unknown registry effort")
    if entry["provider"] == "cursor" and entry.get("efforts"):
        raise ValueError("Cursor registry entries use exact IDs, not effort arguments")
    if entry.get("encoded_effort") is not None and entry["encoded_effort"] not in EFFORTS:
        raise ValueError("Unknown encoded effort")
    for field in ("modes", "capabilities"):
        if field in entry and (not isinstance(entry[field], list) or not all(isinstance(x, str) for x in entry[field])):
            raise ValueError(field + " must be a string array")
    if set(entry.get("modes", [])) - {"simple", "balanced", "demanding"}:
        raise ValueError("Unknown effort mode")


def validate_settings(value):
    keys = {"schema_version", "providers", "defaults", "pins", "blocked", "registry", "adaptive_stages"}
    if not isinstance(value, dict) or value.get("schema_version") != 1 or set(value) - keys:
        raise ValueError("Expected model settings schema_version 1 and supported fields")
    if "providers" in value and (not isinstance(value["providers"], list) or set(value["providers"]) - PROVIDERS):
        raise ValueError("Invalid provider set")
    for kind in ("defaults", "pins"):
        if not isinstance(value.get(kind, {}), dict):
            raise ValueError(kind + " must be an object")
        for stage, routes in value.get(kind, {}).items():
            if not isinstance(stage, str) or not isinstance(routes, list):
                raise ValueError("Stage routes must be arrays (empty explicitly disables a route)")
            for route in routes:
                validate_route(route)
    for field in ("blocked", "adaptive_stages"):
        if not isinstance(value.get(field, []), list) or not all(isinstance(x, str) for x in value.get(field, [])):
            raise ValueError(field + " must be a string array")
    if not isinstance(value.get("registry", []), list):
        raise ValueError("registry must be an array")
    for entry in value.get("registry", []):
        validate_entry(entry)
    return value


def resolve_settings(layers, providers, legacy=None):
    """Per-stage atomic routes; restrictions intersect; explicit legacy routes are pins."""
    result = {"schema_version": 1, "providers": sorted(set(providers)), "defaults": {}, "pins": {}, "blocked": [], "registry": []}
    registry = {}
    for index, layer in enumerate(layers):
        validate_settings(layer)
        if index == len(layers) - 1:
            # Existing project routes outrank machine pins; only project policy can release them.
            result["pins"].update(deepcopy(legacy or {}))
        if "providers" in layer:
            result["providers"] = sorted(set(result["providers"]) & set(layer["providers"]))
        result["defaults"].update(deepcopy(layer.get("defaults", {})))
        if index == len(layers) - 1:
            for stage in layer.get("adaptive_stages", []):
                result["pins"].pop(stage, None)
        result["pins"].update(deepcopy(layer.get("pins", {})))
        result["blocked"] = sorted(set(result["blocked"]) | set(layer.get("blocked", [])))
        for entry in layer.get("registry", []):
            registry[route_key(entry)] = deepcopy(entry)
    result["registry"] = list(registry.values())
    if not layers:
        result["pins"].update(deepcopy(legacy or {}))
    return result


def validate_facts(facts):
    if not isinstance(facts, dict) or not isinstance(facts.get("stages"), list) or not all(isinstance(s, str) for s in facts["stages"]):
        raise ValueError("Task facts require stages")
    if len(facts["stages"]) != len(set(facts["stages"])):
        raise ValueError("Task stages must be unique")
    if facts.get("size", "medium") not in {"small", "medium", "large"} or facts.get("risk", "standard") not in {"low", "standard", "high"}:
        raise ValueError("Invalid task size or risk")
    for field in ("repository_count", "test_files", "test_lines"):
        if field in facts and (type(facts[field]) is not int or facts[field] < 0):
            raise ValueError(field + " must be a nonnegative integer")
    if "uncertain" in facts and type(facts["uncertain"]) is not bool:
        raise ValueError("uncertain must be boolean")
    for field in ("required_capabilities", "demanding_stages"):
        if field in facts and (not isinstance(facts[field], list) or not all(isinstance(x, str) for x in facts[field])):
            raise ValueError(field + " must be a string array")
    if not isinstance(facts.get("routes", {}), dict):
        raise ValueError("Explicit task routes must be an object")
    for routes in facts.get("routes", {}).values():
        if not isinstance(routes, list):
            raise ValueError("Explicit task routes must be arrays")
        for route in routes:
            validate_route(route)


def validate_catalogue(value):
    if not isinstance(value, dict) or value.get("schema_version") != 1 or not isinstance(value.get("providers"), dict):
        raise ValueError("Expected catalogue schema_version 1")
    for provider, host in value["providers"].items():
        if provider not in PROVIDERS or not isinstance(host, dict) or type(host.get("installed")) is not bool or not isinstance(host.get("models"), list):
            raise ValueError("Invalid catalogue provider")
        for model in host["models"]:
            if not isinstance(model, dict) or model.get("status") not in {"advertised", "confirmed", "used", "needs-confirmation", "unavailable"}:
                raise ValueError("Invalid catalogue observation")
            validate_route({"provider": provider, "model": model.get("model")})
            if "efforts" in model and (not isinstance(model["efforts"], list) or set(model["efforts"]) - EFFORTS):
                raise ValueError("Invalid advertised efforts")


def requirement(facts, stage, policy):
    risk = facts.get("risk", "standard")
    affected = facts.get("demanding_stages", ["specify", "implement", "review"])
    demanding = stage in affected and (risk == "high" or facts.get("uncertain", False) or (facts.get("size") == "large" and facts.get("repository_count", 1) > 1))
    test_scope = stage == "implement-tests" and (facts.get("test_files", 0) >= policy["test_file_threshold"] or facts.get("test_lines", 0) >= policy["test_line_threshold"])
    if demanding or test_scope:
        return "deep", "demanding", "consequential-or-complex" if demanding else "large-test-scope"
    if facts.get("size") == "small" and risk == "low" and facts.get("kind") in {"docs", "config"}:
        return "fast", "simple", "small-bounded-change"
    return "strong", "balanced", "routine-scoped-work"


def evaluate(registry, policy, catalogue, settings, facts):
    validate_facts(facts)
    entries = {route_key(e): deepcopy(e) for e in registry}
    entries.update({route_key(e): deepcopy(e) for e in settings.get("registry", [])})
    for entry in entries.values():
        validate_entry(entry)
    catalogue = catalogue or {"providers": {}}
    allowed = set(settings["providers"])
    blocked = set(settings.get("blocked", []))
    output = {"schema_version": 1, "evaluator_version": VERSION, "routes": {}, "reasons": {}, "unresolved": [], "advisories": []}
    family = None

    def observation(route):
        host = catalogue.get("providers", {}).get(route["provider"], {})
        return host, next((m for m in host.get("models", []) if m["model"] == route["model"]), {})

    def invalid(route):
        if route["provider"] not in allowed or route_key(route) in blocked:
            return "provider-or-model-restricted"
        host, model = observation(route)
        if host.get("installed") is False or model.get("status") == "unavailable":
            return "known-unavailable"
        if route.get("reasoning") and "efforts" in model and route["reasoning"] not in model["efforts"]:
            return "unsupported-effort"
        entry = entries.get(route_key(route), {})
        if not set(facts.get("required_capabilities", [])) <= set(entry.get("capabilities", [])):
            return "required-capability-not-established"
        return None

    # Always evaluate implement before review, regardless of input display order.
    stages = sorted((s for s in facts["stages"] if s not in MECHANICAL), key=lambda s: (s == "review", facts["stages"].index(s)))
    for stage in stages:
        band, effort_mode, reason = requirement(facts, stage, policy)
        defaults = settings.get("defaults", {})
        current = defaults.get(stage, defaults.get("default", []))
        pins = settings.get("pins", {})
        explicit = facts.get("routes", {})
        pinned = explicit.get(stage, explicit.get("default", pins.get(stage, pins.get("default"))))
        selected = None
        if pinned is not None:
            selected = deepcopy(pinned)
            reason = "explicit-route"
        elif stage in defaults and not current:
            selected, reason = [], "explicitly-disabled"
        else:
            candidates = []
            for key, entry in entries.items():
                host, model = observation(entry)
                if entry.get("confidence") != "reviewed" or (stage not in entry["stages"] and "*" not in entry["stages"]) or BANDS[entry["band"]] < BANDS[band]:
                    continue
                if not host.get("installed") or model.get("status") not in {"advertised", "confirmed", "used"}:
                    continue
                if entry.get("encoded_effort") in {"xhigh", "max", "ultra"}:
                    continue
                if entry.get("modes") and effort_mode not in entry["modes"]:
                    continue
                route = {"provider": entry["provider"], "model": entry["model"]}
                effort = entry.get("efforts", {}).get(effort_mode, entry.get("efforts", {}).get("balanced"))
                if effort and effort not in {"xhigh", "max", "ultra"} and effort in model.get("efforts", []):
                    route["reasoning"] = effort
                if invalid(route):
                    continue
                same_family = int(stage == "review" and family is not None and entry["family"] == family)
                keep = int(not current or route != current[0])
                candidates.append(((BANDS[entry["band"]], entry["rank"], same_family, keep, key), route))
            candidates.sort(key=lambda x: x[0])
            if candidates:
                selected, seen = [], set()
                for _, route in candidates:
                    identity = (route["provider"], entries[route_key(route)]["family"])
                    if identity not in seen:
                        selected.append(route); seen.add(identity)
                    if len(selected) >= policy["max_fallbacks"] + 1:
                        break
            elif current:
                selected, reason = deepcopy(current), "retained-configured-default"
                entry = entries.get(route_key(current[0]))
                if entry and BANDS[entry["band"]] < BANDS[band]:
                    output["unresolved"].append({"stage": stage, "reason": "configured-default-below-required-band"})
            else:
                selected, reason = [], "no-reviewed-available-route"
        problems = [invalid(r) for r in selected if invalid(r)]
        if problems or not selected:
            output["unresolved"].append({"stage": stage, "reason": problems[0] if problems else reason})
        if pinned and selected:
            entry = entries.get(route_key(selected[0]))
            if entry and BANDS[entry["band"]] < BANDS[band]:
                output["advisories"].append({"stage": stage, "reason": "explicit-route-below-recommended-band"})
        output["routes"][stage] = selected
        output["reasons"][stage] = reason
        if stage == "implement" and selected:
            family = entries.get(route_key(selected[0]), {}).get("family")
    output["provenance"] = {"registry": fingerprint(list(entries.values())), "policy": fingerprint(policy), "catalogue": fingerprint(catalogue), "settings": fingerprint(settings), "facts": deepcopy(facts)}
    output["snapshot_hash"] = fingerprint(output)
    return output


def validate_snapshot(snapshot, routes=None):
    if snapshot.get("schema_version") != 1 or snapshot.get("snapshot_hash") != fingerprint({k: v for k, v in snapshot.items() if k != "snapshot_hash"}):
        raise ValueError("Model selection snapshot is invalid or changed; evaluate the revised plan")
    for rows in snapshot["routes"].values():
        for route in rows:
            validate_route(route)
    if routes is not None and routes != snapshot["routes"]:
        raise ValueError("Plan routes differ from the saved model selection")
