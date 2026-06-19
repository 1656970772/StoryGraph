import json
from pathlib import Path

from storygraph_lib.manifest import write_manifest
from storygraph_lib.paths import file_sha256, resolve_novel_context


FIXTURES = Path(__file__).parent / "fixtures"


def test_resolve_novel_context_creates_independent_graph_dir(tmp_path):
    novel = tmp_path / "凡人修仙传.txt"
    novel.write_text("第一章 开端\n韩立进山。", encoding="utf-8")

    ctx = resolve_novel_context(novel, graph_dir_suffix=".storygraph", create=True)

    assert ctx.novel_name == "凡人修仙传"
    assert ctx.source_hash == file_sha256(novel)
    assert ctx.source_size == novel.stat().st_size
    assert ctx.graph_dir == tmp_path / "凡人修仙传.storygraph"
    assert ctx.graph_dir.exists()


def test_manifest_records_source_hash_and_stage_status(tmp_path):
    novel = tmp_path / "mini.txt"
    novel.write_text((FIXTURES / "mini_novel.txt").read_text(encoding="utf-8"), encoding="utf-8")
    ctx = resolve_novel_context(novel, ".storygraph", create=False)

    manifest = write_manifest(ctx, config_hash="cfg", graphify_source="local")

    data = json.loads(manifest.read_text(encoding="utf-8"))
    assert ctx.graph_dir.exists()
    assert data["source_path"] == str(novel)
    assert data["source_hash"] == file_sha256(novel)
    assert data["source_size"] == novel.stat().st_size
    assert data["config_hash"] == "cfg"
    assert data["graphify_repo"] == "local"
    assert data["graphify_version_or_commit"] is None
    assert data["created_at"]
    assert data["updated_at"]
    assert data["stage_status"]["stage1"] == "initialized"
    assert data["stage_status"]["stage2"] == "not_requested"


def test_manifest_preserves_created_at_and_stage_status_on_rewrite(tmp_path):
    novel = tmp_path / "mini.txt"
    novel.write_text("正文", encoding="utf-8")
    ctx = resolve_novel_context(novel, ".storygraph", create=True)
    manifest = write_manifest(ctx, config_hash="cfg", graphify_source="local")
    data = json.loads(manifest.read_text(encoding="utf-8"))
    data["created_at"] = "2000-01-01T00:00:00+00:00"
    data["updated_at"] = "2000-01-02T00:00:00+00:00"
    data["stage_status"] = {"stage1": "success", "stage2": "not_requested"}
    manifest.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    write_manifest(ctx, config_hash="cfg2", graphify_source="remote")

    updated = json.loads(manifest.read_text(encoding="utf-8"))
    assert updated["created_at"] == "2000-01-01T00:00:00+00:00"
    assert updated["updated_at"] != "2000-01-02T00:00:00+00:00"
    assert updated["stage_status"] == {"stage1": "success", "stage2": "not_requested"}
    assert updated["config_hash"] == "cfg2"
    assert updated["graphify_repo"] == "remote"
