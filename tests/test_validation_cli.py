import ast
import json
import os
import subprocess
from pathlib import Path

import pytest

from storygraph_lib.validation import validate_skill_tree


def test_validate_skill_tree_requires_core_directories(tmp_path):
    root = tmp_path / "storygraph"
    (root / "references").mkdir(parents=True)
    (root / "scripts").mkdir()
    (root / "config").mkdir()
    (root / "agents").mkdir()
    (root / "SKILL.md").write_text("# StoryGraph\n", encoding="utf-8")
    (root / "agents" / "openai.yaml").write_text("name: storygraph\n", encoding="utf-8")
    (root / "config" / "storygraph.default.json").write_text("{}", encoding="utf-8")
    (root / "references" / "workflow.md").write_text("# Workflow\n", encoding="utf-8")
    (root / "references" / "graph-schema.md").write_text("# Graph Schema\n", encoding="utf-8")
    (root / "references" / "extraction-workflow.md").write_text("# Extraction Workflow\n", encoding="utf-8")
    (root / "scripts" / "storygraph.py").write_text("print('ok')\n", encoding="utf-8")
    (root / "scripts" / "sync-skill.ps1").write_text("Write-Output 'ok'\n", encoding="utf-8")
    result = validate_skill_tree(root)
    assert result.ok is True
    assert result.missing == []


def test_storygraph_script_validate_skill_success(tmp_path):
    root = tmp_path / "storygraph"
    (root / "references").mkdir(parents=True)
    (root / "scripts").mkdir()
    (root / "config").mkdir()
    (root / "agents").mkdir()
    (root / "SKILL.md").write_text("# StoryGraph\n", encoding="utf-8")
    (root / "agents" / "openai.yaml").write_text("name: storygraph\n", encoding="utf-8")
    (root / "config" / "storygraph.default.json").write_text("{}", encoding="utf-8")
    (root / "references" / "workflow.md").write_text("# Workflow\n", encoding="utf-8")
    (root / "references" / "graph-schema.md").write_text("# Graph Schema\n", encoding="utf-8")
    (root / "references" / "extraction-workflow.md").write_text("# Extraction Workflow\n", encoding="utf-8")
    (root / "scripts" / "storygraph.py").write_text("print('ok')\n", encoding="utf-8")
    (root / "scripts" / "sync-skill.ps1").write_text("Write-Output 'ok'\n", encoding="utf-8")
    result = subprocess.run(
        [
            "python",
            "skill-src/storygraph/scripts/storygraph.py",
            "validate-skill",
            "--skill-root",
            str(root),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert result.stdout.strip() == "{'ok': True, 'missing': []}"


def test_storygraph_script_validate_skill_missing_file_returns_nonzero(tmp_path):
    root = tmp_path / "storygraph"
    root.mkdir()
    result = subprocess.run(
        [
            "python",
            "skill-src/storygraph/scripts/storygraph.py",
            "validate-skill",
            "--skill-root",
            str(root),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 2
    payload = json.loads(result.stdout)
    assert payload["ok"] is False
    assert "SKILL.md" in payload["missing"]


def test_sync_clean_script_contains_destination_boundary_guard():
    script = Path("skill-src/storygraph/scripts/sync-skill.ps1").read_text(encoding="utf-8")
    assert "[IO.Path]::GetFullPath($Destination).TrimEnd('\\')" in script
    assert ".codex\\skills\\storygraph" in script
    assert "if ($Clean -and $destinationRoot -ne $expectedResolved)" in script
    assert "Remove-Item -LiteralPath $target -Recurse -Force" in script


def test_sync_clean_refuses_unexpected_destination(tmp_path):
    source = tmp_path / "source"
    destination = tmp_path / "not-storygraph"
    source.mkdir()
    destination.mkdir()
    script = Path("skill-src/storygraph/scripts/sync-skill.ps1")
    result = __import__("subprocess").run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
            "-Source",
            str(source),
            "-Destination",
            str(destination),
            "-Clean",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "Refusing to clean unexpected destination" in (result.stderr + result.stdout)


def test_sync_clean_refuses_unexpected_destination_without_creating_it(tmp_path):
    source = tmp_path / "source"
    destination = tmp_path / "not-created"
    source.mkdir()
    script = Path("skill-src/storygraph/scripts/sync-skill.ps1")
    result = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
            "-Source",
            str(source),
            "-Destination",
            str(destination),
            "-Clean",
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode != 0
    assert "Refusing to clean unexpected destination" in (result.stderr + result.stdout)
    assert not destination.exists()


def test_sync_without_clean_allows_custom_destination(tmp_path):
    source = tmp_path / "source"
    destination = tmp_path / "custom-storygraph"
    (source / "scripts").mkdir(parents=True)
    (source / "SKILL.md").write_text("# StoryGraph\n", encoding="utf-8")
    script = Path("skill-src/storygraph/scripts/sync-skill.ps1")
    result = __import__("subprocess").run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
            "-Source",
            str(source),
            "-Destination",
            str(destination),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert (destination / "SKILL.md").exists()


def test_sync_without_clean_preserves_extra_destination_files(tmp_path):
    source = tmp_path / "source"
    destination = tmp_path / "custom-storygraph"
    (source / "scripts").mkdir(parents=True)
    (source / "SKILL.md").write_text("# StoryGraph\n", encoding="utf-8")
    destination.mkdir()
    extra = destination / "README.local.md"
    extra.write_text("keep me\n", encoding="utf-8")
    script = Path("skill-src/storygraph/scripts/sync-skill.ps1")
    result = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
            "-Source",
            str(source),
            "-Destination",
            str(destination),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert (destination / "SKILL.md").exists()
    assert extra.read_text(encoding="utf-8") == "keep me\n"


def test_sync_clean_preserves_local_config_in_default_install(tmp_path):
    source = tmp_path / "source"
    (source / "config").mkdir(parents=True)
    (source / "config" / "storygraph.default.json").write_text('{"managed": true}\n', encoding="utf-8")
    home = tmp_path / "home"
    destination = home / ".codex" / "skills" / "storygraph"
    (destination / "config").mkdir(parents=True)
    local_config = destination / "config" / "storygraph.local.json"
    local_config.write_text('{"local": true}\n', encoding="utf-8")
    (destination / "config" / "storygraph.default.json").write_text('{"old": true}\n', encoding="utf-8")
    script = Path("skill-src/storygraph/scripts/sync-skill.ps1")
    env = os.environ.copy()
    env["USERPROFILE"] = str(home)
    result = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
            "-Source",
            str(source),
            "-Clean",
        ],
        capture_output=True,
        text=True,
        env=env,
    )
    assert result.returncode == 0
    assert local_config.read_text(encoding="utf-8") == '{"local": true}\n'
    assert (destination / "config" / "storygraph.default.json").read_text(encoding="utf-8") == (
        '{"managed": true}\n'
    )


def test_sync_preserves_destination_local_config_when_source_has_local_config(tmp_path):
    source = tmp_path / "source"
    destination = tmp_path / "custom-storygraph"
    (source / "config").mkdir(parents=True)
    (destination / "config").mkdir(parents=True)
    (source / "config" / "storygraph.default.json").write_text('{"managed": true}\n', encoding="utf-8")
    (source / "config" / "storygraph.local.json").write_text('{"source": true}\n', encoding="utf-8")
    (destination / "config" / "storygraph.default.json").write_text('{"old": true}\n', encoding="utf-8")
    local_config = destination / "config" / "storygraph.local.json"
    local_config.write_text('{"destination": true}\n', encoding="utf-8")
    script = Path("skill-src/storygraph/scripts/sync-skill.ps1")
    result = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
            "-Source",
            str(source),
            "-Destination",
            str(destination),
        ],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert local_config.read_text(encoding="utf-8") == '{"destination": true}\n'
    assert (destination / "config" / "storygraph.default.json").read_text(encoding="utf-8") == (
        '{"managed": true}\n'
    )


def test_storygraph_script_version_flag_remains_supported():
    result = subprocess.run(
        ["python", "skill-src/storygraph/scripts/storygraph.py", "--version"],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0
    assert result.stdout.strip() == "storygraph 0.1.0"


def test_config_check_accepts_config_and_preserves_explicit_missing_override_guard(capsys, tmp_path):
    from storygraph_lib.cli import main

    default = tmp_path / "storygraph.default.json"
    default.write_text(json.dumps({"graph_dir_suffix": ".from-config"}), encoding="utf-8")
    missing = tmp_path / "missing.local.json"

    assert main(["config-check", "--config", str(default), "--local-override", str(missing)]) == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert payload["error"] == "local_override_missing"
    assert payload["path"] == str(missing)


def test_config_check_config_and_local_override_merge(capsys, tmp_path):
    from storygraph_lib.cli import main

    default = tmp_path / "storygraph.default.json"
    default.write_text(json.dumps({"graph_dir_suffix": ".from-config"}), encoding="utf-8")
    local = tmp_path / "storygraph.local.json"
    local.write_text(json.dumps({"graph_dir_suffix": ".from-local"}), encoding="utf-8")

    assert main(["config-check", "--config", str(default), "--local-override", str(local)]) == 0
    payload = ast.literal_eval(capsys.readouterr().out)
    assert payload["ok"] is True
    assert payload["graph_dir_suffix"] == ".from-local"


@pytest.mark.parametrize(
    ("writer", "expected_error"),
    [
        (lambda path: path.write_text("{bad json", encoding="utf-8"), "config_json_error"),
        (lambda path: path.write_bytes(b"\xff"), "config_encoding_error"),
    ],
)
def test_config_check_bad_config_returns_structured_error(
    capsys, tmp_path, writer, expected_error
):
    from storygraph_lib.cli import main

    config = tmp_path / "storygraph.default.json"
    writer(config)

    assert main(["config-check", "--config", str(config)]) == 2
    payload = json.loads(capsys.readouterr().out)

    assert payload["ok"] is False
    assert payload["error"] == expected_error


@pytest.mark.parametrize(
    ("command", "writer", "expected_error"),
    [
        (
            "build-stage1",
            lambda path: path.write_text("{bad json", encoding="utf-8"),
            "config_json_error",
        ),
        (
            "build-stage1",
            lambda path: path.write_bytes(b"\xff"),
            "config_encoding_error",
        ),
        (
            "inspect-templates",
            lambda path: path.write_text("{bad json", encoding="utf-8"),
            "config_json_error",
        ),
        (
            "inspect-templates",
            lambda path: path.write_bytes(b"\xff"),
            "config_encoding_error",
        ),
    ],
)
def test_cli_commands_bad_config_returns_structured_error(
    capsys, tmp_path, command, writer, expected_error
):
    from storygraph_lib.cli import main

    config = tmp_path / "storygraph.default.json"
    writer(config)
    source = tmp_path / "mini.txt"
    source.write_text("法宝", encoding="utf-8")
    template_dir = tmp_path / "templates"
    template_dir.mkdir()
    args = [command, "--config", str(config), "--template-dir", str(template_dir)]
    if command == "build-stage1":
        args.extend(["--source", str(source)])

    assert main(args) == 2
    payload = json.loads(capsys.readouterr().out)

    assert payload["ok"] is False
    assert payload["error"] == expected_error


def test_inspect_templates_returns_discovery_inventory_without_legacy_matrix(capsys, tmp_path):
    from storygraph_lib.cli import main

    template_dir = tmp_path / "templates"
    template_dir.mkdir()
    (template_dir / "可配置模板.md").write_text("# 可配置模板\n", encoding="utf-8")
    config = tmp_path / "storygraph.default.json"
    config.write_text(
        json.dumps(
            {
                "graph_dir_suffix": ".storygraph",
                "output_language": "zh-CN",
                "template_discovery": {
                    "glob": "*模板.md",
                    "readme_index_file": "README.md",
                    "exclude_files": ["README.md"],
                    "readme_missing_policy": "warn",
                },
                "template_parser_rules": None,
                "status_enums": {
                    "requirement_statuses": [
                        "covered",
                        "needs_review",
                        "not_found_in_source",
                    ]
                },
                "template_count_policy": {
                    "expected_existing_templates": 1,
                    "enforce_integration_count": True,
                },
            }
        ),
        encoding="utf-8",
    )

    assert main(["inspect-templates", "--config", str(config), "--template-dir", str(template_dir)]) == 0
    payload = json.loads(capsys.readouterr().out)

    assert payload["ok"] is True
    assert payload["template_count"] == 1
    assert payload["expected_template_count"] == 1
    assert payload["enforce_integration_count"] is True
    assert payload["count_matches_expected"] is True
    assert payload["warnings"] == []
    assert payload["templates"] == [
        {
            "name": "可配置",
            "file": "可配置模板.md",
        }
    ]


def test_inspect_templates_bad_utf8_template_returns_structured_error(capsys, tmp_path):
    from storygraph_lib.cli import main

    config = tmp_path / "storygraph.default.json"
    config.write_text(
        json.dumps(
            {
                "graph_dir_suffix": ".storygraph",
                "output_language": "zh-CN",
                "template_discovery": {
                    "glob": "*模板.md",
                    "readme_index_file": "README.md",
                    "exclude_files": ["README.md"],
                    "readme_missing_policy": "warn",
                },
                "template_parser_rules": None,
                "template_graph_mappings": {
                    "default_mapping": {
                        "graph_node_mapping": ["generic_node"],
                        "graph_event_mapping": ["generic_event"],
                        "graph_relation_mapping": ["generic_relation"],
                    }
                },
                "status_enums": {
                    "requirement_statuses": [
                        "covered",
                        "needs_review",
                        "not_found_in_source",
                    ]
                },
                "template_count_policy": {
                    "expected_existing_templates": 1,
                    "enforce_integration_count": False,
                },
            }
        ),
        encoding="utf-8",
    )
    template_dir = tmp_path / "templates"
    template_dir.mkdir()
    (template_dir / "坏模板.md").write_bytes(b"\xff")

    assert main(["inspect-templates", "--config", str(config), "--template-dir", str(template_dir)]) == 2
    payload = json.loads(capsys.readouterr().out)

    assert payload["ok"] is False
    assert payload["error"] in {"template_discovery_failed", "template_encoding_error"}


def test_validate_graph_cli_reports_missing_outputs_and_blocking_ledger(capsys, tmp_path):
    from storygraph_lib.cli import main

    graph_dir = tmp_path / "mini.storygraph"
    (graph_dir / "coverage").mkdir(parents=True)
    (graph_dir / "coverage" / "agent-run-ledger.json").write_text(
        json.dumps(
            [
                {
                    "run_id": "stage1-graph-extraction",
                    "status": "failed",
                    "errors": [{"code": "graphify_artifact_missing"}],
                }
            ]
        ),
        encoding="utf-8",
    )

    assert main(["validate-graph", "--graph-dir", str(graph_dir)]) == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert "missing:manifest.json" in payload["errors"]
    assert "blocking_ledger:graphify_artifact_missing" in payload["errors"]


def test_validate_graph_dir_reports_bad_json_without_throwing(tmp_path):
    from storygraph_lib.validation import validate_graph_dir

    graph_dir = tmp_path / "mini.storygraph"
    (graph_dir / "graphify-out").mkdir(parents=True)
    (graph_dir / "requirements").mkdir()
    (graph_dir / "coverage").mkdir()
    _write_minimal_merge_queue(graph_dir)
    (graph_dir / "manifest.json").write_text("{bad json", encoding="utf-8")
    (graph_dir / "graphify-out" / "graph.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "graphify_schema_version": "test",
                "storygraph_schema_version": "1.0",
                "nodes": [],
                "edges": [],
                "hyperedges": [],
                "events": [],
                "evidence_index": [],
                "metadata": {},
            }
        ),
        encoding="utf-8",
    )
    (graph_dir / "graphify-out" / "GRAPH_REPORT.md").write_text("# report\n", encoding="utf-8")
    (graph_dir / "graphify-out" / "graph.html").write_text("<!doctype html>", encoding="utf-8")
    (graph_dir / "requirements" / "template-requirements.json").write_text(
        json.dumps({"template_count": 0, "templates": []}), encoding="utf-8"
    )
    (graph_dir / "coverage" / "chunk-ledger.json").write_text("[]", encoding="utf-8")
    (graph_dir / "coverage" / "evidence-index.json").write_text("[]", encoding="utf-8")
    (graph_dir / "coverage" / "template-readiness.json").write_text("[]", encoding="utf-8")
    (graph_dir / "coverage" / "agent-run-ledger.json").write_text("[]", encoding="utf-8")
    (graph_dir / "coverage" / "gap-report.md").write_text("", encoding="utf-8")

    result = validate_graph_dir(graph_dir)

    assert result.ok is False
    assert "bad_json:manifest.json" in result.errors


