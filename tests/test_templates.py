from pathlib import Path

import pytest

from storygraph_lib.templates import (
    TemplateDiscoveryError,
    build_requirement_matrix,
    discover_templates,
)


def test_discover_templates_uses_existing_files_and_warns_missing_readme_items(tmp_path):
    template_dir = tmp_path / "templates"
    template_dir.mkdir()
    (template_dir / "有限视角与叙事日志模板.md").write_text(
        "# 有限视角与叙事日志模板\n## 字段\n- 视角持有者", encoding="utf-8"
    )
    (template_dir / "角色AI行为参考模板.md").write_text(
        "# 角色AI行为参考模板\n## 字段\n- 角色目标", encoding="utf-8"
    )
    (template_dir / "README.md").write_text(
        "- 有限视角与叙事日志模板.md\n- 缺失模板.md", encoding="utf-8"
    )

    result = discover_templates(template_dir, glob="*模板.md", readme_index_file="README.md")

    assert [t.name for t in result.templates] == ["有限视角与叙事日志", "角色AI行为参考"]
    assert result.warnings == [{"code": "missing_template_file", "file": "缺失模板.md"}]


def test_discover_templates_remains_file_inventory_only(tmp_path):
    template_dir = tmp_path / "templates"
    template_dir.mkdir()
    (template_dir / "法宝分析模板.md").write_text(
        "# 法宝分析模板\n## 字段\n- 法宝", encoding="utf-8"
    )

    discovery = discover_templates(template_dir)

    assert discovery.templates[0].name == "法宝分析"
    assert discovery.templates[0].text.startswith("# 法宝分析模板")


def test_discover_templates_rejects_missing_template_dir(tmp_path):
    missing = tmp_path / "missing-templates"

    with pytest.raises(TemplateDiscoveryError) as exc_info:
        discover_templates(missing)

    assert exc_info.value.to_dict() == {
        "ok": False,
        "error": "template_dir_missing",
        "path": str(missing),
    }


def test_discover_templates_can_error_on_missing_readme_items(tmp_path):
    template_dir = tmp_path / "templates"
    template_dir.mkdir()
    (template_dir / "保留模板.md").write_text("# 保留模板\n", encoding="utf-8")
    (template_dir / "README.md").write_text("- 保留模板.md\n- 缺失模板.md", encoding="utf-8")

    with pytest.raises(TemplateDiscoveryError) as exc_info:
        discover_templates(template_dir, readme_missing_policy="error")

    assert exc_info.value.to_dict() == {
        "ok": False,
        "error": "missing_template_file",
        "file": "缺失模板.md",
    }


def test_build_requirement_matrix_is_structured_legacy_failure(tmp_path):
    template_dir = tmp_path / "templates"
    template_dir.mkdir()
    (template_dir / "法宝分析模板.md").write_text("# 法宝分析模板\n", encoding="utf-8")
    discovery = discover_templates(template_dir)

    with pytest.raises(ValueError) as exc_info:
        build_requirement_matrix(discovery.templates, rules=None, mappings=None)

    assert getattr(exc_info.value, "code", None) == "legacy_requirement_matrix_disabled"
