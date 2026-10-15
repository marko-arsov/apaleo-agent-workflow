"""CLI contract shared by independent workflow adapters."""
from pathlib import Path
from .core import PROVIDERS, route_key
from .storage import read, write, summary


def arguments(parser):
    parser.add_argument("action", choices=["inspect", "refresh", "evaluate", "propose", "apply", "recover"])
    parser.add_argument("--scope", choices=["global", "project", "both"])
    parser.add_argument("--providers", help="Confirmed provider set, comma-separated")
    parser.add_argument("--confirm-model", action="append", default=[], help="Explicitly confirmed provider:model access; refresh only")
    parser.add_argument("--input", type=Path, help="Task facts, scoped settings, or approved proposal JSON")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--settings", type=Path, help="Evaluate proposed scope settings without applying them")
    parser.add_argument("--approve")
    parser.add_argument("--verbose", action="store_true")


def execute(args, store, cwd):
    if args.action in {"propose", "apply"} and not args.input:
        raise ValueError("A reviewed --input file is required")
    if args.action == "inspect":
        return {"workflow": store.workflow, "global": str(store.global_file), "project": str(store.project) if store.project else None, "effective": store.effective(), "catalogue": read(store.data / "catalogue.json", {})}
    if args.action == "recover":
        return store.recover()
    if args.action == "refresh":
        from .discovery import discover
        if args.providers is None:
            raise ValueError("Confirm providers first and pass --providers")
        providers = args.providers.split(",") if args.providers else []
        if not providers or not set(providers) <= set(store.providers):
            raise ValueError("Choose a nonempty subset of the project's allowed providers")
        with store.lock():
            result = discover(providers, cwd, read(store.data / "catalogue.json", {}), args.confirm_model)
            write(store.data / "catalogue.json", result)
        registry = read(Path(__file__).parent / "registry.json") + store.effective().get("registry", [])
        known = {route_key(r) for r in registry}
        unknown = [p + ":" + m["model"] for p, row in result["providers"].items() for m in row["models"] if p + ":" + m["model"] not in known]
        return {"workflow": store.workflow, "providers": {p: {"installed": r["installed"], "models": len(r["models"]), "requires_confirmation": [m["model"] for m in r["models"] if m["status"] == "needs-confirmation"], "notice": r.get("notice")} for p, r in result["providers"].items()}, "unreviewed_models": unknown, "errors": result["errors"], "defaults_changed": False}
    if args.action == "evaluate":
        facts = read(args.input) if args.input else {"stages": ["specify", "implement-tests", "implement", "review"]}
        result = store.evaluate(facts, read(args.settings) if args.settings else None)
    elif args.action == "propose":
        if not args.scope:
            raise ValueError("Confirm the target scope and pass --scope")
        result = store.propose(read(args.input), args.scope)
    else:
        result = store.apply(read(args.input), args.approve)
    if args.output:
        write(args.output, result)
    if args.action == "evaluate" and not args.verbose:
        return summary(result) | ({"snapshot": str(args.output)} if args.output else {})
    return result