def test_validate_graph_dir_malformed_ledgers_return_errors_without_throwing(tmp_path):
    from storygraph_lib.validation import validate_graph_dir

    graph_dir = tmp_path / "mini.storygraph"
    (graph_dir / "graphify-out").mkdir(parents=True)
    (graph_dir / "requirements").mkdir()
    (graph_dir / "coverage").mkdir()
    _write_minimal_merge_queue(graph_dir)
    source = tmp_path / "mini.txt"
    source.write_text("法宝", encoding="utf-8")
    (graph_dir / "manifest.json").write_text(
        json.dumps(
            {
                "source_path": str(source),
                "source_size": len("法宝".encode("utf-8")),
                "stage_status": {"stage1": "success"},
            }
        ),
        encoding="utf-8",
    )
    (graph_dir / "graphify-out" / "graph.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "graphify_schema_version": "test",
                "storygraph_schema_version": "1.0",
                "nodes": [],
                "edges": [],
                "hyperedges": [],
                "events": [],
                "evidence_index": [],
                "metadata": {},
            }
        ),
        encoding="utf-8",
    )
    (graph_dir / "graphify-out" / "GRAPH_REPORT.md").write_text("# report\n", encoding="utf-8")
    (graph_dir / "graphify-out" / "graph.html").write_text("<!doctype html>", encoding="utf-8")
    (graph_dir / "requirements" / "template-requirements.json").write_text(
        json.dumps(
            {
                "template_count": 1,
                "templates": [{"template_name": "法宝分析", "required_fields": ["法宝"]}],
            }
        ),
        encoding="utf-8",
    )
    (graph_dir / "coverage" / "chunk-ledger.json").write_text(
        json.dumps(["not-a-chunk", {"chunk_id": "chunk-bad", "source_range": ["bad"]}]),
        encoding="utf-8",
    )
    (graph_dir / "coverage" / "evidence-index.json").write_text("[]", encoding="utf-8")
    (graph_dir / "coverage" / "template-readiness.json").write_text(
        json.dumps(
            [
                {"template_name": "法宝分析", "requirement_statuses": "not-a-list"},
                {"template_name": "坏记录", "requirement_statuses": ["not-a-dict"]},
            ]
        ),
        encoding="utf-8",
    )
    (graph_dir / "coverage" / "agent-run-ledger.json").write_text(
        json.dumps([{"run_id": "run-1", "status": "completed", "output_paths": [], "write_scope": []}]),
        encoding="utf-8",
    )
    (graph_dir / "coverage" / "gap-report.md").write_text("", encoding="utf-8")

    result = validate_graph_dir(graph_dir)

    assert result.ok is False
    assert "bad_chunk_record" in result.errors
    assert "bad_chunk_source_range:chunk-bad" in result.errors
    assert "bad_readiness_requirement_statuses:法宝分析" in result.errors
    assert "bad_readiness_status_record:坏记录" in result.errors


