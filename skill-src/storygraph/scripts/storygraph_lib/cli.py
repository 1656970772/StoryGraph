from pathlib import Path

from .config import ConfigLoadError, load_config
from .stage1 import build_stage1_graph
from .templates import TemplateDiscoveryError, build_requirement_matrix, discover_templates
from .validation import validate_graph_dir, validate_skill_tree


def _default_config_path() -> Path:
    return Path(__file__).resolve().parents[2] / "config" / "storygraph.default.json"


def _print_json(data: dict) -> None:
    import json

    print(json.dumps(data, ensure_ascii=False, indent=2))


def _local_override_arg(args):
    value = getattr(args, "local_override", None)
    return Path(value) if value else None


def _config_arg(args) -> Path:
    value = getattr(args, "config", None)
    return Path(value) if value else _default_config_path()


def _missing_local_override_payload(local: Path) -> dict:
    return {"ok": False, "error": "local_override_missing", "path": str(local)}


def _load_config_for_cli(args, local: Path | None) -> tuple[dict | None, int | None]:
    try:
        return load_config(_config_arg(args), local_override=local), None
    except ConfigLoadError as error:
        _print_json(error.to_dict())
        return None, 2


def main(argv=None):
    import argparse
    import json

    parser = argparse.ArgumentParser(prog="storygraph")
    parser.add_argument("--version", action="store_true")
    sub = parser.add_subparsers(dest="command")
    validate = sub.add_parser("validate-skill")
    validate.add_argument("--skill-root", default=str(Path(__file__).resolve().parents[2]))
    config_check = sub.add_parser("config-check")
    config_check.add_argument("--config")
    config_check.add_argument("--local-override")
    inspect_templates = sub.add_parser("inspect-templates")
    inspect_templates.add_argument("--config")
    inspect_templates.add_argument("--template-dir", required=True)
    inspect_templates.add_argument("--local-override")
    build = sub.add_parser("build-stage1")
    build.add_argument("--config")
    build.add_argument("--local-override")
    build.add_argument("--source", required=True)
    build.add_argument("--template-dir", required=True)
    build.add_argument("--graphify-repo")
    validate_graph = sub.add_parser("validate-graph")
    validate_graph.add_argument("--graph-dir", required=True)
    args = parser.parse_args(argv)
    if args.version:
        print("storygraph 0.1.0")
        return 0
    if args.command == "validate-skill":
        result = validate_skill_tree(Path(args.skill_root))
        print({"ok": result.ok, "missing": result.missing})
        return 0 if result.ok else 2
    if args.command == "config-check":
        local = _local_override_arg(args)
        if local and not local.exists():
            print(_missing_local_override_payload(local))
            return 2
        config, error_code = _load_config_for_cli(args, local)
        if error_code is not None:
            return error_code
        print({"ok": True, "graph_dir_suffix": config["graph_dir_suffix"]})
        return 0
    if args.command == "inspect-templates":
        local = _local_override_arg(args)
        if local and not local.exists():
            print(
                json.dumps(
                    _missing_local_override_payload(local),
                    ensure_ascii=False,
                )
            )
            return 2
        template_dir = Path(args.template_dir)
        if not template_dir.is_dir():
            print(
                json.dumps(
                    {"ok": False, "error": "template_dir_missing", "path": str(template_dir)},
                    ensure_ascii=False,
                )
            )
            return 2
        config, error_code = _load_config_for_cli(args, local)
        if error_code is not None:
            return error_code
        discovery_config = config.get("template_discovery", {})
        try:
            discovery = discover_templates(
                template_dir,
                glob=discovery_config.get("glob", "*模板.md"),
                readme_index_file=discovery_config.get("readme_index_file", "README.md"),
                exclude_files=discovery_config.get("exclude_files", []),
                readme_missing_policy=discovery_config.get("readme_missing_policy", "warn"),
            )
        except TemplateDiscoveryError as error:
            print(json.dumps(error.to_dict(), ensure_ascii=False))
            return 2
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
        count_policy = config.get("template_count_policy", {})
        expected_template_count = count_policy.get("expected_existing_templates")
        enforce_count = bool(count_policy.get("enforce_integration_count", False))
        count_matches_expected = (
            None
            if expected_template_count is None
            else matrix["template_count"] == expected_template_count
        )
        payload = {
            "template_count": matrix["template_count"],
            "expected_template_count": expected_template_count,
            "enforce_integration_count": enforce_count,
            "count_matches_expected": count_matches_expected,
            "warnings": discovery.warnings,
            "has_default_mapping": has_default_mapping,
            "templates": matrix["templates"],
        }
        if enforce_count and count_matches_expected is False:
            payload["error"] = "template_count_mismatch"
        elif enforce_count and count_matches_expected and has_default_mapping:
            payload["error"] = "default_mapping_used"
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        if enforce_count and expected_template_count is not None and (
            not count_matches_expected or has_default_mapping
        ):
            return 2
        return 0
    if args.command == "build-stage1":
        local = _local_override_arg(args)
        if local and not local.exists():
            _print_json(_missing_local_override_payload(local))
            return 2
        config, error_code = _load_config_for_cli(args, local)
        if error_code is not None:
            return error_code
        config.setdefault("paths", {})
        config["paths"]["template_dir"] = args.template_dir
        if args.graphify_repo is not None:
            config["paths"]["graphify_repo"] = args.graphify_repo
        result = build_stage1_graph(Path(args.source), config)
        _print_json(result)
        return 0 if result.get("status") in {"success", "warning", "reused"} else 2
    if args.command == "validate-graph":
        result = validate_graph_dir(Path(args.graph_dir))
        _print_json({"ok": result.ok, "errors": result.errors})
        return 0 if result.ok else 2
    parser.print_usage()
    return 2
