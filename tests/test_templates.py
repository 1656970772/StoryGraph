import json
import os
from pathlib import Path

import pytest

from storygraph_lib.templates import discover_templates, build_requirement_matrix


def test_discover_templates_uses_existing_files_and_warns_missing_readme_items(tmp_path):
    template_dir = tmp_path / "templates"
    template_dir.mkdir()
    (template_dir / "有限视角与叙事日志模板.md").write_text(
        "# 有限视角与叙事日志模板\n## 字段\n- 视角持有者", encoding="utf-8"
    )
    (template_dir / "角色AI行为参考模板.md").write_text(
        "# 角色AI行为参考模板\n## 字段\n- 角色目标", encoding="utf-8"
    )
    (template_dir / "README.md").write_text("- 有限视角与叙事日志模板.md\n- 缺失模板.md", encoding="utf-8")
    result = discover_templates(template_dir, glob="*模板.md", readme_index_file="README.md")
    assert [t.name for t in result.templates] == ["有限视角与叙事日志", "角色AI行为参考"]
    assert result.warnings == [{"code": "missing_template_file", "file": "缺失模板.md"}]


def test_build_requirement_matrix_uses_configured_non_generic_mappings(tmp_path):
    template_dir = tmp_path / "templates"
    template_dir.mkdir()
    (template_dir / "法宝分析模板.md").write_text(
        "# 法宝分析模板\n## 字段\n- 法宝\n## 证据要求\n- 原文位置", encoding="utf-8"
    )
    discovery = discover_templates(template_dir, glob="*模板.md", readme_index_file="README.md")
    mappings = {
        "法宝分析": {
            "graph_node_mapping": ["artifact"],
            "graph_event_mapping": ["artifact_transfer"],
            "graph_relation_mapping": ["owner_artifact"],
        },
        "default_mapping": {
            "graph_node_mapping": ["template_specific_node"],
            "graph_event_mapping": ["template_specific_event"],
            "graph_relation_mapping": ["template_specific_relation"],
        },
    }
    matrix = build_requirement_matrix(discovery.templates, rules=None, mappings=mappings)
    record = matrix["templates"][0]
    expected_contract_fields = {
        "template_file",
        "template_file_hash",
        "template_status",
        "required_sections",
        "required_entity_types",
        "required_event_types",
        "required_relation_types",
        "output_sections",
        "coverage_rules",
    }
    assert expected_contract_fields <= set(record)
    assert record["template_file"] == "法宝分析模板.md"
    assert record["template_file_hash"] == record["file_hash"]
    assert record["template_status"] == "parsed"
    assert record["required_entity_types"] == ["artifact"]
    assert record["required_event_types"] == ["artifact_transfer"]
    assert record["required_relation_types"] == ["owner_artifact"]
    assert "fields" in record["required_sections"]
    assert "evidence" in record["required_sections"]
    assert "requirement_matrix" in record["output_sections"]
    assert record["coverage_rules"]["required_evidence_fields"] == ["原文位置"]
    assert record["graph_node_mapping"] == ["artifact"]
    assert record["mapping_source"] == "configured"
    assert record["required_card_headings"] == []
    assert record["required_card_fields"] == []


def test_build_requirement_matrix_derives_non_generic_mapping_from_template_parse_result(tmp_path):
    template_dir = tmp_path / "templates"
    template_dir.mkdir()
    (template_dir / "丹药谱系模板.md").write_text(
        "# 丹药谱系模板\n## 字段\n- 丹药\n## 案例\n- 筑基丹", encoding="utf-8"
    )
    discovery = discover_templates(template_dir, glob="*模板.md", readme_index_file="README.md")
    matrix = build_requirement_matrix(
        discovery.templates,
        rules=None,
        mappings={
            "default_mapping": {
                "graph_node_mapping": ["template_specific_node"],
                "graph_event_mapping": ["template_specific_event"],
                "graph_relation_mapping": ["template_specific_relation"],
            }
        },
    )
    record = matrix["templates"][0]
    assert record["mapping_source"] == "template_parse_result"
    assert record["graph_node_mapping"] == ["丹药谱系.node"]
    assert record["graph_event_mapping"] == ["丹药谱系.event"]
    assert record["graph_relation_mapping"] == ["丹药谱系.relation"]


