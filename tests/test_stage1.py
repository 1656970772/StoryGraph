import json
import sys
from pathlib import Path

from storygraph_lib.stage1 import build_stage1_graph
from storygraph_lib.validation import validate_graph_dir


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


def _graphify_command_with(script_body: str):
    return [sys.executable, "-c", script_body, "{source}", "{output_dir}"]


def _config(template_dir: Path, graphify_repo: Path | None = None) -> dict:
    return {
        "graph_dir_suffix": ".storygraph",
        "output_language": "zh-CN",
        "paths": {
            "template_dir": str(template_dir),
            "graphify_repo": str(graphify_repo) if graphify_repo else None,
        },
        "template_discovery": {
            "glob": "*模板.md",
            "readme_index_file": "README.md",
            "exclude_files": ["README.md"],
            "readme_missing_policy": "warn",
        },
        "template_parser_rules": {
            "field_headings": ["字段"],
            "table_markers": ["|", "表格"],
            "card_markers": ["卡片"],
            "case_markers": ["案例"],
            "evidence_markers": ["证据", "原文"],
            "gap_markers": ["缺口", "待核验"],
        },
        "template_graph_mappings": {
            "法宝分析": {
                "graph_node_mapping": ["artifact"],
                "graph_event_mapping": ["artifact_gain"],
                "graph_relation_mapping": ["artifact_influence"],
            },
            "default_mapping": {
                "graph_node_mapping": ["template_specific_node"],
                "graph_event_mapping": ["template_specific_event"],
                "graph_relation_mapping": ["template_specific_relation"],
            },
        },
        "status_enums": {
            "requirement_statuses": ["covered", "needs_review", "not_found_in_source"],
            "verification_statuses": ["verified", "needs_review", "rejected"],
            "confidence_levels": ["EXTRACTED", "INFERRED", "AMBIGUOUS"],
        },
        "template_count_policy": {
            "expected_existing_templates": 1,
            "enforce_integration_count": False,
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
            "chapter_heading_patterns": ["^第.+章"],
        },
        "evidence_matching_strategy": {"mode": "substring", "case_sensitive": False},
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


def _write_template(template_dir: Path, body: str | None = None) -> None:
    template_dir.mkdir(exist_ok=True)
    (template_dir / "法宝分析模板.md").write_text(
        body or "# 法宝分析模板\n## 字段\n- 法宝\n## 法宝卡片\n- 小瓶\n## 证据要求\n- 原文位置",
        encoding="utf-8",
    )


def test_stage1_build_merges_real_template_aware_supplements(tmp_path):
    novel = tmp_path / "mini_novel.txt"
    novel.write_text("第一章\n韩立获得小瓶。法宝卡片记载小瓶影响法宝资源获取。", encoding="utf-8")
    template_dir = tmp_path / "templates"
    graphify_repo = tmp_path / "graphify"
    graphify_repo.mkdir()
    _write_template(template_dir)

    result = build_stage1_graph(novel, _config(template_dir, graphify_repo))

    graph_dir = tmp_path / "mini_novel.storygraph"
    graph = json.loads((graph_dir / "graphify-out" / "graph.json").read_text(encoding="utf-8"))
    readiness = json.loads(
        (graph_dir / "coverage" / "template-readiness.json").read_text(encoding="utf-8")
    )
    ledger = json.loads(
        (graph_dir / "coverage" / "agent-run-ledger.json").read_text(encoding="utf-8")
    )
    manifest = json.loads((graph_dir / "manifest.json").read_text(encoding="utf-8"))
    requirements = json.loads(
        (graph_dir / "requirements" / "template-requirements.json").read_text(encoding="utf-8")
    )

    assert result["status"] == "success"
    assert result["manifest_written"] is True
    assert graph["nodes"] and graph["edges"] and graph["events"] and graph["evidence_index"]
    assert readiness[0]["requirement_statuses"]
    assert {record["status"] for record in ledger} == {"completed"}
    assert manifest["stage_status"]["stage1"] == "success"
    assert requirements["templates"][0]["template_name"] == "法宝分析"
    assert validate_graph_dir(graph_dir).ok is True


def test_stage1_graphify_unavailable_is_blocking_failed(tmp_path):
    novel = tmp_path / "mini_novel.txt"
    novel.write_text("法宝", encoding="utf-8")
    template_dir = tmp_path / "templates"
    _write_template(template_dir, "# 法宝分析模板\n## 字段\n- 法宝")

    result = build_stage1_graph(novel, _config(template_dir, tmp_path / "missing-graphify"))
    second = build_stage1_graph(novel, _config(template_dir, tmp_path / "missing-graphify"))

    graph_dir = tmp_path / "mini_novel.storygraph"
    ledger = json.loads((graph_dir / "coverage" / "agent-run-ledger.json").read_text(encoding="utf-8"))
    assert result["status"] == "failed"
    assert second["status"] == "failed"
    assert not (graph_dir / "graphify-out" / "graph.json").exists()
    failed = next(record for record in ledger if record["status"] == "failed")
    assert failed["agent_role"] == "图抽取"
    assert failed["errors"][0]["code"] == "graphify_unavailable"


def test_stage1_empty_graphify_command_is_structured_failure_and_writes_outputs(tmp_path):
    novel = tmp_path / "mini_novel.txt"
    novel.write_text("法宝", encoding="utf-8")
    template_dir = tmp_path / "templates"
    _write_template(template_dir, "# 法宝分析模板\n## 字段\n- 法宝")
    config = _config(template_dir, graphify_repo=None)
    config["graphify_adapter"] = {
        "mode": "cli",
        "command": [],
        "timeout_seconds": 5,
    }

    graph_dir = tmp_path / "mini_novel.storygraph"
    stale_out = graph_dir / "graphify-out"
    stale_out.mkdir(parents=True)
    (stale_out / "graph.json").write_text("{}", encoding="utf-8")
    (stale_out / "GRAPH_REPORT.md").write_text("# stale\n", encoding="utf-8")
    (stale_out / "graph.html").write_text("<!doctype html>", encoding="utf-8")

    result = build_stage1_graph(novel, config)

    manifest = json.loads((graph_dir / "manifest.json").read_text(encoding="utf-8"))
    ledger = json.loads((graph_dir / "coverage" / "agent-run-ledger.json").read_text(encoding="utf-8"))
    gap = (graph_dir / "coverage" / "gap-report.md").read_text(encoding="utf-8")
    validation = validate_graph_dir(graph_dir)
    assert result["status"] == "failed"
    assert result["error"]["code"] == "graphify_bad_command"
    assert "graphify_bad_command" in result["validation_errors"]
    assert manifest["stage_status"]["stage1"] == "failed"
    assert any(
        error["code"] == "graphify_bad_command"
        for record in ledger
        for error in record.get("errors", [])
    )
    assert "graphify_bad_command" in gap
    assert "blocking_ledger:graphify_bad_command" in validation.errors
    assert not (graph_dir / "graphify-out" / "graph.json").exists()
    assert not (graph_dir / "graphify-out" / "GRAPH_REPORT.md").exists()
    assert not (graph_dir / "graphify-out" / "graph.html").exists()


def test_stage1_readiness_below_threshold_and_template_without_reliable_evidence_fail(tmp_path):
    novel = tmp_path / "mini_novel.txt"
    novel.write_text("完全无关正文", encoding="utf-8")
    template_dir = tmp_path / "templates"
    graphify_repo = tmp_path / "graphify"
    graphify_repo.mkdir()
    _write_template(template_dir, "# 法宝分析模板\n## 字段\n- 法宝")

    result = build_stage1_graph(novel, _config(template_dir, graphify_repo))

    graph_dir = tmp_path / "mini_novel.storygraph"
    manifest = json.loads((graph_dir / "manifest.json").read_text(encoding="utf-8"))
    gap = (graph_dir / "coverage" / "gap-report.md").read_text(encoding="utf-8")
    ledger = json.loads((graph_dir / "coverage" / "agent-run-ledger.json").read_text(encoding="utf-8"))
    assert result["status"] == "failed"
    assert manifest["stage_status"]["stage1"] == "failed"
    assert "readiness_below_threshold" in gap
    assert "template_without_reliable_evidence" in gap
    assert any(
        error["code"] == "readiness_below_threshold"
        for record in ledger
        for error in record["errors"]
    )


def test_stage1_chunk_extraction_failure_writes_failed_chunk_ledger(tmp_path, monkeypatch):
    import storygraph_lib.stage1 as stage1_mod

    novel = tmp_path / "mini_novel.txt"
    novel.write_text("法宝", encoding="utf-8")
    template_dir = tmp_path / "templates"
    graphify_repo = tmp_path / "graphify"
    graphify_repo.mkdir()
    _write_template(template_dir, "# 法宝分析模板\n## 字段\n- 法宝")

    def fail_chunks(*args, **kwargs):
        raise ValueError("chunk boom")

    monkeypatch.setattr(stage1_mod, "make_chunk_ledger", fail_chunks)

    result = build_stage1_graph(novel, _config(template_dir, graphify_repo))

    graph_dir = tmp_path / "mini_novel.storygraph"
    chunks = json.loads((graph_dir / "coverage" / "chunk-ledger.json").read_text(encoding="utf-8"))
    manifest = json.loads((graph_dir / "manifest.json").read_text(encoding="utf-8"))
    assert result["status"] == "failed"
    assert manifest["stage_status"]["stage1"] == "failed"
    assert chunks[0]["extraction_status"] == "failed"
    assert chunks[0]["failure"]["code"] == "chunk_extraction_failure"
    assert chunks[0]["processor"] == "storygraph-stage1"


def test_stage1_unparsable_subagent_json_fails_and_records_ledger(tmp_path):
    novel = tmp_path / "mini_novel.txt"
    novel.write_text("法宝", encoding="utf-8")
    template_dir = tmp_path / "templates"
    graphify_repo = tmp_path / "graphify"
    graphify_repo.mkdir()
    _write_template(template_dir, "# 法宝分析模板\n## 字段\n- 法宝")
    config = _config(template_dir, graphify_repo)
    config["agent_policy"]["sub_agent_json_payloads"] = ["{not json"]

    result = build_stage1_graph(novel, config)

    graph_dir = tmp_path / "mini_novel.storygraph"
    ledger = json.loads((graph_dir / "coverage" / "agent-run-ledger.json").read_text(encoding="utf-8"))
    gap = (graph_dir / "coverage" / "gap-report.md").read_text(encoding="utf-8")
    assert result["status"] == "failed"
    assert any(
        error["code"] == "unparsable_subagent_json"
        for record in ledger
        for error in record["errors"]
    )
    assert "unparsable_subagent_json" in gap


def test_stage1_single_writer_conflict_fails_before_success_outputs(tmp_path, monkeypatch):
    import storygraph_lib.stage1 as stage1_mod
    from storygraph_lib.agent_ledger import make_agent_run_record

    novel = tmp_path / "mini_novel.txt"
    novel.write_text("法宝", encoding="utf-8")
    template_dir = tmp_path / "templates"
    graphify_repo = tmp_path / "graphify"
    graphify_repo.mkdir()
    _write_template(template_dir, "# 法宝分析模板\n## 字段\n- 法宝")

    def conflicting_records(chunk_ids, template_names):
        return [
            make_agent_run_record(
                "run-a",
                "模板需求分析",
                "stage1",
                [],
                template_names,
                ["source"],
                ["manifest.json"],
                ["manifest.json"],
            ),
            make_agent_run_record(
                "run-b",
                "图抽取",
                "stage1",
                chunk_ids,
                template_names,
                ["source"],
                ["manifest.json"],
                ["graphify-out/graph.json"],
            ),
        ]

    monkeypatch.setattr(stage1_mod, "make_stage_agent_records", conflicting_records)

    result = build_stage1_graph(novel, _config(template_dir, graphify_repo))

    graph_dir = tmp_path / "mini_novel.storygraph"
    manifest = json.loads((graph_dir / "manifest.json").read_text(encoding="utf-8"))
    assert result["status"] == "failed"
    assert result["error"]["code"] == "single_writer_conflict"
    assert manifest["stage_status"]["stage1"] == "failed"
    assert not (graph_dir / "graphify-out" / "graph.json").exists()


def test_stage1_missing_source_returns_structured_error_and_writes_failure_outputs_when_graph_dir_is_known(
    tmp_path,
):
    source = tmp_path / "missing_novel.txt"
    template_dir = tmp_path / "templates"
    _write_template(template_dir, "# 法宝分析模板\n## 字段\n- 法宝")

    result = build_stage1_graph(source, _config(template_dir, tmp_path / "graphify"))

    graph_dir = tmp_path / "missing_novel.storygraph"
    manifest = json.loads((graph_dir / "manifest.json").read_text(encoding="utf-8"))
    ledger = json.loads((graph_dir / "coverage" / "agent-run-ledger.json").read_text(encoding="utf-8"))
    gap = (graph_dir / "coverage" / "gap-report.md").read_text(encoding="utf-8")
    assert result["status"] == "failed"
    assert result["error"]["code"] == "source_unreadable"
    assert result["graph_dir"] == str(graph_dir)
    assert result["manifest_written"] is True
    assert manifest["stage_status"]["stage1"] == "failed"
    assert any(
        error["code"] == "source_unreadable"
        for record in ledger
        for error in record.get("errors", [])
    )
    assert "source_unreadable" in gap


def test_stage1_cli_source_unreadable_returns_json_even_when_graph_dir_cannot_be_inferred(
    tmp_path, capsys, monkeypatch
):
    import storygraph_lib.cli as cli_mod
    import storygraph_lib.stage1 as stage1_mod

    template_dir = tmp_path / "templates"
    _write_template(template_dir, "# 法宝分析模板\n## 字段\n- 法宝")

    def fail_preflight(*args, **kwargs):
        raise OSError("bad source path")

    monkeypatch.setattr(stage1_mod, "_infer_novel_context_without_reading", fail_preflight)

    exit_code = cli_mod.main(
        ["build-stage1", "--source", "<bad-source>", "--template-dir", str(template_dir)]
    )

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 2
    assert payload["status"] == "failed"
    assert payload["error"]["code"] == "source_unreadable"
    assert payload["graph_dir"] is None
    assert payload["manifest_written"] is False


def test_stage1_invalid_utf8_source_uses_stable_encoding_error_code(tmp_path):
    novel = tmp_path / "bad_encoding.txt"
    novel.write_bytes(b"\xff\xfe\xfa")
    template_dir = tmp_path / "templates"
    graphify_repo = tmp_path / "graphify"
    graphify_repo.mkdir()
    _write_template(template_dir, "# 法宝分析模板\n## 字段\n- 法宝")

    result = build_stage1_graph(novel, _config(template_dir, graphify_repo))

    graph_dir = tmp_path / "bad_encoding.storygraph"
    manifest = json.loads((graph_dir / "manifest.json").read_text(encoding="utf-8"))
    ledger = json.loads((graph_dir / "coverage" / "agent-run-ledger.json").read_text(encoding="utf-8"))
    assert result["status"] == "failed"
    assert result["error"]["code"] == "source_encoding_error"
    assert manifest["stage_status"]["stage1"] == "failed"
    assert any(
        error["code"] == "source_encoding_error"
        for record in ledger
        for error in record.get("errors", [])
    )


def test_stage1_graphify_exit_zero_missing_artifacts_fails_manifest_and_validate_graph_blocks(
    tmp_path,
):
    novel = tmp_path / "mini_novel.txt"
    novel.write_text("法宝", encoding="utf-8")
    template_dir = tmp_path / "templates"
    _write_template(template_dir, "# 法宝分析模板\n## 字段\n- 法宝")
    config = _config(template_dir, graphify_repo=None)
    config["graphify_adapter"] = {
        "mode": "cli",
        "command": [
            sys.executable,
            "-c",
            "import pathlib,sys; pathlib.Path(sys.argv[2]).mkdir(parents=True, exist_ok=True)",
            "{source}",
            "{output_dir}",
        ],
        "timeout_seconds": 5,
    }

    result = build_stage1_graph(novel, config)

    graph_dir = tmp_path / "mini_novel.storygraph"
    manifest = json.loads((graph_dir / "manifest.json").read_text(encoding="utf-8"))
    ledger = json.loads((graph_dir / "coverage" / "agent-run-ledger.json").read_text(encoding="utf-8"))
    validation = validate_graph_dir(graph_dir)
    assert result["status"] == "failed"
    assert result["error"]["code"] == "graphify_artifact_missing"
    assert not (graph_dir / "graphify-out" / "graph.json").exists()
    assert manifest["stage_status"]["stage1"] == "failed"
    assert any(
        error["code"] == "graphify_artifact_missing"
        for record in ledger
        for error in record.get("errors", [])
    )
    assert "blocking_ledger:graphify_artifact_missing" in validation.errors


def test_stage1_graphify_malformed_graph_json_is_structured_failure(tmp_path):
    novel = tmp_path / "mini_novel.txt"
    novel.write_text("第一章\n法宝卡片记载法宝。小瓶出现。", encoding="utf-8")
    template_dir = tmp_path / "templates"
    _write_template(template_dir)
    config = _config(template_dir, graphify_repo=None)
    config["graphify_adapter"] = {
        "mode": "cli",
        "command": _graphify_command_with(
            "import pathlib,sys; "
            "out=pathlib.Path(sys.argv[2]); out.mkdir(parents=True, exist_ok=True); "
            "(out/'graph.json').write_text('{bad json', encoding='utf-8'); "
            "(out/'GRAPH_REPORT.md').write_text('# Graph Report\\n', encoding='utf-8'); "
            "(out/'graph.html').write_text('<!doctype html><title>graph</title>', encoding='utf-8')"
        ),
        "timeout_seconds": 5,
    }

    result = build_stage1_graph(novel, config)

    graph_dir = tmp_path / "mini_novel.storygraph"
    manifest = json.loads((graph_dir / "manifest.json").read_text(encoding="utf-8"))
    ledger = json.loads((graph_dir / "coverage" / "agent-run-ledger.json").read_text(encoding="utf-8"))
    gap = (graph_dir / "coverage" / "gap-report.md").read_text(encoding="utf-8")
    assert result["status"] == "failed"
    assert result["error"]["code"] == "graphify_failed"
    assert "graphify_failed" in result["validation_errors"]
    assert manifest["stage_status"]["stage1"] == "failed"
    assert any(
        error["code"] == "graphify_failed"
        for record in ledger
        for error in record.get("errors", [])
    )
    assert "graphify_failed" in gap
    assert not (graph_dir / "graphify-out" / "graph.json").exists()


def test_stage1_graphify_unreadable_report_is_structured_failure(tmp_path):
    novel = tmp_path / "mini_novel.txt"
    novel.write_text("第一章\n法宝卡片记载法宝。小瓶出现。", encoding="utf-8")
    template_dir = tmp_path / "templates"
    _write_template(template_dir)
    config = _config(template_dir, graphify_repo=None)
    config["graphify_adapter"] = {
        "mode": "cli",
        "command": _graphify_command_with(
            "import json,pathlib,sys; "
            "out=pathlib.Path(sys.argv[2]); out.mkdir(parents=True, exist_ok=True); "
            "graph={'schema_version':'1.0','graphify_schema_version':'test',"
            "'storygraph_schema_version':'1.0','nodes':[],'edges':[],'hyperedges':[],"
            "'events':[],'evidence_index':[],'metadata':{'graphify_schema_version':'test'}}; "
            "(out/'graph.json').write_text(json.dumps(graph), encoding='utf-8'); "
            "(out/'GRAPH_REPORT.md').mkdir(); "
            "(out/'graph.html').write_text('<!doctype html><title>graph</title>', encoding='utf-8')"
        ),
        "timeout_seconds": 5,
    }

    result = build_stage1_graph(novel, config)

    graph_dir = tmp_path / "mini_novel.storygraph"
    manifest = json.loads((graph_dir / "manifest.json").read_text(encoding="utf-8"))
    ledger = json.loads((graph_dir / "coverage" / "agent-run-ledger.json").read_text(encoding="utf-8"))
    assert result["status"] == "failed"
    assert result["error"]["code"] == "graphify_failed"
    assert manifest["stage_status"]["stage1"] == "failed"
    assert any(
        error["code"] == "graphify_failed"
        for record in ledger
        for error in record.get("errors", [])
    )
    assert not (graph_dir / "graphify-out" / "graph.json").exists()


def test_stage1_graphify_bad_graph_shape_is_structured_failure(tmp_path):
    novel = tmp_path / "mini_novel.txt"
    novel.write_text("第一章\n法宝卡片记载法宝。小瓶出现。", encoding="utf-8")
    template_dir = tmp_path / "templates"
    _write_template(template_dir)
    config = _config(template_dir, graphify_repo=None)
    config["graphify_adapter"] = {
        "mode": "cli",
        "command": _graphify_command_with(
            "import json,pathlib,sys; "
            "out=pathlib.Path(sys.argv[2]); out.mkdir(parents=True, exist_ok=True); "
            "graph={'schema_version':'1.0','graphify_schema_version':'test',"
            "'storygraph_schema_version':'1.0','nodes':['bad-node'],"
            "'edges':[],'hyperedges':[],'events':[],'evidence_index':[],'metadata':'bad'}; "
            "(out/'graph.json').write_text(json.dumps(graph), encoding='utf-8'); "
            "(out/'GRAPH_REPORT.md').write_text('# Graph Report\\n', encoding='utf-8'); "
            "(out/'graph.html').write_text('<!doctype html><title>graph</title>', encoding='utf-8')"
        ),
        "timeout_seconds": 5,
    }

    result = build_stage1_graph(novel, config)

    graph_dir = tmp_path / "mini_novel.storygraph"
    manifest = json.loads((graph_dir / "manifest.json").read_text(encoding="utf-8"))
    assert result["status"] == "failed"
    assert result["error"]["code"] == "graphify_failed"
    assert manifest["stage_status"]["stage1"] == "failed"
    assert not (graph_dir / "graphify-out" / "graph.json").exists()