def test_validate_graph_dir_malformed_graph_collections_return_errors_without_throwing(
    tmp_path,
):
    from storygraph_lib.validation import validate_graph_dir

    graph_dir = tmp_path / "mini.storygraph"
    (graph_dir / "graphify-out").mkdir(parents=True)
    (graph_dir / "requirements").mkdir()
    (graph_dir / "coverage").mkdir()
    _write_minimal_merge_queue(graph_dir)
    source = tmp_path / "mini.txt"
    source.write_text("法宝", encoding="utf-8")
    (graph_dir / "manifest.json").write_text(
        json.dumps(
            {
                "source_path": str(source),
                "source_size": len("法宝"),
                "stage_status": {"stage1": "success"},
            }
        ),
        encoding="utf-8",
    )
    (graph_dir / "graphify-out" / "graph.json").write_text(
        json.dumps(
            {
                "schema_version": "1.0",
                "graphify_schema_version": "test",
                "storygraph_schema_version": "1.0",
                "nodes": {},
                "edges": [],
                "hyperedges": [],
                "events": [],
                "evidence_index": {},
                "metadata": {},
            }
        ),
        encoding="utf-8",
    )
    (graph_dir / "graphify-out" / "GRAPH_REPORT.md").write_text("# report\n", encoding="utf-8")
    (graph_dir / "graphify-out" / "graph.html").write_text("<!doctype html>", encoding="utf-8")
    (graph_dir / "requirements" / "template-requirements.json").write_text(
        json.dumps({"template_count": 0, "templates": []}), encoding="utf-8"
    )
    (graph_dir / "coverage" / "chunk-ledger.json").write_text(
        json.dumps(
            [
                {
                    "chunk_id": "chunk-0001",
                    "source_range": [0, len("法宝")],
                    "extraction_status": "completed",
                }
            ]
        ),
        encoding="utf-8",
    )
    (graph_dir / "coverage" / "evidence-index.json").write_text("[]", encoding="utf-8")
    (graph_dir / "coverage" / "template-readiness.json").write_text("[]", encoding="utf-8")
    (graph_dir / "coverage" / "agent-run-ledger.json").write_text(
        json.dumps([{"run_id": "run-1", "status": "completed", "output_paths": [], "write_scope": []}]),
        encoding="utf-8",
    )
    (graph_dir / "coverage" / "gap-report.md").write_text("", encoding="utf-8")

    result = validate_graph_dir(graph_dir)

    assert result.ok is False
    assert "bad_graph_collection:nodes" in result.errors
    assert "bad_graph_collection:evidence_index" in result.errors


def test_validate_graph_dir_malformed_graph_items_return_errors_without_throwing(
    tmp_path,
):
    from storygraph_lib.validation import validate_graph_dir

    graph_dir = tmp_path / "mini.storygraph"
    _write_minimal_valid_graph_dir(graph_dir, graph={"nodes": ["not-object"]})

    result = validate_graph_dir(graph_dir)

    assert result.ok is False
    assert "bad_graph_item:nodes" in result.errors


def test_validate_graph_dir_graph_evidence_index_null_returns_errors_without_throwing(
    tmp_path,
):
    from storygraph_lib.validation import validate_graph_dir

    graph_dir = tmp_path / "mini.storygraph"
    _write_minimal_valid_graph_dir(graph_dir, graph={"evidence_index": None})

    result = validate_graph_dir(graph_dir)

    assert result.ok is False
    assert "bad_graph_collection:evidence_index" in result.errors


def test_validate_graph_dir_graph_item_evidence_ids_null_returns_errors_without_throwing(
    tmp_path,
):
    from storygraph_lib.validation import validate_graph_dir

    graph_dir = tmp_path / "mini.storygraph"
    evidence = [
        {
            "evidence_id": "evidence:valid",
            "source_range": [0, 1],
            "fact_summary": "valid",
            "confidence": "EXTRACTED",
            "verification_status": "verified",
            "supports_templates": [
                {
                    "template_name": "法宝分析",
                    "requirement_id": "法宝分析.required_fields.法宝",
                    "status": "covered",
                }
            ],
        }
    ]
    _write_minimal_valid_graph_dir(
        graph_dir,
        coverage_evidence=evidence,
        graph={
            "nodes": [
                {
                    "id": "node:badrefs",
                    "label": "坏引用",
                    "node_type": "artifact",
                    "source_range": [0, 1],
                    "evidence_ids": None,
                    "supports_templates": [
                        {
                            "template_name": "法宝分析",
                            "requirement_id": "法宝分析.required_fields.法宝",
                            "status": "covered",
                        }
                    ],
                    "confidence": "EXTRACTED",
                    "verification_status": "verified",
                }
            ],
            "evidence_index": evidence,
        },
    )

    result = validate_graph_dir(graph_dir)

    assert result.ok is False
    assert "bad_graph_evidence_refs:node:badrefs" in result.errors


def test_validate_graph_dir_malformed_agent_ledger_records_return_errors_without_throwing(
    tmp_path,
):
    from storygraph_lib.validation import validate_graph_dir

    graph_dir = tmp_path / "mini.storygraph"
    _write_minimal_valid_graph_dir(
        graph_dir,
        agent_ledger=[
            "not-a-record",
            {
                "run_id": "stage1-template-requirements",
                "agent_role": "模板需求分析",
                "status": "completed",
                "output_paths": 1,
                "write_scope": [],
            },
            {
                "run_id": "stage1-graph-extraction",
                "agent_role": "图抽取",
                "status": "completed",
                "output_paths": [],
                "write_scope": 1,
            },
            {
                "run_id": "stage1-coverage-review",
                "agent_role": "覆盖审查",
                "status": "completed",
                "output_paths": [],
                "write_scope": [],
            },
            {
                "run_id": "stage1-quality-review",
                "agent_role": "质量审查",
                "status": "completed",
                "output_paths": [],
                "write_scope": [],
            },
        ],
    )

    result = validate_graph_dir(graph_dir)

    assert result.ok is False
    assert "bad_agent_ledger_record" in result.errors
    assert "invalid_path_list:stage1-template-requirements:output_paths" in result.errors
    assert "invalid_path_list:stage1-graph-extraction:write_scope" in result.errors


def test_validate_graph_dir_malformed_agent_ledger_path_items_return_errors_without_throwing(
    tmp_path,
):
    from storygraph_lib.validation import validate_graph_dir

    graph_dir = tmp_path / "mini.storygraph"
    _write_minimal_valid_graph_dir(
        graph_dir,
        agent_ledger=[
            {
                "run_id": "stage1-template-requirements",
                "agent_role": "模板需求分析",
                "status": "completed",
                "output_paths": [{"not": "a path"}],
                "write_scope": [],
            },
            {
                "run_id": "stage1-graph-extraction",
                "agent_role": "图抽取",
                "status": "completed",
                "output_paths": [],
                "write_scope": [["also-not-a-path"]],
            },
            {
                "run_id": "stage1-coverage-review",
                "agent_role": "覆盖审查",
                "status": "completed",
                "output_paths": [],
                "write_scope": [],
            },
            {
                "run_id": "stage1-quality-review",
                "agent_role": "质量审查",
                "status": "completed",
                "output_paths": [],
                "write_scope": [],
            },
        ],
    )

    result = validate_graph_dir(graph_dir)

    assert result.ok is False
    assert "invalid_path_item:stage1-template-requirements:output_paths" in result.errors
    assert "invalid_path_item:stage1-graph-extraction:write_scope" in result.errors


def test_validate_graph_dir_failed_ledger_bad_errors_shape_returns_errors_without_throwing(
    tmp_path,
):
    from storygraph_lib.validation import validate_graph_dir

    graph_dir = tmp_path / "mini.storygraph"
    _write_minimal_valid_graph_dir(
        graph_dir,
        agent_ledger=[
            {
                "run_id": "stage1-graph-extraction",
                "agent_role": "图抽取",
                "status": "failed",
                "errors": 1,
                "output_paths": [],
                "write_scope": [],
            }
        ],
    )

    result = validate_graph_dir(graph_dir)

    assert result.ok is False
    assert "bad_agent_ledger_errors:stage1-graph-extraction" in result.errors
    assert "blocking_ledger:unknown" in result.errors


def test_validate_graph_dir_manifest_stage_status_bad_shape_returns_errors_without_throwing(
    tmp_path,
):
    from storygraph_lib.validation import validate_graph_dir

    graph_dir = tmp_path / "mini.storygraph"
    _write_minimal_valid_graph_dir(graph_dir, manifest={"stage_status": "success"})

    result = validate_graph_dir(graph_dir)

    assert result.ok is False
    assert "bad_manifest_stage_status" in result.errors


def test_validate_graph_dir_malformed_requirement_shapes_return_errors_without_throwing(
    tmp_path,
):
    from storygraph_lib.validation import validate_graph_dir

    graph_dir = tmp_path / "mini.storygraph"
    _write_minimal_valid_graph_dir(
        graph_dir,
        manifest={
            "source_size": {"bad": True},
            "stage_status": {"stage1": "success"},
        },
        requirements={
            "template_count": 1,
            "status_enums": ["not-a-dict"],
            "templates": [{"template_name": "法宝分析", "required_fields": None}],
        },
        readiness=[{"template_name": "法宝分析", "requirement_statuses": []}],
    )

    result = validate_graph_dir(graph_dir)

    assert result.ok is False
    assert "bad_requirement_list:法宝分析:required_fields" in result.errors
    assert "bad_status_enums" in result.errors
    assert "bad_manifest_source_size" in result.errors


@pytest.mark.parametrize("source_path", [[1], {"bad": "path"}, True])
def test_validate_graph_dir_manifest_source_path_bad_shape_returns_errors_without_throwing(
    tmp_path, source_path
):
    from storygraph_lib.validation import validate_graph_dir

    graph_dir = tmp_path / "mini.storygraph"
    _write_minimal_valid_graph_dir(
        graph_dir,
        manifest={"source_path": source_path, "source_size": len("法宝")},
    )

    result = validate_graph_dir(graph_dir)

    assert result.ok is False
    assert "bad_manifest_source_path" in result.errors


def test_validate_graph_dir_manifest_source_path_embedded_nul_is_reported(tmp_path):
    from storygraph_lib.validation import validate_graph_dir

    graph_dir = tmp_path / "mini.storygraph"
    _write_minimal_valid_graph_dir(
        graph_dir,
        manifest={"source_path": "bad\0path", "source_size": None},
    )

    result = validate_graph_dir(graph_dir)

    assert result.ok is False
    assert "bad_manifest_source_path" in result.errors


def test_validate_graph_dir_agent_ledger_embedded_nul_path_is_invalid(tmp_path):
    from storygraph_lib.validation import validate_graph_dir

    graph_dir = tmp_path / "ledger-nul.storygraph"
    agent_ledger = [
        {
            "run_id": f"stage1-{index}",
            "agent_role": role,
            "status": "completed",
            "output_paths": ["coverage/x\0.json"] if index == 1 else [],
            "write_scope": ["coverage/x\0.json"] if index == 1 else [],
        }
        for index, role in enumerate(["模板需求分析", "图抽取", "覆盖审查", "质量审查"], start=1)
    ]
    _write_minimal_valid_graph_dir(graph_dir, agent_ledger=agent_ledger)

    result = validate_graph_dir(graph_dir)

    assert result.ok is False
    assert any(error.startswith("invalid_path:") for error in result.errors)


