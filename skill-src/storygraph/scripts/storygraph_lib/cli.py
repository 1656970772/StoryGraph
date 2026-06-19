from pathlib import Path

from .validation import validate_skill_tree


def main(argv=None):
    import argparse

    parser = argparse.ArgumentParser(prog="storygraph")
    sub = parser.add_subparsers(dest="command", required=True)
    validate = sub.add_parser("validate-skill")
    validate.add_argument("--skill-root", default=str(Path(__file__).resolve().parents[2]))
    args = parser.parse_args(argv)
    if args.command == "validate-skill":
        result = validate_skill_tree(Path(args.skill_root))
        if not result.ok:
            print({"ok": False, "missing": result.missing})
            return 2
        print({"ok": True, "missing": []})
        return 0
    return 2
