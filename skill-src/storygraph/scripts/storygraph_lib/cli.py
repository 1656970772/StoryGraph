from pathlib import Path

from .config import load_config
from .validation import validate_skill_tree


def _default_config_path() -> Path:
    return Path(__file__).resolve().parents[2] / "config" / "storygraph.default.json"


def main(argv=None):
    import argparse

    parser = argparse.ArgumentParser(prog="storygraph")
    parser.add_argument("--version", action="store_true")
    sub = parser.add_subparsers(dest="command")
    validate = sub.add_parser("validate-skill")
    validate.add_argument("--skill-root", default=str(Path(__file__).resolve().parents[2]))
    config_check = sub.add_parser("config-check")
    config_check.add_argument("--local-override")
    args = parser.parse_args(argv)
    if args.version:
        print("storygraph 0.1.0")
        return 0
    if args.command == "validate-skill":
        result = validate_skill_tree(Path(args.skill_root))
        print({"ok": result.ok, "missing": result.missing})
        return 0 if result.ok else 2
    if args.command == "config-check":
        local = Path(args.local_override) if args.local_override else None
        config = load_config(_default_config_path(), local_override=local)
        print({"ok": True, "graph_dir_suffix": config["graph_dir_suffix"]})
        return 0
    parser.print_usage()
    return 2
