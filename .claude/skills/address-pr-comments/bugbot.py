#!/usr/bin/env python3
"""Cursor Bugbot helpers for /address-pr-comments --bugbot."""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "pipeline"))
from common import FEATURE_REPOS  # noqa: E402

BUGBOT_LOGIN = re.compile(
    r"^(cursor(\[bot\])?|cursor-bugbot|bugbot(\[bot\])?)$",
    re.I,
)
BUGBOT_NAME = re.compile(r"bugbot", re.I)
BLOCKED_AUTHOR = re.compile(r"coderabbit|claude\[bot\]", re.I)


def utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def run_gh(args: list[str], cwd: Path, timeout: int = 90) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["gh", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def gh_json(args: list[str], cwd: Path, timeout: int = 90) -> Any:
    r = run_gh(args, cwd, timeout=timeout)
    if r.returncode != 0:
        raise RuntimeError(r.stderr.strip() or r.stdout.strip() or f"gh {' '.join(args)} failed")
    raw = (r.stdout or "").strip()
    return json.loads(raw) if raw else None


def is_bugbot(login: str | None, name: str | None = None) -> bool:
    login = (login or "").strip()
    name = (name or "").strip()
    blob = f"{login} {name}"
    if BLOCKED_AUTHOR.search(blob):
        return False
    if BUGBOT_LOGIN.match(login):
        return True
    return bool(BUGBOT_NAME.search(login) or BUGBOT_NAME.search(name))


def repo_cwds(root: Path, branch: str) -> list[tuple[str, Path]]:
    out: list[tuple[str, Path]] = []
    for name in FEATURE_REPOS:
        wt = root / "worktrees" / branch / name
        main = root / name
        if wt.is_dir():
            out.append((name, wt))
        elif main.is_dir():
            out.append((name, main))
    return out


def list_prs(root: Path, branch: str) -> list[dict[str, Any]]:
    prs: list[dict[str, Any]] = []
    for name, cwd in repo_cwds(root, branch):
        r = run_gh(
            [
                "pr",
                "view",
                "--json",
                "number,url,isDraft,state,headRefName,title",
            ],
            cwd,
        )
        if r.returncode != 0:
            continue
        try:
            data = json.loads(r.stdout or "{}")
        except json.JSONDecodeError:
            continue
        if not data.get("number"):
            continue
        if (data.get("headRefName") or "") != branch:
            continue
        prs.append(
            {
                "repo": name,
                "path": str(cwd),
                "number": data["number"],
                "url": data.get("url"),
                "isDraft": bool(data.get("isDraft")),
                "state": data.get("state"),
                "branch": data.get("headRefName") or branch,
                "title": data.get("title"),
            }
        )
    return prs


def owner_repo(cwd: Path) -> str:
    data = gh_json(["repo", "view", "--json", "nameWithOwner"], cwd)
    if not isinstance(data, dict):
        raise RuntimeError(f"could not resolve nameWithOwner in {cwd}")
    nwo = data.get("nameWithOwner") or ""
    if "/" not in nwo:
        raise RuntimeError(f"could not resolve nameWithOwner in {cwd}")
    return nwo


def cmd_prs(args: argparse.Namespace) -> int:
    prs = list_prs(Path(args.root), args.branch)
    json.dump(prs, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0 if prs else 1


def cmd_ready(args: argparse.Namespace) -> int:
    root = Path(args.root)
    prs = list_prs(root, args.branch)
    if not prs:
        print("ERROR: no open PRs for this branch", file=sys.stderr)
        return 1
    state = {
        "ready_at": utc_now(),
        "branch": args.branch,
        "prs": [],
    }

    def persist() -> None:
        if not args.state_file:
            return
        path = Path(args.state_file)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(state, indent=2) + "\n", encoding="utf-8")

    persist()
    for pr in prs:
        cwd = Path(pr["path"])
        was_draft = bool(pr.get("isDraft"))
        row = {
            **pr,
            "was_draft": was_draft,
            "marked_ready": False,
        }
        state["prs"].append(row)
        # Persist intent before the external mutation. If interrupted while gh
        # is running, cleanup can safely attempt to restore this draft.
        persist()
        if was_draft:
            r = run_gh(["pr", "ready", str(pr["number"])], cwd)
            if r.returncode != 0:
                print(
                    f"ERROR: gh pr ready {pr['repo']}#{pr['number']}: {r.stderr.strip()}",
                    file=sys.stderr,
                )
                restore_from_state({"prs": state["prs"]}, quiet=True)
                return 1
            row["marked_ready"] = True
            persist()
        print(f"ready {pr['repo']}#{pr['number']} was_draft={was_draft} {pr.get('url')}", file=sys.stderr)
    json.dump(state, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


def restore_from_state(state: dict[str, Any], *, quiet: bool = False) -> int:
    rc = 0
    for pr in state.get("prs") or []:
        tracked_state = "was_draft" in pr or "marked_ready" in pr
        if tracked_state and not bool(pr.get("was_draft")):
            # It was already ready before this run; preserve that state.
            continue
        cwd = Path(pr["path"])
        num = str(pr["number"])
        r = run_gh(["pr", "ready", "--undo", num], cwd)
        if r.returncode != 0:
            # already draft is success
            err = (r.stderr or "") + (r.stdout or "")
            if "draft" in err.lower() and "already" in err.lower():
                if not quiet:
                    print(f"draft {pr.get('repo')}#{num} (already)", file=sys.stderr)
                continue
            # confirm current state
            try:
                view = gh_json(["pr", "view", num, "--json", "isDraft"], cwd)
                if isinstance(view, dict) and view.get("isDraft"):
                    if not quiet:
                        print(f"draft {pr.get('repo')}#{num} (confirmed)", file=sys.stderr)
                    continue
            except Exception:
                pass
            print(f"ERROR: gh pr ready --undo {pr.get('repo')}#{num}: {err.strip()}", file=sys.stderr)
            rc = 1
            continue
        if not quiet:
            print(f"draft {pr.get('repo')}#{num}", file=sys.stderr)
    return rc


def cmd_restore(args: argparse.Namespace) -> int:
    root = Path(args.root)
    if args.state_file and Path(args.state_file).is_file():
        state = json.loads(Path(args.state_file).read_text(encoding="utf-8"))
        return restore_from_state(state)
    prs = list_prs(root, args.branch)
    fake = {"prs": prs}
    return restore_from_state(fake)


def fetch_bugbot_items(pr: dict[str, Any]) -> dict[str, Any]:
    cwd = Path(pr["path"])
    num = pr["number"]
    nwo = owner_repo(cwd)
    reviews_raw = gh_json(["api", "--paginate", f"repos/{nwo}/pulls/{num}/reviews"], cwd) or []
    comments_raw = gh_json(["api", "--paginate", f"repos/{nwo}/pulls/{num}/comments"], cwd) or []
    if isinstance(reviews_raw, dict):
        reviews_raw = [reviews_raw]
    if isinstance(comments_raw, dict):
        comments_raw = [comments_raw]

    reviews = []
    for rev in reviews_raw:
        author = (rev.get("user") or {}).get("login") or ""
        if not is_bugbot(author, (rev.get("user") or {}).get("name")):
            continue
        reviews.append(
            {
                "id": rev.get("id"),
                "author": author,
                "state": rev.get("state"),
                "body": rev.get("body") or "",
                "submitted_at": rev.get("submitted_at"),
                "html_url": rev.get("html_url"),
            }
        )

    comments = []
    for c in comments_raw:
        user = c.get("user") or {}
        author = user.get("login") or ""
        if not is_bugbot(author, user.get("name")):
            continue
        comments.append(
            {
                "id": c.get("id"),
                "author": author,
                "path": c.get("path"),
                "line": c.get("line") or c.get("original_line"),
                "original_line": c.get("original_line"),
                "diff_hunk": c.get("diff_hunk") or "",
                "body": c.get("body") or "",
                "html_url": c.get("html_url"),
                "created_at": c.get("created_at"),
                "updated_at": c.get("updated_at"),
                "in_reply_to_id": c.get("in_reply_to_id"),
                "commit_id": c.get("commit_id"),
            }
        )

    threads = graphql_threads(cwd, nwo, num)
    return {"reviews": reviews, "comments": comments, "threads": threads}


def graphql_threads(cwd: Path, nwo: str, number: int) -> list[dict[str, Any]]:
    owner, name = nwo.split("/", 1)
    query = """
    query($owner: String!, $name: String!, $number: Int!) {
      repository(owner: $owner, name: $name) {
        pullRequest(number: $number) {
          reviewThreads(first: 100) {
            nodes {
              id
              isResolved
              isOutdated
              path
              line
              comments(first: 20) {
                nodes {
                  databaseId
                  body
                  createdAt
                  author { login }
                }
              }
            }
          }
        }
      }
    }
    """
    payload = {
        "query": query,
        "variables": {"owner": owner, "name": name, "number": int(number)},
    }
    r = subprocess.run(
        ["gh", "api", "graphql", "--input", "-"],
        cwd=str(cwd),
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        timeout=120,
    )
    if r.returncode != 0:
        return []
    try:
        data = json.loads(r.stdout or "{}")
    except json.JSONDecodeError:
        return []
    nodes = (
        (((data.get("data") or {}).get("repository") or {}).get("pullRequest") or {})
        .get("reviewThreads")
        or {}
    ).get("nodes") or []
    out = []
    for th in nodes:
        comments = []
        for c in ((th.get("comments") or {}).get("nodes") or []):
            login = ((c.get("author") or {}) or {}).get("login")
            if not is_bugbot(login):
                continue
            comments.append(
                {
                    "id": c.get("databaseId"),
                    "author": login,
                    "body": c.get("body") or "",
                    "created_at": c.get("createdAt"),
                }
            )
        if not comments:
            continue
        out.append(
            {
                "id": th.get("id"),
                "isResolved": bool(th.get("isResolved")),
                "isOutdated": bool(th.get("isOutdated")),
                "path": th.get("path"),
                "line": th.get("line"),
                "comments": comments,
            }
        )
    return out


def cmd_comments(args: argparse.Namespace) -> int:
    prs = list_prs(Path(args.root), args.branch)
    payload = {"prs": [], "bugbot_comment_count": 0, "bugbot_review_count": 0, "bugbot_thread_count": 0}
    for pr in prs:
        try:
            items = fetch_bugbot_items(pr)
        except Exception as exc:
            payload["prs"].append({**pr, "error": str(exc)})
            continue
        row = {**pr, **items}
        payload["prs"].append(row)
        payload["bugbot_comment_count"] += len(items["comments"])
        payload["bugbot_review_count"] += len(items["reviews"])
        payload["bugbot_thread_count"] += len(items["threads"])
    json.dump(payload, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


def has_bugbot_signal(payload: dict[str, Any]) -> bool:
    if payload.get("bugbot_comment_count") or payload.get("bugbot_review_count") or payload.get(
        "bugbot_thread_count"
    ):
        return True
    # A "no bugs found" review still counts as Bugbot having run.
    for pr in payload.get("prs") or []:
        if pr.get("reviews"):
            return True
    return False


def cmd_wait(args: argparse.Namespace) -> int:
    import time

    root = Path(args.root)
    initial = int(args.initial)
    poll = int(args.poll)
    poll_max = int(args.poll_max)
    print(
        f"bugbot wait: initial={initial}s poll={poll}s × {poll_max} branch={args.branch}",
        file=sys.stderr,
    )
    if initial > 0:
        time.sleep(initial)

    last: dict[str, Any] = {}
    for i in range(1, poll_max + 1):
        prs = list_prs(root, args.branch)
        payload: dict[str, Any] = {
            "status": "polling",
            "poll": i,
            "prs": [],
            "bugbot_comment_count": 0,
            "bugbot_review_count": 0,
            "bugbot_thread_count": 0,
        }
        if not prs:
            payload["status"] = "no_prs"
            last = payload
            print("bugbot wait: no PRs", file=sys.stderr)
            break
        for pr in prs:
            try:
                items = fetch_bugbot_items(pr)
            except Exception as exc:
                print(f"bugbot wait poll {i}: {pr['repo']} error: {exc}", file=sys.stderr)
                items = {"reviews": [], "comments": [], "threads": [], "error": str(exc)}
            payload["prs"].append({**pr, **items})
            payload["bugbot_comment_count"] += len(items.get("comments") or [])
            payload["bugbot_review_count"] += len(items.get("reviews") or [])
            payload["bugbot_thread_count"] += len(items.get("threads") or [])
        print(
            f"bugbot poll {i}/{poll_max}: comments={payload['bugbot_comment_count']} "
            f"reviews={payload['bugbot_review_count']} threads={payload['bugbot_thread_count']}",
            file=sys.stderr,
        )
        last = payload
        if has_bugbot_signal(payload):
            payload["status"] = "found"
            last = payload
            break
        if i < poll_max:
            time.sleep(poll)
    else:
        last["status"] = "timeout_none"

    if last.get("status") == "polling":
        last["status"] = "timeout_none"
    json.dump(last, sys.stdout, indent=2)
    sys.stdout.write("\n")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--root", required=True)
    p.add_argument("--branch", required=True)
    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("prs")
    ready = sub.add_parser("ready")
    ready.add_argument("--state-file", default="")
    restore = sub.add_parser("restore-draft")
    restore.add_argument("--state-file", default="")
    wait = sub.add_parser("wait")
    wait.add_argument("--initial", type=int, default=int(os.environ.get("PIPELINE_BUGBOT_WAIT_SEC", "90")))
    wait.add_argument("--poll", type=int, default=int(os.environ.get("PIPELINE_BUGBOT_POLL_SEC", "15")))
    wait.add_argument("--poll-max", type=int, default=int(os.environ.get("PIPELINE_BUGBOT_POLL_MAX", "8")))
    sub.add_parser("comments")
    return p


def main() -> int:
    args = build_parser().parse_args()
    if args.cmd == "prs":
        return cmd_prs(args)
    if args.cmd == "ready":
        return cmd_ready(args)
    if args.cmd == "restore-draft":
        return cmd_restore(args)
    if args.cmd == "wait":
        return cmd_wait(args)
    if args.cmd == "comments":
        return cmd_comments(args)
    return 64


if __name__ == "__main__":
    raise SystemExit(main())
