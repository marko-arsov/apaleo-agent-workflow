"""Workflow-local policy storage with exact previews, backups and crash recovery."""
from __future__ import annotations
from contextlib import contextmanager
from copy import deepcopy
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import tempfile
from .core import fingerprint, resolve_settings, validate_settings, validate_catalogue, evaluate

EMPTY = {"schema_version": 1}


def read(path, default=None):
    path = Path(path)
    if not path.exists():
        return deepcopy(default)
    if path.stat().st_size > 2_000_000:
        raise ValueError("Model configuration exceeds size limit")
    return json.loads(path.read_text())


def write(path, value):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix="." + path.name, dir=path.parent)
    try:
        with os.fdopen(fd, "w") as stream:
            json.dump(value, stream, indent=2, sort_keys=True); stream.write("\n")
            stream.flush(); os.fsync(stream.fileno())
        os.replace(name, path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


class Store:
    def __init__(self, data, project_file=None, providers=("codex", "claude", "cursor"), legacy=None, workflow="workflow", baseline=None):
        self.data = Path(data).resolve()
        self.project = Path(project_file).resolve() if project_file else None
        self.providers = list(providers)
        self.legacy = legacy or {}
        self.workflow = workflow
        self.baseline = baseline or EMPTY
        self.global_file = self.data / "settings.json"

    @contextmanager
    def lock(self):
        self.data.mkdir(parents=True, exist_ok=True)
        with (self.data / "write.lock").open("a") as stream:
            fcntl.flock(stream, fcntl.LOCK_EX)
            yield

    def layers(self):
        if (self.data / "pending.json").exists():
            raise ValueError("Interrupted model update: run models recover before another settings operation")
        return [read(self.global_file, EMPTY), read(self.project, EMPTY) if self.project else EMPTY]

    def effective(self, layers=None):
        return resolve_settings([self.baseline, *(layers if layers is not None else self.layers())], self.providers, self.legacy)

    def evaluate(self, facts, overrides=None):
        directory = Path(__file__).parent
        registry = read(directory / "registry.json")
        policy = read(directory / "policy.json")
        notice = None
        try:
            catalogue = read(self.data / "catalogue.json", {})
            if catalogue:
                validate_catalogue(catalogue)
            for row in catalogue.get("providers", {}).values():
                if not row.get("installed"):
                    continue
                observed = datetime.fromisoformat(row.get("observed_at", ""))
                if observed.tzinfo is None or (datetime.now(timezone.utc) - observed).days > policy["stale_days"] or row.get("refresh_failed"):
                    notice = "Model catalogue is stale or incomplete; run update-models when convenient."
            if not catalogue:
                notice = "No model catalogue; retaining configured routes. Run update-models when convenient."
        except (ValueError, TypeError, KeyError, OSError):
            catalogue = {}
            notice = "Model catalogue is missing or invalid; retaining configured routes."
        if notice:
            # Retain explicit/default routes, not unverified recommendations from stale data.
            catalogue = {"providers": {k: dict(v, models=[dict(m, status="unavailable" if m.get("status") == "unavailable" else "stale") for m in v.get("models", [])]) for k, v in catalogue.get("providers", {}).items()}}
        layers = self.layers()
        if overrides is not None:
            if not isinstance(overrides, dict) or set(overrides) - {"global", "project"}:
                raise ValueError("Preview settings use global and/or project objects")
            for idx, scope in enumerate(("global", "project")):
                if scope in overrides:
                    if scope == "project" and self.project is None:
                        raise ValueError("Project preview requires a resolved project")
                    layers[idx] = validate_settings(overrides[scope])
        result = evaluate(registry, policy, catalogue, self.effective(layers), facts)
        if notice:
            result["notice"] = notice
            result["snapshot_hash"] = fingerprint({k: v for k, v in result.items() if k != "snapshot_hash"})
        return result

    def propose(self, updates, scope):
        scopes = ["global", "project"] if scope == "both" else [scope]
        if scope not in {"global", "project", "both"} or set(updates) != set(scopes):
            raise ValueError("Input must contain exactly the selected global/project scope objects")
        old = self.layers(); new = deepcopy(old)
        changes = []
        for name in scopes:
            path = self.global_file if name == "global" else self.project
            if path is None:
                raise ValueError("Project scope requires a resolved workflow project")
            value = validate_settings(updates[name])
            idx = 0 if name == "global" else 1
            new[idx] = deepcopy(value)
            before = read(path)
            changes.append({"scope": name, "path": str(path), "before": fingerprint(before), "previous": before, "after": value})
        payload = {"schema_version": 1, "workflow": self.workflow, "scope": scope, "changes": changes, "effective": self.effective(new), "dependencies": {str(self.global_file): fingerprint(read(self.global_file))}}
        if self.project:
            payload["dependencies"][str(self.project)] = fingerprint(read(self.project))
        payload["approval"] = fingerprint(payload)
        return payload

    def _paths(self, proposal):
        allowed = {"global": self.global_file, "project": self.project}
        paths = []
        for change in proposal["changes"]:
            path = allowed.get(change["scope"])
            if path is None or str(path) != change["path"] or path in paths:
                raise ValueError("Proposal target differs from this workflow's resolved scope")
            validate_settings(change["after"])
            paths.append(path)
        return paths

    def apply(self, proposal, approval):
        if proposal.get("workflow") != self.workflow or approval != proposal.get("approval") or approval != fingerprint({k: v for k, v in proposal.items() if k != "approval"}):
            raise ValueError("Approval must match the exact workflow proposal")
        paths = self._paths(proposal)
        with self.lock():
            self.layers()
            for path, expected in proposal["dependencies"].items():
                if path not in {str(self.global_file), str(self.project)} or fingerprint(read(path)) != expected:
                    raise ValueError("Model settings changed since preview; regenerate the proposal")
            for path, change in zip(paths, proposal["changes"]):
                if fingerprint(read(path)) != change["before"]:
                    raise ValueError("Model settings changed since preview")
            layers = self.layers()
            for change in proposal["changes"]:
                layers[0 if change["scope"] == "global" else 1] = change["after"]
            if self.effective(layers) != proposal["effective"]:
                raise ValueError("Project provider restrictions or pins changed since preview")
            write(self.data / "backups" / (approval + ".json"), proposal)
            write(self.data / "pending.json", proposal)
            try:
                for path, change in zip(paths, proposal["changes"]):
                    write(path, change["after"])
                for path, change in zip(paths, proposal["changes"]):
                    if read(path) != change["after"]:
                        raise ValueError("Model settings read-back mismatch")
            except Exception:
                self._rollback(proposal)
                raise
            (self.data / "pending.json").unlink()
        return {"workflow": self.workflow, "changed": [str(p) for p in paths], "effective": self.effective()}

    def _rollback(self, proposal):
        paths = self._paths(proposal)
        for path, change in zip(paths, proposal["changes"]):
            current = read(path)
            if current != change["previous"] and current != change["after"]:
                raise ValueError("Recovery found concurrent edits; inspect pending.json and preserve them")
        for path, change in zip(paths, proposal["changes"]):
            if change["previous"] is None:
                path.unlink(missing_ok=True)
            else:
                write(path, change["previous"])
        (self.data / "pending.json").unlink()

    def recover(self):
        with self.lock():
            proposal = read(self.data / "pending.json")
            if proposal:
                self._rollback(proposal)
        return {"recovered": bool(proposal)}


def summary(result):
    rows = []
    for stage, routes in result["routes"].items():
        route = routes[0] if routes else {}
        rows.append({"stage": stage, "route": route, "fallbacks": routes[1:], "reason": result["reasons"][stage]})
    return {"stages": rows, "unresolved": result["unresolved"], "advisories": result["advisories"], **({"notice": result["notice"]} if result.get("notice") else {})}