def test_validate_graph_dir_requirement_nested_items_return_errors_without_throwing(
    tmp_path,
):
    from storygraph_lib.validation import validate_graph_dir

    graph_dir = tmp_path / "mini.storygraph"
    _write_minimal_valid_graph_dir(
        graph_dir,
        requirements={
            "template_count": 1,
            "templates": [{"template_name": "法宝分析", "required_fields": [["bad-nested"]]}],
        },
        readiness=[{"template_name": "法宝分析", "requirement_statuses": []}],
    )

    result = validate_graph_dir(graph_dir)

    assert result.ok is False
    assert "bad_requirement_item:法宝分析:required_fields" in result.errors


def test_validate_graph_dir_rejects_float_source_ranges(tmp_path):
    from storygraph_lib.validation import validate_graph_dir

    graph_dir = tmp_path / "mini.storygraph"
    evidence = [
        {
            "evidence_id": "evidence:float",
            "source_range": [0.0, 1.0],
            "fact_summary": "float range",
            "confidence": "EXTRACTED",
            "verification_status": "verified",
            "supports_templates": [
                {
                    "template_name": "法宝分析",
                    "requirement_id": "法宝分析.required_fields.法宝",
                    "status": "covered",
                }
            ],
        }
    ]
    _write_minimal_valid_graph_dir(
        graph_dir,
        chunks=[
            {
                "chunk_id": "chunk-float",
                "source_range": [0.0, 2.0],
                "extraction_status": "completed",
            }
        ],
        coverage_evidence=evidence,
        graph={"evidence_index": evidence},
    )

    result = validate_graph_dir(graph_dir)

    assert result.ok is False
    assert "bad_chunk_source_range:chunk-float" in result.errors
    assert "bad_evidence_source_range:evidence:float" in result.errors


def test_validate_graph_dir_rejects_graph_node_float_source_range(tmp_path):
    from storygraph_lib.validation import validate_graph_dir

    graph_dir = tmp_path / "mini.storygraph"
    evidence = [
        {
            "evidence_id": "evidence:valid",
            "source_range": [0, 2],
            "fact_summary": "valid",
            "confidence": "EXTRACTED",
            "verification_status": "verified",
            "supports_templates": [
                {
                    "template_name": "法宝分析",
                    "requirement_id": "法宝分析.required_fields.法宝",
                    "status": "covered",
                }
            ],
        }
    ]
    _write_minimal_valid_graph_dir(
        graph_dir,
        coverage_evidence=evidence,
        graph={
            "nodes": [
                {
                    "id": "node:item:float",
                    "label": "小瓶",
                    "node_type": "artifact",
                    "source_range": [0.5, 1.5],
                    "evidence_ids": ["evidence:valid"],
                    "supports_templates": [
                        {
                            "template_name": "法宝分析",
                            "requirement_id": "法宝分析.required_fields.法宝",
                            "status": "covered",
                        }
                    ],
                    "confidence": "EXTRACTED",
                    "verification_status": "verified",
                }
            ],
            "evidence_index": evidence,
        },
    )

    result = validate_graph_dir(graph_dir)

    assert result.ok is False
    assert "node_bad_source_range:node:item:float" in result.errors


def test_validate_graph_dir_rejects_native_graph_node_non_string_id(tmp_path):
    from storygraph_lib.validation import validate_graph_dir

    graph_dir = tmp_path / "mini.storygraph"
    _write_minimal_valid_graph_dir(
        graph_dir,
        graph={"nodes": [{"id": ["bad"], "source_range": [0, 1]}]},
    )

    result = validate_graph_dir(graph_dir)

    assert result.ok is False
    assert "node_bad_id:['bad']" in result.errors


def test_validate_graph_dir_rejects_native_graph_node_scalar_source_location(tmp_path):
    from storygraph_lib.validation import validate_graph_dir

    graph_dir = tmp_path / "mini.storygraph"
    _write_minimal_valid_graph_dir(
        graph_dir,
        graph={"nodes": [{"id": "node:native", "source_location": 123}]},
    )

    result = validate_graph_dir(graph_dir)

    assert result.ok is False
    assert "node_bad_source_location:node:native" in result.errors


def test_validate_graph_dir_rejects_non_object_coverage_evidence_record(tmp_path):
    from storygraph_lib.validation import validate_graph_dir

    graph_dir = tmp_path / "mini.storygraph"
    _write_minimal_valid_graph_dir(graph_dir, coverage_evidence=["not-object"])

    result = validate_graph_dir(graph_dir)

    assert result.ok is False
    assert "bad_coverage_evidence_record" in result.errors


def test_validate_graph_dir_rejects_malformed_coverage_evidence_record(tmp_path):
    from storygraph_lib.validation import validate_graph_dir

    graph_dir = tmp_path / "mini.storygraph"
    graph = {
        "evidence_index": [
            {
                "evidence_id": "evidence:1",
                "source_range": [0, 1],
                "fact_summary": "ok",
                "confidence": "EXTRACTED",
                "verification_status": "verified",
                "supports_templates": [
                    {
                        "template_name": "法宝分析",
                        "requirement_id": "法宝分析.required_fields.法宝",
                        "status": "covered",
                    }
                ],
            }
        ]
    }
    coverage_evidence = [
        {
            "evidence_id": "evidence:1",
            "source_range": [0, 1],
            "fact_summary": "ok",
            "confidence": "BOGUS",
            "verification_status": "bogus",
            "supports_templates": ["bad"],
        }
    ]
    _write_minimal_valid_graph_dir(
        graph_dir, graph=graph, coverage_evidence=coverage_evidence
    )

    result = validate_graph_dir(graph_dir)

    assert result.ok is False
    assert "bad_confidence:BOGUS" in result.errors
    assert "bad_verification_status:bogus" in result.errors
    assert "evidence_bad_support:evidence:1" in result.errors


def test_validate_graph_dir_rejects_malformed_readiness_link_fields(tmp_path):
    from storygraph_lib.validation import validate_graph_dir

    graph_dir = tmp_path / "mini.storygraph"
    readiness = [
        {
            "template_name": "法宝分析",
            "requirement_statuses": [
                {
                    "requirement_id": "法宝分析.required_fields.法宝",
                    "status": "covered",
                    "linked_node_ids": [["bad"]],
                    "linked_edge_ids": "bad",
                    "linked_event_ids": [1],
                    "evidence_ids": [{"bad": "id"}],
                    "notes": "bad",
                }
            ],
        }
    ]
    _write_minimal_valid_graph_dir(graph_dir, readiness=readiness)

    result = validate_graph_dir(graph_dir)

    assert result.ok is False
    assert "bad_readiness_linked_node_ids:法宝分析.required_fields.法宝" in result.errors
    assert "bad_readiness_linked_edge_ids:法宝分析.required_fields.法宝" in result.errors
    assert "bad_readiness_linked_event_ids:法宝分析.required_fields.法宝" in result.errors
    assert "bad_readiness_evidence_ids:法宝分析.required_fields.法宝" in result.errors
    assert "bad_readiness_notes:法宝分析.required_fields.法宝" in result.errors


def test_validate_graph_dir_uses_dynamic_template_readiness_count(tmp_path):
    from storygraph_lib.validation import validate_graph_dir

    graph_dir = tmp_path / "mini.storygraph"
    sample_template_count = 37
    requirements = {
        "template_count": sample_template_count,
        "templates": [
            {"template_name": f"模板{index:02d}", "required_fields": ["字段"]}
            for index in range(sample_template_count)
        ],
    }
    readiness = [
        {
            "template_name": f"模板{index:02d}",
            "requirement_statuses": [
                {
                    "requirement_id": f"模板{index:02d}.required_fields.字段",
                    "status": "covered",
                }
            ],
        }
        for index in range(36)
    ]
    _write_minimal_valid_graph_dir(
        graph_dir, requirements=requirements, readiness=readiness
    )

    result = validate_graph_dir(graph_dir)

    assert result.ok is False
    assert "requirements_readiness_template_mismatch" in result.errors
    assert "requirements_readiness_id_mismatch" in result.errors
    assert not any(error.startswith("template_readiness_count_not_") for error in result.errors)


def test_validate_graph_dir_rejects_duplicate_readiness_template_names(tmp_path):
    from storygraph_lib.validation import validate_graph_dir

    graph_dir = tmp_path / "mini.storygraph"
    readiness = [
        {
            "template_name": "法宝分析",
            "requirement_statuses": [
                {"requirement_id": "法宝分析.required_fields.法宝", "status": "covered"}
            ],
        },
        {
            "template_name": "法宝分析",
            "requirement_statuses": [
                {"requirement_id": "法宝分析.required_fields.法宝", "status": "covered"}
            ],
        },
    ]
    _write_minimal_valid_graph_dir(graph_dir, readiness=readiness)

    result = validate_graph_dir(graph_dir)

    assert result.ok is False
    assert "duplicate_readiness_template_name:法宝分析" in result.errors


