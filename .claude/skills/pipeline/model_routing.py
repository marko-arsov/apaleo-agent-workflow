#!/usr/bin/env python3
"""Apaleo adapter; all model state belongs to this workflow, not Agent Flow."""
import argparse
import json
import os
from pathlib import Path
from common import find_root
from model_policy.commands import arguments, execute
from model_policy.storage import Store


def store(root):
    from pipeline_manifest import DEFAULT_ROUTES
    baseline = {"schema_version": 1, "defaults": {k: [v] for k, v in DEFAULT_ROUTES.items()}}
    return Store(Path(os.environ.get("XDG_DATA_HOME", str(Path.home() / ".local/share"))) / "apaleo-workflow/models",
                 Path(root) / ".claude/model-routing.json", workflow="apaleo-workflow", baseline=baseline)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path)
    arguments(parser)
    args = parser.parse_args()
    try:
        root = find_root(args.root or Path.cwd())
        result = execute(args, store(root), root)
        print(json.dumps(result, indent=2))
        return 0
    except (ValueError, OSError, KeyError) as exc:
        print("Error: " + str(exc))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
