from pathlib import Path

from .config import ConfigLoadError, load_config
from .stage1 import build_stage1_graph, ingest_stage1, merge_stage1, prepare_stage1
from .templates import (
    TemplateDiscoveryError,
    discover_templates,
)
from .validation import validate_graph_dir, validate_skill_tree


class _CliArgumentError(Exception):
    def __init__(self, message: str):
        self.message = message
        super().__init__(message)


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


def _argument_error_payload(message: str) -> dict:
    return {
        "ok": False,
        "error": "cli_argument_error",
        "missing": _missing_arguments(message),
    }


def _missing_arguments(message: str) -> list[str]:
    marker = "the following arguments are required:"
    if marker not in message:
        return []
    raw = message.split(marker, 1)[1]
    return [item.strip() for item in raw.split(",") if item.strip()]


def _graph_dir_arg(args) -> Path | None:
    value = getattr(args, "graph_dir", None)
    return Path(value) if value else None


def _graph_dir_for_source(args, config: dict) -> Path:
    supplied = _graph_dir_arg(args)
    if supplied is not None:
        return supplied
    source = Path(args.source).expanduser().resolve(strict=False)
    suffix = config.get("graph_dir_suffix", ".storygraph")
    return source.parent / f"{source.stem}{suffix}"


def _stage1_cli_ok(status: str | None) -> bool:
    return status in {
        "success",
        "warning",
        "reused",
        "prepared",
        "pending_agent_outputs",
        "ingested",
    }


def main(argv=None):
    import argparse
    import json

    class JsonArgumentParser(argparse.ArgumentParser):
        def error(self, message):
            raise _CliArgumentError(message)

    parser = JsonArgumentParser(prog="storygraph")
    parser.add_argument("--version", action="store_true")
    sub = parser.add_subparsers(dest="command", parser_class=JsonArgumentParser)
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
    build.add_argument("--graph-dir")
    build.add_argument("--graphify-repo")
    prepare = sub.add_parser("prepare-stage1")
    prepare.add_argument("--config")
    prepare.add_argument("--local-override")
    prepare.add_argument("--source", required=True)
    prepare.add_argument("--template-dir", required=True)
    prepare.add_argument("--graph-dir")
    ingest = sub.add_parser("ingest-stage1")
    ingest.add_argument("--config")
    ingest.add_argument("--local-override")
    ingest.add_argument("--graph-dir", required=True)
    merge = sub.add_parser("merge-stage1")
    merge.add_argument("--config")
    merge.add_argument("--local-override")
    merge.add_argument("--graph-dir", required=True)
    validate_graph = sub.add_parser("validate-graph")
    validate_graph.add_argument("--graph-dir", required=True)
    try:
        args = parser.parse_args(argv)
    except _CliArgumentError as error:
        _print_json(_argument_error_payload(error.message))
        return 2
    if args.version:
        print("storygraph 0.1.0")
        return 0
    if args.command == "validate-skill":
        result = validate_skill_tree(Path(args.skill_root))
        payload = {"ok": result.ok, "missing": result.missing}
        if result.ok:
            print(payload)
        else:
            _print_json(payload)
        return 0 if result.ok else 2
    if args.command == "config-check":
        local = _local_override_arg(args)
        if local and not local.exists():
            _print_json(_missing_local_override_payload(local))
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
        count_policy = config.get("template_count_policy", {})
        expected_template_count = count_policy.get("expected_existing_templates")
        enforce_count = bool(count_policy.get("enforce_integration_count", False))
        template_count = len(discovery.templates)
        count_matches_expected = (
            None
            if expected_template_count is None
            else template_count == expected_template_count
        )
        payload = {
            "ok": True,
            "template_count": template_count,
            "expected_template_count": expected_template_count,
            "enforce_integration_count": enforce_count,
            "count_matches_expected": count_matches_expected,
            "warnings": discovery.warnings,
            "templates": [
                {
                    "name": template.name,
                    "file": template.path.name,
                }
                for template in discovery.templates
            ],
        }
        if enforce_count and count_matches_expected is False:
            payload["ok"] = False
            payload["error"] = "template_count_mismatch"
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        if enforce_count and expected_template_count is not None and not count_matches_expected:
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
        graph_dir = _graph_dir_arg(args)
        if graph_dir is not None:
            config["paths"]["graph_dir"] = str(graph_dir)
        if args.graphify_repo is not None:
            config["paths"]["graphify_repo"] = args.graphify_repo
        result = build_stage1_graph(Path(args.source), config)
        _print_json(result)
        return 0 if _stage1_cli_ok(result.get("status")) else 2
    if args.command == "prepare-stage1":
        local = _local_override_arg(args)
        if local and not local.exists():
            _print_json(_missing_local_override_payload(local))
            return 2
        config, error_code = _load_config_for_cli(args, local)
        if error_code is not None:
            return error_code
        config.setdefault("paths", {})
        config["paths"]["template_dir"] = args.template_dir
        graph_dir = _graph_dir_for_source(args, config)
        config["paths"]["graph_dir"] = str(graph_dir)
        result = prepare_stage1(
            source_path=Path(args.source),
            template_dir=Path(args.template_dir),
            graph_dir=graph_dir,
            config=config,
        )
        _print_json(result)
        return 0 if result.get("status") == "prepared" else 2
    if args.command == "ingest-stage1":
        local = _local_override_arg(args)
        if local and not local.exists():
            _print_json(_missing_local_override_payload(local))
            return 2
        config, error_code = _load_config_for_cli(args, local)
        if error_code is not None:
            return error_code
        result = ingest_stage1(graph_dir=Path(args.graph_dir), config=config)
        _print_json(result)
        return 0 if result.get("status") == "ingested" else 2
    if args.command == "merge-stage1":
        local = _local_override_arg(args)
        if local and not local.exists():
            _print_json(_missing_local_override_payload(local))
            return 2
        config, error_code = _load_config_for_cli(args, local)
        if error_code is not None:
            return error_code
        result = merge_stage1(graph_dir=Path(args.graph_dir), config=config)
        _print_json(result)
        return 0 if result.get("status") == "success" else 2
    if args.command == "validate-graph":
        result = validate_graph_dir(Path(args.graph_dir))
        _print_json({"ok": result.ok, "errors": result.errors})
        return 0 if result.ok else 2
    _print_json({"ok": False, "error": "cli_argument_error", "missing": ["command"]})
    return 2