@pytest.mark.parametrize(
    ("case_name", "kwargs", "expected_errors"),
    [
        (
            "manifest_stage_status_non_dict",
            {"manifest": {"stage_status": "success"}},
            ["bad_manifest_stage_status"],
        ),
        (
            "manifest_source_path_non_path_string",
            {"manifest": {"source_path": {"bad": "path"}, "source_size": len("法宝")}},
            ["bad_manifest_source_path"],
        ),
        (
            "graph_collection_non_list",
            {"graph": {"nodes": {}, "evidence_index": None}},
            ["bad_graph_collection:nodes", "bad_graph_collection:evidence_index"],
        ),
        (
            "graph_item_non_dict",
            {"graph": {"nodes": ["not-object"]}},
            ["bad_graph_item:nodes"],
        ),
        (
            "graph_item_id_non_str",
            {"graph": {"nodes": [{"id": ["bad"], "source_range": [0, 1]}]}},
            ["node_bad_id:['bad']"],
        ),
        (
            "graph_item_source_range_float",
            {"graph": {"nodes": [{"id": "node:native", "source_range": [0.5, 1.5]}]}},
            ["node_bad_source_range:node:native"],
        ),
        (
            "graph_item_source_location_bad_shapes",
            {
                "graph": {
                    "nodes": [
                        {"id": "node:scalar", "source_location": 123},
                        {
                            "id": "node:nested",
                            "source_location": {"source_range": [0.5, 1.5]},
                        },
                    ]
                }
            },
            [
                "node_bad_source_location:node:scalar",
                "node_bad_source_location_range:node:nested",
            ],
        ),
        (
            "graph_evidence_index_non_list",
            {"graph": {"evidence_index": "bad"}},
            ["bad_graph_collection:evidence_index"],
        ),
        (
            "graph_evidence_fact_summary_non_string",
            {
                "graph": {
                    "evidence_index": [
                        {
                            "evidence_id": "evidence:1",
                            "source_range": [0, 1],
                            "fact_summary": ["bad"],
                            "confidence": "EXTRACTED",
                            "verification_status": "verified",
                            "supports_templates": [
                                {
                                    "template_name": "法宝分析",
                                    "requirement_id": "法宝分析.required_fields.法宝",
                                    "status": "covered",
                                }
                            ],
                        }
                    ]
                },
                "coverage_evidence": [
                    {
                        "evidence_id": "evidence:1",
                        "source_range": [0, 1],
                        "fact_summary": "ok",
                        "confidence": "EXTRACTED",
                        "verification_status": "verified",
                        "supports_templates": [
                            {
                                "template_name": "法宝分析",
                                "requirement_id": "法宝分析.required_fields.法宝",
                                "status": "covered",
                            }
                        ],
                    }
                ],
                "readiness": [
                    {
                        "template_name": "法宝分析",
                        "requirement_statuses": [
                            {
                                "requirement_id": "法宝分析.required_fields.法宝",
                                "status": "covered",
                                "evidence_ids": ["evidence:1"],
                            }
                        ],
                    }
                ],
            },
            ["bad_evidence_fact_summary:evidence:1"],
        ),
        (
            "graph_top_level_bad_shapes",
            {
                "graph": {
                    "schema_version": ["bad"],
                    "graphify_schema_version": 123,
                    "storygraph_schema_version": None,
                    "metadata": "bad",
                }
            },
            [
                "bad_graph_top_level:schema_version",
                "bad_graph_top_level:graphify_schema_version",
                "bad_graph_top_level:storygraph_schema_version",
                "bad_graph_top_level:metadata",
            ],
        ),
        (
            "coverage_evidence_non_dict",
            {"coverage_evidence": ["not-object"]},
            ["bad_coverage_evidence_record"],
        ),
        (
            "coverage_evidence_missing_evidence_id",
            {"coverage_evidence": [{"source_range": [0, 1], "fact_summary": "missing"}]},
            ["bad_coverage_evidence_id"],
        ),
        (
            "coverage_evidence_bad_status_enums_and_support_shape",
            {
                "graph": {
                    "evidence_index": [
                        {
                            "evidence_id": "evidence:1",
                            "source_range": [0, 1],
                            "fact_summary": "ok",
                            "confidence": "EXTRACTED",
                            "verification_status": "verified",
                            "supports_templates": [
                                {
                                    "template_name": "法宝分析",
                                    "requirement_id": "法宝分析.required_fields.法宝",
                                    "status": "covered",
                                }
                            ],
                        }
                    ]
                },
                "coverage_evidence": [
                    {
                        "evidence_id": "evidence:1",
                        "source_range": [0, 1],
                        "fact_summary": "ok",
                        "confidence": "BOGUS",
                        "verification_status": "bogus",
                        "supports_templates": ["bad"],
                    }
                ],
            },
            [
                "bad_confidence:BOGUS",
                "bad_verification_status:bogus",
                "evidence_bad_support:evidence:1",
            ],
        ),
        (
            "coverage_evidence_support_missing_required_field",
            {
                "graph": {
                    "evidence_index": [
                        {
                            "evidence_id": "evidence:1",
                            "source_range": [0, 1],
                            "fact_summary": "ok",
                            "confidence": "EXTRACTED",
                            "verification_status": "verified",
                            "supports_templates": [
                                {
                                    "template_name": "法宝分析",
                                    "requirement_id": "法宝分析.required_fields.法宝",
                                    "status": "covered",
                                }
                            ],
                        }
                    ]
                },
                "coverage_evidence": [
                    {
                        "evidence_id": "evidence:1",
                        "source_range": [0, 1],
                        "fact_summary": "ok",
                        "confidence": "EXTRACTED",
                        "verification_status": "verified",
                        "supports_templates": [{"template_name": "法宝分析"}],
                    }
                ],
            },
            [
                "evidence_support_missing:evidence:1:requirement_id",
                "evidence_support_missing:evidence:1:status",
                "bad_requirement_status:None",
            ],
        ),
        (
            "coverage_evidence_malformed_optional_fields",
            {
                "graph": {
                    "evidence_index": [
                        {
                            "evidence_id": "evidence:1",
                            "source_range": [0, 1],
                            "fact_summary": "ok",
                            "confidence": "EXTRACTED",
                            "verification_status": "verified",
                            "supports_templates": [
                                {
                                    "template_name": "法宝分析",
                                    "requirement_id": "法宝分析.required_fields.法宝",
                                    "status": "covered",
                                }
                            ],
                        }
                    ]
                },
                "coverage_evidence": [
                    {
                        "evidence_id": "evidence:1",
                        "source_path": {},
                        "source_location": 123,
                        "chunk_id": [],
                        "chapter_hint": {},
                        "support": None,
                        "linked_node_ids": "bad",
                        "linked_edge_ids": [{}],
                        "linked_event_ids": [1],
                    }
                ],
                "readiness": [
                    {
                        "template_name": "法宝分析",
                        "requirement_statuses": [
                            {
                                "requirement_id": "法宝分析.required_fields.法宝",
                                "status": "covered",
                                "evidence_ids": ["evidence:1"],
                            }
                        ],
                    }
                ],
            },
            [
                "bad_coverage_source_path:evidence:1",
                "bad_coverage_source_location:evidence:1",
                "bad_coverage_chunk_id:evidence:1",
                "bad_coverage_chapter_hint:evidence:1",
                "bad_coverage_support:evidence:1",
                "bad_coverage_linked_node_ids:evidence:1",
                "bad_coverage_linked_edge_ids:evidence:1",
                "bad_coverage_linked_event_ids:evidence:1",
            ],
        ),
        (
            "requirements_nested_required_fields",
            {
                "requirements": {
                    "template_count": 1,
                    "templates": [
                        {"template_name": "法宝分析", "required_fields": [["nested"], 1]}
                    ],
                },
                "readiness": [{"template_name": "法宝分析", "requirement_statuses": []}],
            },
            ["bad_requirement_item:法宝分析:required_fields"],
        ),
        (
            "requirements_template_count_string",
            {
                "requirements": {
                    "template_count": "1",
                    "templates": [{"template_name": "法宝分析", "required_fields": ["法宝"]}],
                }
            },
            ["bad_requirements_template_count"],
        ),
        (
            "requirements_template_count_mismatch",
            {
                "requirements": {
                    "template_count": 2,
                    "templates": [{"template_name": "法宝分析", "required_fields": ["法宝"]}],
                }
            },
            ["requirements_template_count_mismatch"],
        ),
        (
            "manifest_source_size_string",
            {"manifest": {"source_size": "2"}},
            ["bad_manifest_source_size"],
        ),
        (
            "manifest_source_size_float",
            {"manifest": {"source_size": 2.0}},
            ["bad_manifest_source_size"],
        ),
        (
            "readiness_requirement_statuses_non_list",
            {"readiness": [{"template_name": "法宝分析", "requirement_statuses": "bad"}]},
            ["bad_readiness_requirement_statuses:法宝分析"],
        ),
        (
            "readiness_nested_link_fields",
            {
                "readiness": [
                    {
                        "template_name": "法宝分析",
                        "requirement_statuses": [
                            {
                                "requirement_id": "法宝分析.required_fields.法宝",
                                "status": "covered",
                                "linked_node_ids": [["bad"]],
                                "linked_edge_ids": "bad",
                                "linked_event_ids": [1],
                                "evidence_ids": [{"bad": "id"}],
                                "notes": "bad",
                            }
                        ],
                    }
                ]
            },
            [
                "bad_readiness_linked_node_ids:法宝分析.required_fields.法宝",
                "bad_readiness_linked_edge_ids:法宝分析.required_fields.法宝",
                "bad_readiness_linked_event_ids:法宝分析.required_fields.法宝",
                "bad_readiness_evidence_ids:法宝分析.required_fields.法宝",
                "bad_readiness_notes:法宝分析.required_fields.法宝",
            ],
        ),
        (
            "readiness_unknown_link_references",
            {
                "readiness": [
                    {
                        "template_name": "法宝分析",
                        "requirement_statuses": [
                            {
                                "requirement_id": "法宝分析.required_fields.法宝",
                                "status": "covered",
                                "linked_node_ids": ["node:missing"],
                                "linked_edge_ids": ["edge:missing"],
                                "linked_event_ids": ["event:missing"],
                                "evidence_ids": ["evidence:missing"],
                            }
                        ],
                    }
                ]
            },
            [
                "unknown_readiness_node:node:missing",
                "unknown_readiness_edge:edge:missing",
                "unknown_readiness_event:event:missing",
                "unknown_readiness_evidence:evidence:missing",
            ],
        ),
        (
            "readiness_summary_malformed_fields",
            {
                "readiness": [
                    {
                        "template_name": "法宝分析",
                        "readiness_score": "bad",
                        "supporting_node_count": "x",
                        "supporting_edge_count": {},
                        "supporting_event_count": [],
                        "evidence_count": None,
                        "missing_requirement_types": "fields",
                        "requirement_statuses": [
                            {
                                "requirement_id": "法宝分析.required_fields.法宝",
                                "status": "covered",
                            }
                        ],
                        "notes": "bad",
                    }
                ]
            },
            [
                "bad_readiness_score:法宝分析",
                "bad_readiness_supporting_node_count:法宝分析",
                "bad_readiness_supporting_edge_count:法宝分析",
                "bad_readiness_supporting_event_count:法宝分析",
                "bad_readiness_evidence_count:法宝分析",
                "bad_readiness_missing_requirement_types:法宝分析",
                "bad_readiness_notes:法宝分析",
            ],
        ),
        (
            "agent_ledger_record_non_dict",
            {"agent_ledger": ["not-record"]},
            ["bad_agent_ledger_record"],
        ),
        (
            "agent_ledger_errors_non_list",
            {
                "agent_ledger": [
                    {
                        "run_id": "stage1-graph-extraction",
                        "agent_role": "图抽取",
                        "status": "failed",
                        "errors": 1,
                        "output_paths": [],
                        "write_scope": [],
                    }
                ]
            },
            ["bad_agent_ledger_errors:stage1-graph-extraction"],
        ),
        (
            "agent_ledger_path_item_dict_list",
            {
                "agent_ledger": [
                    {
                        "run_id": "stage1-template-requirements",
                        "agent_role": "模板需求分析",
                        "status": "completed",
                        "output_paths": [{"not": "a path"}],
                        "write_scope": [],
                    },
                    {
                        "run_id": "stage1-graph-extraction",
                        "agent_role": "图抽取",
                        "status": "completed",
                        "output_paths": [],
                        "write_scope": [["also-not-a-path"]],
                    },
                    {
                        "run_id": "stage1-coverage-review",
                        "agent_role": "覆盖审查",
                        "status": "completed",
                        "output_paths": [],
                        "write_scope": [],
                    },
                    {
                        "run_id": "stage1-quality-review",
                        "agent_role": "质量审查",
                        "status": "completed",
                        "output_paths": [],
                        "write_scope": [],
                    },
                ]
            },
            [
                "invalid_path_item:stage1-template-requirements:output_paths",
                "invalid_path_item:stage1-graph-extraction:write_scope",
            ],
        ),
        (
            "chunk_source_range_float",
            {
                "chunks": [
                    {
                        "chunk_id": "chunk-float",
                        "source_range": [0.0, 2.0],
                        "extraction_status": "completed",
                    }
                ]
            },
            ["bad_chunk_source_range:chunk-float"],
        ),
        (
            "chunk_malformed_optional_fields",
            {
                "chunks": [
                    {
                        "chunk_id": ["bad-id"],
                        "source_path": {"bad": "path"},
                        "source_range": [0, 2],
                        "chapter_hint": 123,
                        "hash": [],
                        "scanned_at": {},
                        "processor": None,
                        "extraction_status": "completed",
                        "failure": "bad",
                        "retry_count": "zero",
                        "text": 5,
                    }
                ]
            },
            [
                "bad_chunk_id",
                "bad_chunk_source_path:unknown",
                "bad_chunk_chapter_hint:unknown",
                "bad_chunk_hash:unknown",
                "bad_chunk_scanned_at:unknown",
                "bad_chunk_processor:unknown",
                "bad_chunk_failure:unknown",
                "bad_chunk_retry_count:unknown",
                "bad_chunk_text:unknown",
            ],
        ),
    ],
)
def test_validate_graph_dir_external_json_malformed_regression_matrix(
    tmp_path, case_name, kwargs, expected_errors
):
    from storygraph_lib.validation import validate_graph_dir

    graph_dir = tmp_path / f"{case_name}.storygraph"
    _write_minimal_valid_graph_dir(graph_dir, **kwargs)

    result = validate_graph_dir(graph_dir)

    assert result.ok is False
    for expected_error in expected_errors:
        assert expected_error in result.errors


