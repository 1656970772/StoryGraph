from pathlib import Path

import pytest

from storygraph_lib.stage2_schema import resolve_render_target


POLICY = {
    "default_dir": "drafts",
    "allowed_policies": ["draft", "backup-and-overwrite", "merge"],
    "draft_action": "write_draft",
    "existing_document_action": "write_versioned_draft",
}


def test_default_policy_writes_draft_and_does_not_overwrite_existing_formal_doc(tmp_path):
    graph_dir = tmp_path / "凡人修仙传.storygraph"
    novel_dir = tmp_path
    graph_dir.mkdir()
    formal = novel_dir / "法宝分析.md"
    formal.write_text("用户已有文档", encoding="utf-8")

    decision = resolve_render_target(
        graph_dir,
        novel_dir,
        "法宝分析",
        POLICY,
        overwrite_policy="draft",
    )

    assert decision["target_path"] == str(graph_dir / "drafts" / "法宝分析.md")
    assert decision["formal_target_path"] == str(formal)
    assert decision["action"] == "write_draft"
    assert decision["will_overwrite"] is False
    assert formal.read_text(encoding="utf-8") == "用户已有文档"


def test_formal_target_can_only_be_used_by_backup_overwrite_or_merge_policy(tmp_path):
    graph_dir = tmp_path / "凡人修仙传.storygraph"
    novel_dir = tmp_path
    graph_dir.mkdir()
    formal = novel_dir / "法宝分析.md"
    formal.write_text("用户已有文档", encoding="utf-8")

    backup = resolve_render_target(
        graph_dir,
        novel_dir,
        "法宝分析",
        POLICY,
        overwrite_policy="backup-and-overwrite",
    )
    merge = resolve_render_target(
        graph_dir,
        novel_dir,
        "法宝分析",
        POLICY,
        overwrite_policy="merge",
    )

    assert backup["target_path"] == str(formal)
    assert backup["backup_path"].endswith("法宝分析.md.bak")
    assert backup["action"] == "backup_and_overwrite"
    assert backup["will_overwrite"] is True
    assert merge["target_path"] == str(formal)
    assert merge["action"] == "merge_existing"
    assert merge["will_overwrite"] is True


def test_backup_path_is_stable_when_formal_document_does_not_exist(tmp_path):
    graph_dir = tmp_path / "凡人修仙传.storygraph"
    novel_dir = tmp_path
    graph_dir.mkdir()

    decision = resolve_render_target(
        graph_dir,
        novel_dir,
        "法宝分析",
        POLICY,
        overwrite_policy="backup-and-overwrite",
    )

    assert decision["target_path"] == str(novel_dir / "法宝分析.md")
    assert decision["backup_path"] == str(novel_dir / "法宝分析.md.bak")
    assert decision["action"] == "write_new_formal"
    assert decision["will_overwrite"] is False


def test_unsupported_output_policy_raises_value_error(tmp_path):
    graph_dir = tmp_path / "凡人修仙传.storygraph"
    novel_dir = tmp_path
    graph_dir.mkdir()

    with pytest.raises(ValueError, match="unsupported overwrite_policy"):
        resolve_render_target(graph_dir, novel_dir, "法宝分析", POLICY, overwrite_policy="replace")


@pytest.mark.parametrize("default_dir", ["C:relative", "drafts:ads"])
def test_stage2_default_dir_rejects_windows_drive_relative_and_colon(tmp_path, default_dir):
    graph_dir = tmp_path / "book.storygraph"
    novel_dir = tmp_path / "novel"
    graph_dir.mkdir()
    novel_dir.mkdir()
    policy = {
        "default_dir": default_dir,
        "allowed_policies": ["draft", "backup-and-overwrite", "merge"],
        "draft_action": "write_draft",
    }

    with pytest.raises(ValueError, match="unsafe output_policy.default_dir"):
        resolve_render_target(graph_dir, novel_dir, "法宝分析", policy)


@pytest.mark.parametrize(
    "template_name",
    [
        "../越界",
        "nested/name",
        "nested\\name",
        "/absolute",
        "C:/absolute",
        "bad\x00name",
        "",
    ],
)
def test_template_name_cannot_escape_graph_or_novel_directories(tmp_path, template_name):
    graph_dir = tmp_path / "凡人修仙传.storygraph"
    novel_dir = tmp_path / "novel"
    graph_dir.mkdir()
    novel_dir.mkdir()

    with pytest.raises(ValueError, match="unsafe template_name"):
        resolve_render_target(graph_dir, novel_dir, template_name, POLICY)


def test_draft_target_stays_inside_graph_dir_and_formal_target_stays_inside_novel_dir(tmp_path):
    graph_dir = tmp_path / "凡人修仙传.storygraph"
    novel_dir = tmp_path / "novel"
    graph_dir.mkdir()
    novel_dir.mkdir()

    draft = resolve_render_target(graph_dir, novel_dir, "法宝分析", POLICY)
    formal = resolve_render_target(
        graph_dir,
        novel_dir,
        "法宝分析",
        POLICY,
        overwrite_policy="merge",
    )

    assert Path(draft["target_path"]).is_relative_to(graph_dir)
    assert Path(formal["target_path"]).is_relative_to(novel_dir)
