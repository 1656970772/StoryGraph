import sys
import subprocess
from pathlib import Path

from storygraph_lib.paths import NovelContext
from storygraph_lib.state import REQUIRED_STAGE1_FILES, stage1_state
from storygraph_lib.stage1 import build_stage1_graph


MANAGED_OUTPUTS = [
    "manifest.json",
    "graphify-out/graph.json",
    "graphify-out/GRAPH_REPORT.md",
    "graphify-out/graph.html",
    "requirements/template-requirements.json",
    "coverage/chunk-ledger.json",
    "coverage/evidence-index.json",
    "coverage/template-readiness.json",
    "coverage/agent-run-ledger.json",
    "coverage/gap-report.md",
]


class _ValidationOk:
    ok = True


def _write_required_stage1_files(graph_dir: Path) -> None:
    for relative in REQUIRED_STAGE1_FILES:
        path = graph_dir / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        if relative == "manifest.json":
            continue
        path.write_text("{}", encoding="utf-8")


def _write_37_templates(template_dir: Path) -> None:
    for index in range(37):
        (template_dir / f"模板{index:02d}模板.md").write_text(
            f"# 模板{index:02d}模板\n## 字段\n- 法宝\n## 证据要求\n- 原文位置",
            encoding="utf-8",
        )


def _graphify_command():
    script = (
        "import json,pathlib,sys; "
        "out=pathlib.Path(sys.argv[2]); out.mkdir(parents=True, exist_ok=True); "
        "graph={'schema_version':'1.0','graphify_schema_version':'test',"
        "'storygraph_schema_version':'1.0','nodes':[],'edges':[],'hyperedges':[],"
        "'events':[],'evidence_index':[],'metadata':{'graphify_schema_version':'test'}}; "
        "(out/'graph.json').write_text(json.dumps(graph, ensure_ascii=False), encoding='utf-8'); "
        "(out/'GRAPH_REPORT.md').write_text('# Graph Report\\n', encoding='utf-8'); "
        "(out/'graph.html').write_text('<!doctype html><title>graph</title>', encoding='utf-8')"
    )
    return [sys.executable, "-c", script, "{source}", "{output_dir}"]


def _config(template_dir: Path, graphify_repo: Path) -> dict:
    mappings = {
        f"模板{index:02d}": {
            "graph_node_mapping": [f"template_{index:02d}_node"],
            "graph_event_mapping": [f"template_{index:02d}_event"],
            "graph_relation_mapping": [f"template_{index:02d}_relation"],
        }
        for index in range(37)
    }
    mappings["default_mapping"] = {
        "graph_node_mapping": ["template_specific_node"],
        "graph_event_mapping": ["template_specific_event"],
        "graph_relation_mapping": ["template_specific_relation"],
    }
    return {
        "graph_dir_suffix": ".storygraph",
        "output_language": "zh-CN",
        "paths": {"template_dir": str(template_dir), "graphify_repo": str(graphify_repo)},
        "template_discovery": {
            "glob": "*模板.md",
            "readme_index_file": "README.md",
            "exclude_files": ["README.md"],
            "readme_missing_policy": "warn",
        },
        "template_parser_rules": None,
        "template_graph_mappings": mappings,
        "status_enums": {
            "requirement_statuses": ["covered", "needs_review", "not_found_in_source"],
            "verification_statuses": ["verified", "needs_review", "rejected"],
            "confidence_levels": ["EXTRACTED", "INFERRED", "AMBIGUOUS"],
        },
        "template_count_policy": {
            "expected_existing_templates": 37,
            "enforce_integration_count": True,
        },
        "graphify_adapter": {
            "mode": "local-repo-or-cli",
            "command": _graphify_command(),
            "timeout_seconds": 5,
        },
        "chunk_strategy": {
            "mode": "chapter-aware",
            "fallback_mode": "bounded-chars",
            "max_chars": 100,
            "overlap_chars": 0,
        },
        "evidence_matching_strategy": {"mode": "substring"},
        "coverage_thresholds": {
            "require_all_chunks_scanned": True,
            "readiness_warning_threshold": 0.8,
            "block_on_low_readiness": True,
            "block_on_template_without_reliable_evidence": True,
            "block_on_unparsable_subagent_json": True,
        },
        "agent_policy": {"sub_agent_json_payloads": []},
        "writer_policy": {"managed_outputs": MANAGED_OUTPUTS},
    }


