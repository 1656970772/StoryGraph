from pathlib import Path

from .config import load_config
from .templates import build_requirement_matrix, discover_templates
from .validation import validate_skill_tree


def _default_config_path() -> Path:
    return Path(__file__).resolve().parents[2] / "config" / "storygraph.default.json"


def main(argv=None):
    import argparse
    import json

    parser = argparse.ArgumentParser(prog="storygraph")
    parser.add_argument("--version", action="store_true")
    sub = parser.add_subparsers(dest="command")
    validate = sub.add_parser("validate-skill")
    validate.add_argument("--skill-root", default=str(Path(__file__).resolve().parents[2]))
    config_check = sub.add_parser("config-check")
    config_check.add_argument("--local-override")
    inspect_templates = sub.add_parser("inspect-templates")
    inspect_templates.add_argument("--template-dir", required=True)
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
        if local and not local.exists():
            print({"ok": False, "error": "local_override_missing", "path": str(local)})
            return 2
        config = load_config(_default_config_path(), local_override=local)
        print({"ok": True, "graph_dir_suffix": config["graph_dir_suffix"]})
        return 0
    if args.command == "inspect-templates":
        config = load_config(_default_config_path())
        discovery_config = config.get("template_discovery", {})
        discovery = discover_templates(
            Path(args.template_dir),
            glob=discovery_config.get("glob", "*模板.md"),
            readme_index_file=discovery_config.get("readme_index_file", "README.md"),
        )
        matrix = build_requirement_matrix(
            discovery.templates,
            rules=config.get("template_parser_rules"),
            mappings=config.get("template_graph_mappings", {}),
            status_enums=config.get("status_enums"),
            output_language=config.get("output_language", "zh-CN"),
        )
        has_default_mapping = any(
            record["mapping_source"] == "default_mapping" for record in matrix["templates"]
        )
        payload = {
            "template_count": matrix["template_count"],
            "warnings": discovery.warnings,
            "has_default_mapping": has_default_mapping,
            "templates": matrix["templates"],
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        if matrix["template_count"] == 37 and has_default_mapping:
            return 2
        return 0
    parser.print_usage()
    return 2
