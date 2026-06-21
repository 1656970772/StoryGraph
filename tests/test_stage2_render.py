import json

from storygraph_lib.stage2 import ingest_stage2, prepare_stage2, render_stage2, validate_stage2
from test_stage2_prepare import _stage2_config, _write_stage1_inputs


def _write_stage2_record(graph_dir, *, overwrite_policy="draft"):
    path = (
        graph_dir
        / "intermediate"
        / "stage2"
        / "extraction-records"
        / "法宝分析"
        / "run-001.json"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            {
                "schema": "stage2-extraction-record.v1",
                "template_name": "法宝分析",
                "template_file": "法宝分析模板.md",
                "source_graph": "graphify-out/graph.json",
                "source_novel": "book.txt",
                "stage2_policy": {
                    "stage2_categories": {
                        "facts": "原作事实",
                        "judgments": "我的判断",
                        "pending_verifications": "待核验",
                        "not_found_items": "未见可靠证据",
                    },
                    "stage2_output_policy": {
                        "default_dir": "drafts",
                        "allowed_policies": ["draft", "backup-and-overwrite", "merge"],
                        "draft_action": "write_draft",
                    },
                },
                "coverage_scope": {
                    "scope": "whole_novel",
                    "stage1_chunk_ledger": "coverage/chunk-ledger.json",
                    "chunk_ranges": [{"chunk_id": "chunk-0001", "source_range": [0, 10]}],
                    "ledger_path": "coverage/template-run-ledger.json",
                },
                "fulfilled_sections": [],
                "facts": [
                    {
                        "content": "韩立获得小瓶。",
                        "category": "原作事实",
                        "evidence_ids": ["evidence:abc"],
                        "source_locations": [],
                        "confidence": "EXTRACTED",
                    }
                ],
                "judgments": [],
                "pending_verifications": [],
                "not_found_items": [],
                "document_sections": [
                    {
                        "heading": "来源",
                        "markdown": "韩立获得小瓶，这是后续资源线索。",
                        "evidence_ids": ["evidence:abc"],
                        "requirement_ids": ["resources_items_economy"],
                        "confidence": "EXTRACTED",
                    }
                ],
                "evidence_citations": ["evidence:abc"],
                "overwrite_policy": overwrite_policy,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return path


def _write_manifest(graph_dir, stage2_status="prepared"):
    manifest_path = graph_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            {
                "source_path": str(graph_dir.parent / "book.txt"),
                "stage_status": {"stage1": "success", "stage2": stage2_status},
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    return manifest_path


def _complete_template_task(graph_dir, output_record):
    ledger_path = graph_dir / "coverage" / "template-run-ledger.json"
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    ledger["template_tasks"][0]["status"] = "completed"
    ledger["template_tasks"][0]["output_record"] = output_record
    ledger_path.write_text(json.dumps(ledger, ensure_ascii=False, indent=2), encoding="utf-8")


def test_ingest_and_render_stage2_writes_draft_with_evidence_and_warning(tmp_path):
    graph_dir = tmp_path / "book.storygraph"
    template_dir = tmp_path / "templates"
    graph_dir.mkdir()
    template_dir.mkdir()
    config = _stage2_config()
    _write_stage1_inputs(graph_dir, template_dir)
    prepare_stage2(graph_dir, template_dir, config)
    _write_stage2_record(graph_dir)

    ingest = ingest_stage2(graph_dir, config)
    render = render_stage2(graph_dir, config)

    assert ingest["status"] == "ingested"
    assert render["status"] == "rendered"
    draft = graph_dir / "drafts" / "法宝分析.md"
    text = draft.read_text(encoding="utf-8")
    assert "# 法宝分析" in text
    assert "## 来源" in text
    assert "韩立获得小瓶，这是后续资源线索。" in text
    assert "[evidence:abc]" in text
    assert "Stage 1 review_status: unreviewed_usable" in text


def test_render_stage2_backup_overwrite_backs_up_existing_formal_document(tmp_path):
    graph_dir = tmp_path / "book.storygraph"
    template_dir = tmp_path / "templates"
    graph_dir.mkdir()
    template_dir.mkdir()
    config = _stage2_config()
    config["overwrite_policy"] = "backup-and-overwrite"
    _write_stage1_inputs(graph_dir, template_dir)
    prepare_stage2(graph_dir, template_dir, config)
    formal = tmp_path / "法宝分析.md"
    formal.write_text("用户已有正式文档", encoding="utf-8")
    _write_stage2_record(graph_dir, overwrite_policy="backup-and-overwrite")
    ingest_stage2(graph_dir, config)

    result = render_stage2(graph_dir, config)

    assert result["status"] == "rendered"
    assert result["rendered"] == ["../法宝分析.md"]
    assert (tmp_path / "法宝分析.md.bak").read_text(encoding="utf-8") == "用户已有正式文档"
    formal_text = formal.read_text(encoding="utf-8")
    assert "# 法宝分析" in formal_text
    assert "韩立获得小瓶，这是后续资源线索。" in formal_text


def test_render_stage2_backup_overwrite_creates_new_formal_document_without_backup(tmp_path):
    graph_dir = tmp_path / "book.storygraph"
    template_dir = tmp_path / "templates"
    graph_dir.mkdir()
    template_dir.mkdir()
    config = _stage2_config()
    config["overwrite_policy"] = "backup-and-overwrite"
    _write_stage1_inputs(graph_dir, template_dir)
    prepare_stage2(graph_dir, template_dir, config)
    _write_stage2_record(graph_dir, overwrite_policy="backup-and-overwrite")
    ingest_stage2(graph_dir, config)

    result = render_stage2(graph_dir, config)

    assert result["status"] == "rendered"
    assert (tmp_path / "法宝分析.md").exists()
    assert not (tmp_path / "法宝分析.md.bak").exists()


def test_render_stage2_merge_policy_requires_merge_contract_and_preserves_formal_document(tmp_path):
    graph_dir = tmp_path / "book.storygraph"
    template_dir = tmp_path / "templates"
    graph_dir.mkdir()
    template_dir.mkdir()
    config = _stage2_config()
    config["overwrite_policy"] = "merge"
    _write_stage1_inputs(graph_dir, template_dir)
    prepare_stage2(graph_dir, template_dir, config)
    formal = tmp_path / "法宝分析.md"
    formal.write_text("用户已有正式文档", encoding="utf-8")
    _write_stage2_record(graph_dir, overwrite_policy="merge")
    ingest_stage2(graph_dir, config)

    result = render_stage2(graph_dir, config)

    assert result["status"] == "failed"
    assert result["error"] == "stage2_merge_contract_required"
    assert formal.read_text(encoding="utf-8") == "用户已有正式文档"


def test_render_stage2_fails_without_completed_records_and_preserves_manifest(tmp_path):
    graph_dir = tmp_path / "book.storygraph"
    template_dir = tmp_path / "templates"
    graph_dir.mkdir()
    template_dir.mkdir()
    config = _stage2_config()
    _write_stage1_inputs(graph_dir, template_dir)
    prepare_stage2(graph_dir, template_dir, config)
    manifest_path = _write_manifest(graph_dir, stage2_status="prepared")

    result = render_stage2(graph_dir, config)

    assert result["status"] == "failed"
    assert result["error"] == "no_stage2_records_to_render"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["stage_status"]["stage2"] == "prepared"


def test_ingest_stage2_returns_structured_failure_for_bom_record(tmp_path):
    graph_dir = tmp_path / "book.storygraph"
    template_dir = tmp_path / "templates"
    graph_dir.mkdir()
    template_dir.mkdir()
    config = _stage2_config()
    _write_stage1_inputs(graph_dir, template_dir)
    prepare_stage2(graph_dir, template_dir, config)
    record_path = _write_stage2_record(graph_dir)
    payload = record_path.read_text(encoding="utf-8").encode("utf-8")
    record_path.write_bytes(b"\xef\xbb\xbf" + payload)

    result = ingest_stage2(graph_dir, config)

    assert result["status"] == "failed"
    assert result["error"] == "stage2_record_validation_failed"
    assert any("bom" in error.lower() or "encoding" in error.lower() for error in result["errors"])


def test_validate_stage2_requires_completed_tasks_to_have_output_record(tmp_path):
    graph_dir = tmp_path / "book.storygraph"
    template_dir = tmp_path / "templates"
    graph_dir.mkdir()
    template_dir.mkdir()
    _write_stage1_inputs(graph_dir, template_dir)
    prepare_stage2(graph_dir, template_dir, _stage2_config())
    _complete_template_task(graph_dir, None)

    result = validate_stage2(graph_dir)

    assert result["ok"] is False
    assert "output_record_required:法宝分析" in result["errors"]


def test_validate_stage2_rejects_bom_record(tmp_path):
    graph_dir = tmp_path / "book.storygraph"
    template_dir = tmp_path / "templates"
    graph_dir.mkdir()
    template_dir.mkdir()
    _write_stage1_inputs(graph_dir, template_dir)
    prepare_stage2(graph_dir, template_dir, _stage2_config())
    record_path = _write_stage2_record(graph_dir)
    record_path.write_bytes(b"\xef\xbb\xbf" + record_path.read_bytes())
    _complete_template_task(
        graph_dir,
        "intermediate/stage2/extraction-records/法宝分析/run-001.json",
    )

    result = validate_stage2(graph_dir)

    assert result["ok"] is False
    assert any("bom" in error.lower() or "encoding" in error.lower() for error in result["errors"])


def test_validate_stage2_rejects_record_missing_document_sections(tmp_path):
    graph_dir = tmp_path / "book.storygraph"
    template_dir = tmp_path / "templates"
    graph_dir.mkdir()
    template_dir.mkdir()
    _write_stage1_inputs(graph_dir, template_dir)
    prepare_stage2(graph_dir, template_dir, _stage2_config())
    record_path = _write_stage2_record(graph_dir)
    record = json.loads(record_path.read_text(encoding="utf-8"))
    del record["document_sections"]
    record_path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    _complete_template_task(
        graph_dir,
        "intermediate/stage2/extraction-records/法宝分析/run-001.json",
    )

    result = validate_stage2(graph_dir)

    assert result["ok"] is False
    assert any("document_sections.required" in error for error in result["errors"])


def test_validate_stage2_rejects_unknown_fact_and_citation_evidence(tmp_path):
    graph_dir = tmp_path / "book.storygraph"
    template_dir = tmp_path / "templates"
    graph_dir.mkdir()
    template_dir.mkdir()
    _write_stage1_inputs(graph_dir, template_dir)
    prepare_stage2(graph_dir, template_dir, _stage2_config())
    record_path = _write_stage2_record(graph_dir)
    record = json.loads(record_path.read_text(encoding="utf-8"))
    record["facts"][0]["evidence_ids"] = ["evidence:missing-fact"]
    record["evidence_citations"] = ["evidence:missing-citation"]
    record_path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    _complete_template_task(
        graph_dir,
        "intermediate/stage2/extraction-records/法宝分析/run-001.json",
    )

    result = validate_stage2(graph_dir)

    assert result["ok"] is False
    assert any("facts[0].evidence_ids.unknown:evidence:missing-fact" in error for error in result["errors"])
    assert any("evidence_citations[0].unknown:evidence:missing-citation" in error for error in result["errors"])


def test_validate_stage2_rejects_output_record_that_escapes_graph_dir(tmp_path):
    graph_dir = tmp_path / "book.storygraph"
    template_dir = tmp_path / "templates"
    graph_dir.mkdir()
    template_dir.mkdir()
    _write_stage1_inputs(graph_dir, template_dir)
    prepare_stage2(graph_dir, template_dir, _stage2_config())
    outside_record = tmp_path / "escape.json"
    outside_record.write_text("{}", encoding="utf-8")
    _complete_template_task(graph_dir, "../escape.json")

    result = validate_stage2(graph_dir)

    assert result["ok"] is False
    assert any("output_record_path_invalid:../escape.json" in error for error in result["errors"])