def test_inspect_templates_cli_outputs_json_matrix(capsys, tmp_path):
    from storygraph_lib.cli import main

    template_dir = tmp_path / "templates"
    template_dir.mkdir()
    (template_dir / "测试模板.md").write_text("# 测试模板\n## 字段\n- 条目", encoding="utf-8")
    local = tmp_path / "storygraph.local.json"
    local.write_text(
        json.dumps(
            {
                "template_count_policy": {
                    "expected_existing_templates": 1,
                    "enforce_integration_count": True,
                }
            }
        ),
        encoding="utf-8",
    )

    assert main(["inspect-templates", "--template-dir", str(template_dir), "--local-override", str(local)]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["template_count"] == 1
    assert payload["expected_template_count"] == 1
    assert payload["count_matches_expected"] is True
    assert payload["warnings"] == []
    assert payload["has_default_mapping"] is False
    assert payload["templates"][0]["mapping_source"] == "template_parse_result"


def test_inspect_templates_cli_returns_2_when_37_templates_use_default_mapping(capsys, tmp_path):
    from storygraph_lib.cli import main

    template_dir = tmp_path / "templates"
    template_dir.mkdir()
    for index in range(37):
        (template_dir / f"空白{index:02d}模板.md").write_text("# 空白模板\n", encoding="utf-8")

    assert main(["inspect-templates", "--template-dir", str(template_dir)]) == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["template_count"] == 37
    assert payload["has_default_mapping"] is True


def test_inspect_templates_cli_rejects_missing_template_dir(capsys, tmp_path):
    from storygraph_lib.cli import main

    missing = tmp_path / "missing-templates"

    assert main(["inspect-templates", "--template-dir", str(missing)]) == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert payload["error"] == "template_dir_missing"
    assert payload["path"] == str(missing)


def test_inspect_templates_cli_rejects_missing_local_override(capsys, tmp_path):
    from storygraph_lib.cli import main

    template_dir = tmp_path / "templates"
    template_dir.mkdir()
    missing = tmp_path / "storygraph.local.json"

    assert main(
        ["inspect-templates", "--template-dir", str(template_dir), "--local-override", str(missing)]
    ) == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["ok"] is False
    assert payload["error"] == "local_override_missing"
    assert payload["path"] == str(missing)


def test_inspect_templates_cli_uses_configured_expected_count_instead_of_hardcoded_37(capsys, tmp_path):
    from storygraph_lib.cli import main

    template_dir = tmp_path / "templates"
    template_dir.mkdir()
    for index in range(2):
        (template_dir / f"空白{index:02d}模板.md").write_text("# 空白模板\n", encoding="utf-8")
    local = tmp_path / "storygraph.local.json"
    local.write_text(
        json.dumps(
            {
                "template_count_policy": {
                    "expected_existing_templates": 2,
                    "enforce_integration_count": True,
                }
            }
        ),
        encoding="utf-8",
    )

    assert main(["inspect-templates", "--template-dir", str(template_dir), "--local-override", str(local)]) == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["template_count"] == 2
    assert payload["expected_template_count"] == 2
    assert payload["has_default_mapping"] is True


def test_inspect_templates_cli_local_override_mapping_can_satisfy_expected_count_guard(capsys, tmp_path):
    from storygraph_lib.cli import main

    template_dir = tmp_path / "templates"
    template_dir.mkdir()
    for index in range(2):
        (template_dir / f"空白{index:02d}模板.md").write_text("# 空白模板\n", encoding="utf-8")
    local = tmp_path / "storygraph.local.json"
    local.write_text(
        json.dumps(
            {
                "template_count_policy": {
                    "expected_existing_templates": 2,
                    "enforce_integration_count": True,
                },
                "template_graph_mappings": {
                    "空白00": {
                        "graph_node_mapping": ["blank_node"],
                        "graph_event_mapping": ["blank_event"],
                        "graph_relation_mapping": ["blank_relation"],
                    },
                    "空白01": {
                        "graph_node_mapping": ["blank_node"],
                        "graph_event_mapping": ["blank_event"],
                        "graph_relation_mapping": ["blank_relation"],
                    },
                },
            }
        ),
        encoding="utf-8",
    )

    assert main(["inspect-templates", "--template-dir", str(template_dir), "--local-override", str(local)]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["template_count"] == 2
    assert payload["expected_template_count"] == 2
    assert payload["has_default_mapping"] is False


def test_inspect_templates_cli_rejects_configured_expected_count_mismatch(capsys, tmp_path):
    from storygraph_lib.cli import main

    template_dir = tmp_path / "templates"
    template_dir.mkdir()
    (template_dir / "空白00模板.md").write_text("# 空白模板\n", encoding="utf-8")
    local = tmp_path / "storygraph.local.json"
    local.write_text(
        json.dumps(
            {
                "template_count_policy": {
                    "expected_existing_templates": 2,
                    "enforce_integration_count": True,
                },
                "template_graph_mappings": {
                    "空白00": {
                        "graph_node_mapping": ["blank_node"],
                        "graph_event_mapping": ["blank_event"],
                        "graph_relation_mapping": ["blank_relation"],
                    }
                },
            }
        ),
        encoding="utf-8",
    )

    assert main(["inspect-templates", "--template-dir", str(template_dir), "--local-override", str(local)]) == 2
    payload = json.loads(capsys.readouterr().out)
    assert payload["expected_template_count"] == 2
    assert payload["template_count"] == 1
    assert payload["count_matches_expected"] is False
    assert payload["error"] == "template_count_mismatch"


def test_inspect_templates_cli_applies_discovery_exclude_files_and_readme_policy(capsys, tmp_path):
    from storygraph_lib.cli import main

    template_dir = tmp_path / "templates"
    template_dir.mkdir()
    (template_dir / "保留模板.md").write_text("# 保留模板\n## 字段\n- 条目", encoding="utf-8")
    (template_dir / "忽略模板.md").write_text("# 忽略模板\n", encoding="utf-8")
    (template_dir / "README.md").write_text("- 保留模板.md\n- 缺失模板.md\n", encoding="utf-8")
    local = tmp_path / "storygraph.local.json"
    local.write_text(
        json.dumps(
            {
                "template_discovery": {
                    "exclude_files": ["忽略模板.md"],
                    "readme_missing_policy": "ignore",
                },
                "template_count_policy": {
                    "expected_existing_templates": 1,
                    "enforce_integration_count": True,
                }
            }
        ),
        encoding="utf-8",
    )

    assert main(["inspect-templates", "--template-dir", str(template_dir), "--local-override", str(local)]) == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["template_count"] == 1
    assert payload["count_matches_expected"] is True
    assert payload["warnings"] == []
    assert [record["template_file"] for record in payload["templates"]] == ["保留模板.md"]


def test_real_37_templates_matrix_is_optional_integration_not_hermetic_pytest():
    template_root = os.environ.get("STORYGRAPH_REAL_TEMPLATE_DIR")
    if not template_root:
        pytest.skip("Set STORYGRAPH_REAL_TEMPLATE_DIR for local integration verification.")
    mappings_json = os.environ.get("STORYGRAPH_TEMPLATE_MAPPINGS_JSON")
    if not mappings_json:
        pytest.skip("Set STORYGRAPH_TEMPLATE_MAPPINGS_JSON so the integration test does not hard-code mappings.")
    template_dir = Path(template_root)
    discovery = discover_templates(template_dir, glob="*模板.md", readme_index_file="README.md")
    matrix = build_requirement_matrix(discovery.templates, rules=None, mappings=json.loads(mappings_json))
    assert matrix["template_count"] == 37
    for record in matrix["templates"]:
        assert (
            record["required_fields"]
            or record["required_tables"]
            or record["required_cards"]
            or record["required_case_patterns"]
        )
        assert record["required_evidence_fields"]
        assert record["gap_rules"]["status_enum"] == ["covered", "needs_review", "not_found_in_source"]
        assert record["graph_node_mapping"]
        assert record["graph_event_mapping"]
        assert record["graph_relation_mapping"]
        assert record["mapping_source"] in {"configured", "template_parse_result"}