@pytest.mark.parametrize(
    "relative_path",
    [
        "manifest.json",
        "graphify-out/graph.json",
        "requirements/template-requirements.json",
        "coverage/chunk-ledger.json",
        "coverage/evidence-index.json",
        "coverage/template-readiness.json",
        "coverage/agent-run-ledger.json",
    ],
)
def test_validate_graph_dir_external_json_invalid_utf8_regression_matrix(
    tmp_path, relative_path
):
    from storygraph_lib.validation import validate_graph_dir

    graph_dir = tmp_path / "invalid_utf8.storygraph"
    _write_minimal_valid_graph_dir(
        graph_dir,
        requirements={"template_count": 0, "templates": []},
        readiness=[],
    )
    (graph_dir / Path(*relative_path.split("/"))).write_bytes(b"\xff")

    result = validate_graph_dir(graph_dir)

    assert result.ok is False
    assert f"bad_json:{relative_path}" in result.errors


def test_validate_graph_dir_external_json_deep_recursion_is_bad_json(tmp_path):
    from storygraph_lib.validation import validate_graph_dir

    graph_dir = tmp_path / "deep.storygraph"
    _write_minimal_valid_graph_dir(
        graph_dir,
        requirements={"template_count": 0, "templates": []},
        readiness=[],
    )
    (graph_dir / "graphify-out" / "graph.json").write_text(
        "[" * 20000 + "0" + "]" * 20000,
        encoding="utf-8",
    )

    result = validate_graph_dir(graph_dir)

    assert result.ok is False
    assert "bad_json:graphify-out/graph.json" in result.errors


def test_validate_graph_dir_requires_success_stage1_agent_roles(tmp_path):
    from storygraph_lib.validation import validate_graph_dir

    graph_dir = tmp_path / "mini.storygraph"
    _write_minimal_valid_graph_dir(
        graph_dir,
        requirements={"template_count": 0, "templates": []},
        readiness=[],
        agent_ledger=[
            {
                "run_id": "stage1-quality-review",
                "agent_role": "质量审查",
                "status": "completed",
                "output_paths": [],
                "write_scope": [],
            }
        ],
    )

    result = validate_graph_dir(graph_dir)

    assert result.ok is False
    assert "missing_agent_role:模板需求分析" in result.errors
    assert "missing_agent_role:图抽取" in result.errors
    assert "missing_agent_role:覆盖审查" in result.errors


def test_validate_graph_dir_requires_agent_driven_artifacts(tmp_path):
    from storygraph_lib.validation import validate_graph_dir

    graph_dir = tmp_path / "mini.storygraph"
    _write_minimal_valid_graph_dir(
        graph_dir,
        graph={
            "metadata": {},
        },
        agent_ledger=None,
    )
    (graph_dir / "coverage" / "agent-run-ledger.json").unlink()

    result = validate_graph_dir(graph_dir)

    assert result.ok is False
    assert "missing_agent_run_ledger" in result.errors
    assert "missing_lane_outputs" in result.errors
    assert "canonical_graph_without_agent_provenance" in result.errors


def test_validate_graph_dir_rejects_corrupt_agent_driven_artifacts(tmp_path):
    from storygraph_lib.validation import validate_graph_dir

    lane_output_path = "intermediate/lane-outputs/chunk-0001/entities_resources/run-001.json"
    graph_dir = tmp_path / "mini.storygraph"
    _write_minimal_valid_graph_dir(
        graph_dir,
        graph={
            "metadata": {
                "semantic_generation": "agent-produced",
                "canonical_writer_version": "stage1-agent-driven.v1",
                "source_bundle_paths": ["intermediate/reviewed-bundles/chunk-0001.json"],
            },
        },
        agent_ledger=[
            {
                "run_id": "stage1-template-requirements",
                "agent_role": "模板需求分析",
                "status": "completed",
                "output_paths": ["requirements/template-requirements.json"],
                "write_scope": ["requirements/template-requirements.json"],
            },
            {
                "run_id": "stage1-graph-extraction",
                "agent_role": "图抽取",
                "status": "completed",
                "output_paths": [lane_output_path],
                "write_scope": [lane_output_path],
            },
            {
                "run_id": "stage1-coverage-review",
                "agent_role": "覆盖审查",
                "status": "completed",
                "output_paths": ["coverage/review-findings.json"],
                "write_scope": ["coverage/review-findings.json"],
            },
            {
                "run_id": "stage1-quality-review",
                "agent_role": "质量审查",
                "status": "completed",
                "output_paths": [],
                "write_scope": [],
            },
        ],
    )
    task_packet = graph_dir / "intermediate" / "task-packets" / "chunk-0001" / "bad.json"
    task_packet.parent.mkdir(parents=True, exist_ok=True)
    task_packet.write_text("{bad json", encoding="utf-8")
    (graph_dir / "coverage" / "review-findings.json").write_text("{bad json", encoding="utf-8")

    result = validate_graph_dir(graph_dir)

    assert result.ok is False
    assert {
        "bad_json:coverage/review-findings.json",
        "review_findings_invalid_json",
        "bad_json:intermediate/task-packets/chunk-0001/bad.json",
        "task_packet_invalid_json",
        f"missing_lane_output:{lane_output_path}",
    }.issubset(set(result.errors))


def test_validate_graph_dir_rejects_legacy_python_semantic_metadata(tmp_path):
    from storygraph_lib.validation import validate_graph_dir

    graph_dir = tmp_path / "legacy-semantic.storygraph"
    _write_minimal_valid_graph_dir(
        graph_dir,
        graph={
            "metadata": {
                "evidence_matching_strategy": "substring",
            },
        },
    )

    result = validate_graph_dir(graph_dir)

    assert result.ok is False
    assert "legacy_semantic_metadata:substring" in result.errors


def test_validate_graph_dir_accepts_empty_agent_produced_graph_metadata(tmp_path):
    from storygraph_lib.validation import validate_graph_dir

    graph_dir = tmp_path / "empty-agent-produced.storygraph"
    _write_agent_driven_success_graph_dir(
        graph_dir,
        manifest={
            "schema_version": "storygraph.manifest.v1",
            "stage1_mode": "agent-driven",
            "stage1_agent_schema_version": "stage1-agent-driven.v1",
            "canonical_writer_version": "1.0",
        },
        agent_ledger=_agent_driven_success_ledger(),
        write_lane_output=True,
    )

    result = validate_graph_dir(graph_dir)

    assert "canonical_graph_without_agent_provenance" not in result.errors
    assert "missing_lane_outputs" not in result.errors


def test_validate_graph_dir_rejects_provenance_lane_output_path_traversal(tmp_path):
    from storygraph_lib.validation import validate_graph_dir

    traversal = "intermediate/lane-outputs/../../../outside-lane.json"
    graph_dir = tmp_path / "mini.storygraph"
    _write_agent_driven_success_graph_dir(
        graph_dir,
        manifest={
            "schema_version": "storygraph.manifest.v1",
            "stage1_mode": "agent-driven",
            "stage1_agent_schema_version": "stage1-agent-driven.v1",
            "canonical_writer_version": "1.0",
        },
        agent_ledger=_agent_driven_success_ledger(),
        write_lane_output=True,
    )
    graph_path = graph_dir / "graphify-out" / "graph.json"
    graph = json.loads(graph_path.read_text(encoding="utf-8"))
    graph["nodes"].append({"id": "node:minimal", "provenance": {"lane_output_paths": [traversal]}})
    graph_path.write_text(json.dumps(graph, ensure_ascii=False), encoding="utf-8")

    normal_lane = graph_dir / "intermediate" / "lane-outputs" / "chunk-0001" / "entities_resources" / "run-001.json"
    outside_payload = json.loads(normal_lane.read_text(encoding="utf-8"))
    outside_payload["lane_id"] = ".."
    (graph_dir.parent / "outside-lane.json").write_text(
        json.dumps(outside_payload, ensure_ascii=False),
        encoding="utf-8",
    )

    result = validate_graph_dir(graph_dir)

    assert result.ok is False
    assert (
        f"invalid_lane_output_path:path_parent_traversal_rejected:{traversal}"
        in result.errors
    )


