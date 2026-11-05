"""Cited model evidence. Never selects a route and never stores an API key."""
from __future__ import annotations
from datetime import date, datetime, timedelta, timezone
import json
import os
from pathlib import Path
import urllib.error
import urllib.request
from .storage import read, write

SOURCE = "https://artificialanalysis.ai/api/v2/language/models/free"
ATTRIBUTION = "https://artificialanalysis.ai/"
CREATORS = {"Anthropic", "OpenAI", "SpaceXAI"}
ENV_FILE = Path.home() / ".config" / "apaleo-models.env"


def load_key():
    value = os.environ.get("AA_API_KEY", "").strip()
    if value:
        return value
    if not ENV_FILE.is_file():
        return ""
    for line in ENV_FILE.read_text().splitlines():
        line = line.strip()
        if line.startswith("export "):
            line = line[len("export "):].strip()
        if line.startswith("AA_API_KEY="):
            return line.split("=", 1)[1].strip().strip("'\"")
    return ""


def fetch_models(key):
    if not key:
        raise ValueError("Set AA_API_KEY in the environment or ~/.config/apaleo-models.env")
    rows, version, tier = [], None, None
    for page in range(1, 9):
        request = urllib.request.Request(
            f"{SOURCE}?page={page}",
            headers={"x-api-key": key, "Accept": "application/json", "User-Agent": "apaleo-model-watch"},
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                payload = json.loads(response.read().decode())
        except urllib.error.HTTPError as exc:
            detail = exc.read(400).decode("utf-8", "replace")
            raise ValueError(f"Artificial Analysis returned HTTP {exc.code}: {detail}") from None
        version = payload.get("intelligence_index_version", version)
        tier = payload.get("tier", tier)
        rows.extend(payload.get("data") or [])
        if not (payload.get("pagination") or {}).get("has_more"):
            return rows, version, tier
    raise ValueError("Artificial Analysis pagination exceeds limit")


def normalize(rows):
    models = []
    for item in rows:
        if not isinstance(item, dict) or not item.get("slug"):
            continue
        creator = item.get("model_creator") or {}
        index = (item.get("evaluations") or {}).get("artificial_analysis_intelligence_index")
        models.append({
            "id": item.get("id"),
            "slug": item["slug"],
            "name": item.get("name"),
            "release_date": item.get("release_date"),
            "creator": creator.get("name"),
            "creator_id": creator.get("id"),
            "intelligence_index": index,
        })
    models.sort(key=lambda row: row["slug"])
    return models


def _indexed(models):
    return {row["slug"]: row for row in models}


def summarize(previous, current, aliases, catalogue, defaults, today=None):
    """Diff a saved watch file. `today` is injectable so the recent window is testable."""
    today = today or datetime.now(timezone.utc).date()
    old, new = _indexed(previous.get("models") or []), _indexed(current.get("models") or [])
    baseline = not previous.get("models")

    def listed(slugs):
        return [new[slug] if slug in new else old[slug] for slug in sorted(slugs) if slug in new or slug in old]

    focused_new = {slug for slug in new.keys() - old.keys() if new[slug].get("creator") in CREATORS}
    focused_removed = {slug for slug in old.keys() - new.keys() if old[slug].get("creator") in CREATORS}
    cutoff = (today - timedelta(days=45)).isoformat()
    recent = [row for row in new.values() if row.get("creator") in CREATORS and (row.get("release_date") or "") >= cutoff]
    recent.sort(key=lambda row: row.get("release_date") or "", reverse=True)
    routes = []
    for alias in aliases.get("routes") or []:
        row = new.get(alias.get("slug"))
        provider = catalogue.get("providers", {}).get(alias["provider"], {})
        advertised = any(model.get("model") == alias["model"] and model.get("status") in {"advertised", "confirmed", "used"} for model in provider.get("models", []))
        routes.append({
            "provider": alias["provider"],
            "model": alias["model"],
            "slug": alias.get("slug"),
            "intelligence_index": None if row is None else row.get("intelligence_index"),
            "release_date": None if row is None else row.get("release_date"),
            "advertised": bool(provider) and advertised,
            "catalogue_checked": bool(provider),
        })
    missing = []
    for stage, chain in (defaults or {}).items():
        if not chain:
            continue
        route = chain[0]
        provider = catalogue.get("providers", {}).get(route["provider"], {})
        if not provider:
            continue
        present = any(model.get("model") == route["model"] and model.get("status") != "unavailable" for model in provider.get("models", []))
        if not present:
            missing.append({"stage": stage, "provider": route["provider"], "model": route["model"]})
    return {
        "attribution": ATTRIBUTION,
        "source": SOURCE,
        "baseline": baseline,
        "intelligence_index_version": current.get("intelligence_index_version"),
        "model_count": len(new),
        "new_slugs": [] if baseline else listed(focused_new),
        "removed_slugs": [] if baseline else listed(focused_removed),
        "recent": recent[:40],
        "routes": routes,
        "missing_defaults": missing,
    }


def refresh(data, aliases, catalogue, defaults):
    key = load_key()
    rows, version, tier = fetch_models(key)
    current = {
        "schema_version": 1,
        "source": SOURCE,
        "attribution": ATTRIBUTION,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "intelligence_index_version": version,
        "tier": tier,
        "models": normalize(rows),
    }
    path = Path(data) / "watch.json"
    previous = read(path, {})
    write(path, current)
    report = summarize(previous, current, aliases, catalogue, defaults, date.today())
    report["path"] = str(path)
    report["tier"] = tier
    return report