def test_stage1_state_rebuilds_when_manifest_stage_status_shape_is_malformed(tmp_path):
    source = tmp_path / "mini.txt"
    source.write_text("法宝", encoding="utf-8")
    graph_dir = tmp_path / "mini.storygraph"
    graph_dir.mkdir()
    _write_required_stage1_files(graph_dir)
    (graph_dir / "manifest.json").write_text(
        '{"source_hash":"source-hash","config_hash":"config-hash","stage_status":[]}',
        encoding="utf-8",
    )
    ctx = NovelContext(
        source_path=source,
        source_hash="source-hash",
        source_size=source.stat().st_size,
        novel_name="mini",
        novel_dir=tmp_path,
        graph_dir=graph_dir,
    )

    result = stage1_state(ctx, "config-hash", lambda _: _ValidationOk())

    assert result["action"] == "rebuild"
    assert result["source_state"] == "changed"


def test_stage1_state_rebuilds_on_unreadable_manifest(tmp_path):
    from types import SimpleNamespace
    from storygraph_lib.state import stage1_state

    graph_dir = tmp_path / "mini.storygraph"
    graph_dir.mkdir()
    (graph_dir / "manifest.json").write_bytes(b"\xff")

    ctx = SimpleNamespace(graph_dir=graph_dir, source_hash="h")
    result = stage1_state(ctx, "cfg", lambda _: SimpleNamespace(ok=True))

    assert result["action"] == "rebuild"
    assert result["source_state"] == "changed"


def test_stage1_state_rebuilds_on_deep_manifest_json(tmp_path):
    from types import SimpleNamespace
    from storygraph_lib.state import stage1_state

    graph_dir = tmp_path / "mini.storygraph"
    graph_dir.mkdir()
    (graph_dir / "manifest.json").write_text("[" * 5000 + "]" * 5000, encoding="utf-8")

    ctx = SimpleNamespace(graph_dir=graph_dir, source_hash="h")
    result = stage1_state(ctx, "cfg", lambda _: SimpleNamespace(ok=True))

    assert result["action"] == "rebuild"
    assert result["source_state"] == "changed"


def test_stage1_state_ignores_deep_blocking_ledger_json(tmp_path):
    from types import SimpleNamespace
    from storygraph_lib.state import stage1_state

    graph_dir = tmp_path / "mini.storygraph"
    graph_dir.mkdir()
    _write_required_stage1_files(graph_dir)
    (graph_dir / "manifest.json").write_text(
        '{"source_hash":"h","config_hash":"cfg","stage_status":{"stage1":"success"}}',
        encoding="utf-8",
    )
    (graph_dir / "coverage" / "agent-run-ledger.json").write_text(
        "[" * 5000 + "]" * 5000,
        encoding="utf-8",
    )

    ctx = SimpleNamespace(graph_dir=graph_dir, source_hash="h")
    result = stage1_state(ctx, "cfg", lambda _: SimpleNamespace(ok=True))

    assert result["action"] == "reuse"
    assert result["source_state"] == "unchanged"


def test_stage1_reuses_graph_when_source_hash_is_unchanged(tmp_path):
    novel = tmp_path / "mini.txt"
    novel.write_text("法宝 小瓶", encoding="utf-8")
    template_dir = tmp_path / "templates"
    template_dir.mkdir()
    _write_37_templates(template_dir)
    graphify_repo = tmp_path / "graphify"
    graphify_repo.mkdir()
    config = _config(template_dir, graphify_repo)

    first = build_stage1_graph(novel, config)
    second = build_stage1_graph(novel, config)

    assert first["status"] == "success"
    assert second["status"] == "reused"
    assert second["source_state"] == "unchanged"