def test_validate_graph_dir_rejects_legacy_stage_level_agent_ledger(tmp_path):
    from storygraph_lib.validation import validate_graph_dir

    graph_dir = tmp_path / "legacy-ledger.storygraph"
    _write_agent_driven_success_graph_dir(
        graph_dir,
        manifest={
            "schema_version": "storygraph.manifest.v1",
            "stage1_mode": "agent-driven",
            "stage1_agent_schema_version": "stage1-agent-driven.v1",
            "canonical_writer_version": "1.0",
        },
        agent_ledger=[
            {
                "run_id": f"stage1-{index}",
                "agent_role": role,
                "status": "completed",
                "output_paths": [],
                "write_scope": [],
            }
            for index, role in enumerate(["模板需求分析", "图抽取", "覆盖审查", "质量审查"], start=1)
        ],
        write_lane_output=False,
    )

    result = validate_graph_dir(graph_dir)

    assert result.ok is False
    assert (
        "legacy_agent_ledger_requires_rebuild" in result.errors
        or any(
            error.startswith("agent_ledger_missing_required_field")
            for error in result.errors
        )
        or "missing_lane_outputs" in result.errors
    )


def test_validate_graph_dir_rejects_manifest_without_agent_driven_schema_fields(tmp_path):
    from storygraph_lib.validation import validate_graph_dir

    graph_dir = tmp_path / "legacy-manifest.storygraph"
    _write_agent_driven_success_graph_dir(
        graph_dir,
        manifest={},
        agent_ledger=_agent_driven_success_ledger(),
        write_lane_output=True,
    )

    result = validate_graph_dir(graph_dir)

    assert result.ok is False
    assert (
        "manifest_missing_required_field:schema_version" in result.errors
        or "legacy_manifest_requires_rebuild" in result.errors
    )


def test_cli_prepare_stage1_outputs_json_and_pending_agent_tasks(capsys, novel, template_dir):
    from storygraph_lib.cli import main

    code = main(["prepare-stage1", "--source", str(novel), "--template-dir", str(template_dir)])

    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["status"] == "prepared"
    assert payload["next_action"] == "dispatch_template_requirements_agents"
    assert payload["agent_dispatch"]["dispatch_plan_path"] == (
        "intermediate/agent-dispatch-plan.json"
    )


