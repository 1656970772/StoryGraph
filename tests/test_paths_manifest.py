import json

from storygraph_lib.manifest import write_manifest
from storygraph_lib.paths import resolve_novel_context


def test_resolve_novel_context_creates_independent_graph_dir(tmp_path):
    novel = tmp_path / "凡人修仙传.txt"
    novel.write_text("第一章 开端\n韩立进山。", encoding="utf-8")

    ctx = resolve_novel_context(novel, graph_dir_suffix=".storygraph", create=True)

    assert ctx.novel_name == "凡人修仙传"
    assert ctx.graph_dir == tmp_path / "凡人修仙传.storygraph"
    assert ctx.graph_dir.exists()


def test_manifest_records_source_hash_and_stage_status(tmp_path):
    novel = tmp_path / "mini.txt"
    novel.write_text("正文", encoding="utf-8")
    ctx = resolve_novel_context(novel, ".storygraph", create=True)

    manifest = write_manifest(ctx, config_hash="cfg", graphify_source="local")

    data = json.loads(manifest.read_text(encoding="utf-8"))
    assert data["source_path"] == str(novel)
    assert data["stage_status"]["stage1"] == "initialized"