def test_stage1_marks_source_changed_when_hash_changes(tmp_path):
    novel = tmp_path / "mini.txt"
    novel.write_text("法宝", encoding="utf-8")
    template_dir = tmp_path / "templates"
    template_dir.mkdir()
    _write_37_templates(template_dir)
    graphify_repo = tmp_path / "graphify"
    graphify_repo.mkdir()
    config = _config(template_dir, graphify_repo)
    build_stage1_graph(novel, config)

    novel.write_text("法宝 小瓶", encoding="utf-8")
    result = build_stage1_graph(novel, config)

    assert result["status"] == "success"
    assert result["source_state"] == "changed"


def test_stage1_marks_changed_when_template_file_hash_changes(tmp_path):
    novel = tmp_path / "mini.txt"
    novel.write_text("法宝", encoding="utf-8")
    template_dir = tmp_path / "templates"
    template_dir.mkdir()
    _write_37_templates(template_dir)
    graphify_repo = tmp_path / "graphify"
    graphify_repo.mkdir()
    config = _config(template_dir, graphify_repo)
    build_stage1_graph(novel, config)

    (template_dir / "模板00模板.md").write_text(
        "# 模板00模板\n## 字段\n- 丹药\n## 证据要求\n- 原文位置",
        encoding="utf-8",
    )
    result = build_stage1_graph(novel, config)

    assert result["status"] == "failed"
    assert result["source_state"] == "changed"
    assert result["error"]["code"] == "readiness_below_threshold"


def test_stage1_marks_changed_when_graphify_source_changes(tmp_path):
    novel = tmp_path / "mini.txt"
    novel.write_text("法宝", encoding="utf-8")
    template_dir = tmp_path / "templates"
    template_dir.mkdir()
    _write_37_templates(template_dir)
    graphify_a = tmp_path / "graphify-a"
    graphify_a.mkdir()
    graphify_b = tmp_path / "graphify-b"
    graphify_b.mkdir()
    config = _config(template_dir, graphify_a)
    build_stage1_graph(novel, config)

    config["paths"]["graphify_repo"] = str(graphify_b)
    result = build_stage1_graph(novel, config)

    assert result["status"] == "success"
    assert result["source_state"] == "changed"


def test_stage1_marks_changed_when_graphify_git_repo_dirty_state_changes(tmp_path):
    novel = tmp_path / "mini.txt"
    novel.write_text("法宝", encoding="utf-8")
    template_dir = tmp_path / "templates"
    template_dir.mkdir()
    _write_37_templates(template_dir)
    graphify_repo = tmp_path / "graphify"
    graphify_repo.mkdir()
    subprocess.run(["git", "init"], cwd=graphify_repo, check=True, capture_output=True, text=True)
    subprocess.run(
        ["git", "config", "user.email", "storygraph@example.invalid"],
        cwd=graphify_repo,
        check=True,
        capture_output=True,
        text=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "StoryGraph Test"],
        cwd=graphify_repo,
        check=True,
        capture_output=True,
        text=True,
    )
    tracked = graphify_repo / "tool.py"
    tracked.write_text("VERSION = 1\n", encoding="utf-8")
    subprocess.run(["git", "add", "tool.py"], cwd=graphify_repo, check=True, capture_output=True, text=True)
    subprocess.run(
        ["git", "commit", "-m", "init"],
        cwd=graphify_repo,
        check=True,
        capture_output=True,
        text=True,
    )
    config = _config(template_dir, graphify_repo)
    build_stage1_graph(novel, config)

    tracked.write_text("VERSION = 2\n", encoding="utf-8")
    result = build_stage1_graph(novel, config)

    assert result["status"] == "success"
    assert result["source_state"] == "changed"


def test_stage1_marks_changed_when_graphify_non_git_repo_content_changes(tmp_path):
    novel = tmp_path / "mini.txt"
    novel.write_text("法宝", encoding="utf-8")
    template_dir = tmp_path / "templates"
    template_dir.mkdir()
    _write_37_templates(template_dir)
    graphify_repo = tmp_path / "graphify"
    graphify_repo.mkdir()
    (graphify_repo / "tool.py").write_text("VERSION = 1\n", encoding="utf-8")
    config = _config(template_dir, graphify_repo)
    build_stage1_graph(novel, config)

    (graphify_repo / "tool.py").write_text("VERSION = 2\n", encoding="utf-8")
    result = build_stage1_graph(novel, config)

    assert result["status"] == "success"
    assert result["source_state"] == "changed"