def test_cli_ingest_template_requirements_only_requires_requirement_parts(
    capsys, novel, template_dir, graph_dir
):
    from storygraph_lib.cli import main

    prepare_code = main(
        [
            "prepare-stage1",
            "--source",
            str(novel),
            "--template-dir",
            str(template_dir),
            "--graph-dir",
            str(graph_dir),
        ]
    )
    assert prepare_code == 0
    capsys.readouterr()

    packets = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(
            (graph_dir / "intermediate" / "task-packets" / "template-requirements").glob(
                "batch-*.json"
            )
        )
    ]
    for packet in packets:
        part_path = graph_dir / Path(*packet["output_path"].split("/"))
        part_path.parent.mkdir(parents=True, exist_ok=True)
        part_path.write_text(
            json.dumps(
                {
                    "templates": [
                        {
                            "template_name": item["template_name"],
                            "template_file": item["template_file"],
                            "required_fields": ["字段"],
                            "required_tables": [],
                            "required_cards": [],
                            "required_case_patterns": [],
                            "required_evidence_fields": ["原文位置"],
                            "graph_node_mapping": ["node"],
                            "graph_event_mapping": ["event"],
                            "graph_relation_mapping": ["relation"],
                            "coverage_rules": {
                                "requirement_statuses": [
                                    "covered",
                                    "needs_review",
                                    "not_found_in_source",
                                ]
                            },
                        }
                        for item in packet["template_inventory"]
                    ]
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )

    code = main(["ingest-template-requirements", "--graph-dir", str(graph_dir)])

    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["status"] == "requirements_ingested"
    assert (graph_dir / "requirements" / "template-requirements.json").exists()
    assert not (graph_dir / "intermediate" / "merge-queue.json").exists()


def test_cli_next_agent_batches_returns_limited_pending_batches(
    capsys, novel, template_dir, graph_dir
):
    from storygraph_lib.cli import main

    prepare_code = main(
        [
            "prepare-stage1",
            "--source",
            str(novel),
            "--template-dir",
            str(template_dir),
            "--graph-dir",
            str(graph_dir),
        ]
    )
    assert prepare_code == 0
    capsys.readouterr()

    code = main(
        [
            "next-agent-batches",
            "--graph-dir",
            str(graph_dir),
            "--phase",
            "lane_extraction",
            "--limit",
            "1",
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["status"] == "pending_agent_batches"
    assert payload["phase"] == "lane_extraction"
    assert payload["returned_count"] == 1
    assert payload["batches"][0]["expected_output_paths"]


def test_cli_inspect_dispatch_reports_phase_batch_counts(
    capsys, novel, template_dir, graph_dir
):
    from storygraph_lib.cli import main

    prepare_code = main(
        [
            "prepare-stage1",
            "--source",
            str(novel),
            "--template-dir",
            str(template_dir),
            "--graph-dir",
            str(graph_dir),
        ]
    )
    assert prepare_code == 0
    capsys.readouterr()

    code = main(["inspect-dispatch", "--graph-dir", str(graph_dir)])

    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["status"] == "dispatch_ready"
    assert payload["dispatch_plan_path"] == "intermediate/agent-dispatch-plan.json"
    assert payload["phases"][0]["phase"] == "template_requirements"
    assert "execution_batch_count" in payload["phases"][1]


def test_cli_argument_errors_are_json(capsys):
    from storygraph_lib.cli import main

    assert main(["prepare-stage1", "--template-dir", "x"]) == 2
    captured = capsys.readouterr()
    payload_text = captured.out or captured.err
    payload = json.loads(payload_text)

    assert payload["ok"] is False
    assert payload["error"] == "cli_argument_error"
    assert "--source" in payload["missing"]


@pytest.mark.parametrize(
    ("scenario", "raw_bytes", "expected_code"),
    [
        ("bad_json", b"{not-json", "external_json_invalid"),
        ("bad_utf8", b"\xff\xfe\x00", "external_json_utf8_decode_error"),
        ("json_shape_not_object", b"[1, 2, 3]", "external_json_shape_not_object"),
        ("missing_required_field", b"{}", "external_json_missing_required_field:version"),
        ("field_type_error", b"{\"version\": 1}", "external_json_field_type_error:version"),
    ],
)
def test_external_json_boundary_bad_inputs_are_structured_failures(
    tmp_path, scenario, raw_bytes, expected_code
):
    from storygraph_lib.validation import validate_external_json_artifact

    path = tmp_path / f"{scenario}.json"
    path.write_bytes(raw_bytes)

    result = validate_external_json_artifact(
        path,
        artifact_name="external_json",
        required_fields={"version": str},
        max_depth=32,
    )

    assert result.ok is False
    assert expected_code in result.errors


def test_deep_json_recursion_or_too_deep_is_structured_failure(tmp_path):
    from storygraph_lib.validation import validate_external_json_artifact

    payload = current = {}
    for _ in range(80):
        current["child"] = {}
        current = current["child"]
    path = tmp_path / "deep.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    result = validate_external_json_artifact(
        path,
        artifact_name="subagent_payload",
        max_depth=32,
    )

    assert result.ok is False
    assert "subagent_payload_too_deep" in result.errors


@pytest.mark.parametrize(
    ("scenario", "raw_path", "expected_code"),
    [
        ("windows_path_semantics", r"C:\tmp\outside.json", "path_absolute_rejected"),
        ("embedded_nul", "chunk-0001\x00.json", "path_embedded_nul"),
        ("absolute_path_rejected_where_needed", "/tmp/outside.json", "path_absolute_rejected"),
        ("parent_traversal_rejected", "../outside.json", "path_parent_traversal_rejected"),
    ],
)
def test_path_string_boundary_errors_are_structured(tmp_path, scenario, raw_path, expected_code):
    from storygraph_lib.paths import validate_relative_artifact_path

    result = validate_relative_artifact_path(
        raw_path,
        base_dir=tmp_path / "mini_novel.storygraph",
    )

    assert result.ok is False
    assert expected_code in result.errors


def test_subprocess_output_decode_error_is_structured():
    from storygraph_lib.graphify_adapter import decode_graphify_output

    result = decode_graphify_output(
        stdout=b"\xff\xfe",
        stderr=b"",
        failure_policy="degrade-visualization-and-query",
    )

    assert result.ok is False
    assert "subprocess_output_decode_error" in result.errors
    assert result.status == "degraded"


def test_ingest_stage1_bad_subagent_json_does_not_leak_parser_exception(
    capsys, tmp_path
):
    from storygraph_lib.cli import main

    graph_dir = tmp_path / "mini.storygraph"
    (graph_dir / "requirements").mkdir(parents=True)
    (graph_dir / "requirements" / "template-requirements.json").write_text(
        "{bad json", encoding="utf-8"
    )

    assert main(["ingest-stage1", "--graph-dir", str(graph_dir)]) == 2
    output = capsys.readouterr().out
    payload = json.loads(output)

    assert payload["error"]["code"] in {
        "subagent_payload_invalid_json",
        "template_requirements_invalid_json",
    }
    assert "message" not in payload["error"]
    assert "Expecting property name" not in output


def test_corrupt_legacy_cache_returns_rebuild_or_structured_failure(tmp_path):
    from storygraph_lib.validation import validate_graph_dir

    graph_dir = tmp_path / "mini_novel.storygraph"
    (graph_dir / "coverage").mkdir(parents=True)
    (graph_dir / "coverage" / "template-readiness.json").write_bytes(b"{bad-json")

    result = validate_graph_dir(graph_dir)

    assert result.ok is False
    assert (
        "corrupt_legacy_cache_rebuild_required" in result.errors
        or "coverage_invalid_json" in result.errors
    )


def _write_minimal_valid_graph_dir(
    graph_dir,
    *,
    manifest=None,
    graph=None,
    requirements=None,
    chunks=None,
    coverage_evidence=None,
    readiness=None,
    agent_ledger=None,
):
    (graph_dir / "graphify-out").mkdir(parents=True)
    (graph_dir / "requirements").mkdir()
    (graph_dir / "coverage").mkdir()
    default_manifest = {
        "source_size": len("法宝"),
        "stage_status": {"stage1": "success"},
    }
    if manifest is not None:
        default_manifest.update(manifest)
    base_graph = {
        "schema_version": "1.0",
        "graphify_schema_version": "test",
        "storygraph_schema_version": "1.0",
        "nodes": [],
        "edges": [],
        "hyperedges": [],
        "events": [],
        "evidence_index": [],
        "metadata": {},
    }
    if graph is not None:
        base_graph.update(graph)
    default_requirements = {
        "template_count": 1,
        "templates": [{"template_name": "法宝分析", "required_fields": ["法宝"]}],
    }
    if requirements is not None:
        default_requirements = requirements
    default_readiness = [
        {
            "template_name": "法宝分析",
            "requirement_statuses": [
                {"requirement_id": "法宝分析.required_fields.法宝", "status": "covered"}
            ],
        }
    ]
    if readiness is not None:
        default_readiness = readiness
    default_chunks = [
        {
            "chunk_id": "chunk-0001",
            "source_range": [0, len("法宝")],
            "extraction_status": "completed",
        }
    ]
    if chunks is not None:
        default_chunks = chunks
    default_agent_ledger = [
        {
            "run_id": f"stage1-{index}",
            "agent_role": role,
            "status": "completed",
            "output_paths": [],
            "write_scope": [],
        }
        for index, role in enumerate(["模板需求分析", "图抽取", "覆盖审查", "质量审查"], start=1)
    ]
    if agent_ledger is not None:
        default_agent_ledger = agent_ledger
    _write_minimal_merge_queue(graph_dir)
    (graph_dir / "manifest.json").write_text(json.dumps(default_manifest), encoding="utf-8")
    (graph_dir / "graphify-out" / "graph.json").write_text(
        json.dumps(base_graph), encoding="utf-8"
    )
    (graph_dir / "graphify-out" / "GRAPH_REPORT.md").write_text("# report\n", encoding="utf-8")
    (graph_dir / "graphify-out" / "graph.html").write_text(
        "<!doctype html>", encoding="utf-8"
    )
    (graph_dir / "requirements" / "template-requirements.json").write_text(
        json.dumps(default_requirements), encoding="utf-8"
    )
    (graph_dir / "coverage" / "chunk-ledger.json").write_text(
        json.dumps(default_chunks), encoding="utf-8"
    )
    (graph_dir / "coverage" / "evidence-index.json").write_text(
        json.dumps(coverage_evidence or []), encoding="utf-8"
    )
    (graph_dir / "coverage" / "template-readiness.json").write_text(
        json.dumps(default_readiness), encoding="utf-8"
    )
    (graph_dir / "coverage" / "agent-run-ledger.json").write_text(
        json.dumps(default_agent_ledger), encoding="utf-8"
    )
    (graph_dir / "coverage" / "gap-report.md").write_text("", encoding="utf-8")


def _write_minimal_merge_queue(graph_dir):
    queue_path = graph_dir / "intermediate" / "merge-queue.json"
    queue_path.parent.mkdir(parents=True, exist_ok=True)
    queue_path.write_text(
        json.dumps(
            {
                "status": "ready",
                "bundle_paths": ["intermediate/reviewed-bundles/chunk-0001.json"],
                "required_lane_ids": ["entities_resources"],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def _write_agent_driven_success_graph_dir(
    graph_dir,
    *,
    manifest,
    agent_ledger,
    write_lane_output,
):
    lane_output_path = "intermediate/lane-outputs/chunk-0001/entities_resources/run-001.json"
    default_manifest = {
        "source_size": len("法宝"),
        "stage_status": {"stage1": "success", "stage2": "not_requested"},
    }
    default_manifest.update(manifest)
    graph = {
        "schema_version": "1.0",
        "graphify_schema_version": "test",
        "storygraph_schema_version": "1.0",
        "nodes": [],
        "edges": [],
        "hyperedges": [],
        "events": [],
        "evidence_index": [],
        "metadata": {
            "semantic_generation": "agent-produced",
            "canonical_writer_version": "stage1-agent-driven.v1",
            "source_bundle_paths": ["intermediate/reviewed-bundles/chunk-0001.json"],
        },
    }
    task_packet = {
        "task_packet_id": "chunk-0001:entities_resources",
        "stage": "stage1",
        "chunk_id": "chunk-0001",
        "lane_id": "entities_resources",
        "agent_role": "图抽取",
        "source_path": "source.txt",
        "source_range": [0, len("法宝")],
        "allowed_output_schema": "lane-output.v1",
        "relevant_template_requirements": {},
        "lane_contract": {},
    }
    lane_output = {
        "run_id": "chunk-0001:entities_resources:run-001",
        "task_packet_id": "chunk-0001:entities_resources",
        "chunk_id": "chunk-0001",
        "lane_id": "entities_resources",
        "agent_role": "图抽取",
        "model_or_agent_identity": "agent-driven-test",
        "output_status": "completed",
        "produced_at": "2026-06-21T00:00:00Z",
        "extracted_nodes": [],
        "extracted_edges": [],
        "extracted_events": [],
        "extracted_evidence": [],
        "supports_templates": [],
        "uncertainties": [],
        "rejected_candidates": [],
        "structured_failures": [],
    }

    (graph_dir / "graphify-out").mkdir(parents=True)
    (graph_dir / "requirements").mkdir()
    (graph_dir / "coverage").mkdir()
    _write_minimal_merge_queue(graph_dir)
    (graph_dir / "manifest.json").write_text(json.dumps(default_manifest), encoding="utf-8")
    (graph_dir / "graphify-out" / "graph.json").write_text(json.dumps(graph), encoding="utf-8")
    (graph_dir / "graphify-out" / "GRAPH_REPORT.md").write_text("# report\n", encoding="utf-8")
    (graph_dir / "graphify-out" / "graph.html").write_text("<!doctype html>", encoding="utf-8")
    (graph_dir / "requirements" / "template-requirements.json").write_text(
        json.dumps(
            {
                "template_count": 1,
                "templates": [{"template_name": "法宝分析", "required_fields": ["法宝"]}],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (graph_dir / "coverage" / "chunk-ledger.json").write_text(
        json.dumps(
            [
                {
                    "chunk_id": "chunk-0001",
                    "source_range": [0, len("法宝")],
                    "extraction_status": "completed",
                }
            ]
        ),
        encoding="utf-8",
    )
    (graph_dir / "coverage" / "evidence-index.json").write_text("[]", encoding="utf-8")
    (graph_dir / "coverage" / "template-readiness.json").write_text(
        json.dumps(
            [
                {
                    "template_name": "法宝分析",
                    "requirement_statuses": [
                        {"requirement_id": "法宝分析.required_fields.法宝", "status": "covered"}
                    ],
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (graph_dir / "coverage" / "agent-run-ledger.json").write_text(
        json.dumps(agent_ledger, ensure_ascii=False),
        encoding="utf-8",
    )
    (graph_dir / "coverage" / "gap-report.md").write_text("", encoding="utf-8")
    (graph_dir / "coverage" / "review-findings.json").write_text("[]", encoding="utf-8")
    (graph_dir / "coverage" / "quality-review.json").write_text("[]", encoding="utf-8")
    task_packet_path = graph_dir / "intermediate" / "task-packets" / "chunk-0001" / "entities_resources.json"
    task_packet_path.parent.mkdir(parents=True, exist_ok=True)
    task_packet_path.write_text(json.dumps(task_packet, ensure_ascii=False), encoding="utf-8")
    if write_lane_output:
        output_path = graph_dir / Path(*lane_output_path.split("/"))
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(lane_output), encoding="utf-8")


def _agent_driven_success_ledger():
    lane_output_path = "intermediate/lane-outputs/chunk-0001/entities_resources/run-001.json"
    task_packet_path = "intermediate/task-packets/chunk-0001/entities_resources.json"
    return [
        {
            "run_id": "stage1-template-requirements",
            "stage": "stage1",
            "chunk_id": "chunk-0001",
            "lane_id": "requirements",
            "agent_role": "模板需求分析",
            "prompt_or_input_packet": task_packet_path,
            "status": "completed",
            "output_paths": ["requirements/template-requirements.json"],
            "write_scope": ["requirements/template-requirements.json"],
        },
        {
            "run_id": "chunk-0001:entities_resources:run-001",
            "stage": "stage1",
            "chunk_id": "chunk-0001",
            "lane_id": "entities_resources",
            "agent_role": "图抽取",
            "prompt_or_input_packet": task_packet_path,
            "status": "completed",
            "output_paths": [lane_output_path],
            "write_scope": [lane_output_path],
        },
        {
            "run_id": "stage1-coverage-review",
            "stage": "stage1",
            "chunk_id": "chunk-0001",
            "lane_id": "coverage_review",
            "agent_role": "覆盖审查",
            "prompt_or_input_packet": lane_output_path,
            "status": "completed",
            "output_paths": ["coverage/review-findings.json"],
            "write_scope": ["coverage/review-findings.json"],
        },
        {
            "run_id": "stage1-quality-review",
            "stage": "stage1",
            "chunk_id": "chunk-0001",
            "lane_id": "quality_review",
            "agent_role": "质量审查",
            "prompt_or_input_packet": "coverage/review-findings.json",
            "status": "completed",
            "output_paths": ["coverage/quality-review.json"],
            "write_scope": ["coverage/quality-review.json"],
        },
    ]


def test_build_stage1_cli_rejects_missing_explicit_local_override_before_running_build(
    capsys, tmp_path
):
    from storygraph_lib.cli import main

    source = tmp_path / "mini.txt"
    source.write_text("法宝", encoding="utf-8")
    template_dir = tmp_path / "templates"
    template_dir.mkdir()
    missing = tmp_path / "storygraph.local.json"

    assert (
        main(
            [
                "build-stage1",
                "--source",
                str(source),
                "--template-dir",
                str(template_dir),
                "--local-override",
                str(missing),
            ]
        )
        == 2
    )
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert payload["error"] == "local_override_missing"
