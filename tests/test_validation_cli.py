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
    assert "'SKILL.md'" in result.stdout


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
    payload = ast.literal_eval(capsys.readouterr().out)
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


def test_inspect_templates_accepts_config_without_losing_count_default_mapping_guard(
    capsys, tmp_path
):
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
                    "enforce_integration_count": True,
                },
            }
        ),
        encoding="utf-8",
    )

    assert main(["inspect-templates", "--config", str(config), "--template-dir", str(template_dir)]) == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["template_count"] == 1
    assert payload["count_matches_expected"] is True
    assert payload["has_default_mapping"] is True
    assert payload["error"] == "default_mapping_used"


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
