import json

from storygraph_lib.stage2 import claim_stage2_batches, prepare_stage2
from test_stage2_prepare import _stage2_config, _write_stage1_inputs


def _valid_stage2_record():
    return {
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
                "markdown": "韩立获得小瓶。",
                "evidence_ids": ["evidence:abc"],
                "requirement_ids": ["resources_items_economy"],
                "confidence": "EXTRACTED",
            }
        ],
        "evidence_citations": ["evidence:abc"],
        "overwrite_policy": "draft",
    }


def _record_path(graph_dir):
    return (
        graph_dir
        / "intermediate"
        / "stage2"
        / "extraction-records"
        / "法宝分析"
        / "run-001.json"
    )


def test_claim_stage2_batches_tracks_running_and_completed_outputs(tmp_path):
    graph_dir = tmp_path / "book.storygraph"
    template_dir = tmp_path / "templates"
    graph_dir.mkdir()
    template_dir.mkdir()
    _write_stage1_inputs(graph_dir, template_dir)
    prepare_stage2(graph_dir, template_dir, _stage2_config())

    claimed = claim_stage2_batches(graph_dir, limit=1)

    assert claimed["status"] == "stage2_batches_claimed"
    assert claimed["claimed_count"] == 1
    assert claimed["in_flight_count"] == 1
    assert claimed["pending_count"] == 0

    waiting = claim_stage2_batches(graph_dir, limit=1)

    assert waiting["claimed_count"] == 0
    assert waiting["in_flight_count"] == 1
    assert waiting["pending_count"] == 0

    output_path = _record_path(graph_dir)
    output_path.parent.mkdir(parents=True)
    output_path.write_text(
        json.dumps(_valid_stage2_record(), ensure_ascii=False),
        encoding="utf-8",
    )

    completed = claim_stage2_batches(graph_dir, limit=1)

    assert completed["claimed_count"] == 0
    assert completed["in_flight_count"] == 0
    assert completed["completed_count"] == 1


def test_claim_stage2_batches_does_not_complete_invalid_record(tmp_path):
    graph_dir = tmp_path / "book.storygraph"
    template_dir = tmp_path / "templates"
    graph_dir.mkdir()
    template_dir.mkdir()
    _write_stage1_inputs(graph_dir, template_dir)
    prepare_stage2(graph_dir, template_dir, _stage2_config())
    claim_stage2_batches(graph_dir, limit=1)

    output_path = _record_path(graph_dir)
    output_path.parent.mkdir(parents=True)
    record = _valid_stage2_record()
    del record["document_sections"]
    output_path.write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")

    result = claim_stage2_batches(graph_dir, limit=1)

    assert result["in_flight_count"] == 1
    assert result["completed_count"] == 0
    state_path = graph_dir / "intermediate" / "stage2" / "dispatch-state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["batches"][0]["status"] == "running"
    assert any("document_sections.required" in error for error in state["batches"][0]["errors"])


def test_claim_stage2_batches_does_not_complete_bom_or_malformed_record(tmp_path):
    graph_dir = tmp_path / "book.storygraph"
    template_dir = tmp_path / "templates"
    graph_dir.mkdir()
    template_dir.mkdir()
    _write_stage1_inputs(graph_dir, template_dir)
    prepare_stage2(graph_dir, template_dir, _stage2_config())
    claim_stage2_batches(graph_dir, limit=1)

    output_path = _record_path(graph_dir)
    output_path.parent.mkdir(parents=True)
    payload = json.dumps(_valid_stage2_record(), ensure_ascii=False).encode("utf-8")
    output_path.write_bytes(b"\xef\xbb\xbf" + payload)

    result = claim_stage2_batches(graph_dir, limit=1)

    assert result["in_flight_count"] == 1
    assert result["completed_count"] == 0
    state_path = graph_dir / "intermediate" / "stage2" / "dispatch-state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert any(
        "bom" in error.lower() or "encoding" in error.lower()
        for error in state["batches"][0]["errors"]
    )

    output_path.write_text("{", encoding="utf-8")
    result = claim_stage2_batches(graph_dir, limit=1)

    assert result["in_flight_count"] == 1
    assert result["completed_count"] == 0
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert any("json" in error.lower() for error in state["batches"][0]["errors"])


def test_claim_stage2_batches_rejects_escaping_expected_output_path(tmp_path):
    graph_dir = tmp_path / "book.storygraph"
    template_dir = tmp_path / "templates"
    graph_dir.mkdir()
    template_dir.mkdir()
    _write_stage1_inputs(graph_dir, template_dir)
    prepare_stage2(graph_dir, template_dir, _stage2_config())
    claim_stage2_batches(graph_dir, limit=1)

    outside_record = tmp_path / "escape.json"
    outside_record.write_text(json.dumps(_valid_stage2_record(), ensure_ascii=False), encoding="utf-8")
    state_path = graph_dir / "intermediate" / "stage2" / "dispatch-state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["batches"][0]["expected_output_rel_paths"] = ["../escape.json"]
    state["batches"][0]["expected_output_paths"] = [str(outside_record)]
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")

    result = claim_stage2_batches(graph_dir, limit=1)

    assert result["in_flight_count"] == 1
    assert result["completed_count"] == 0
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert any(
        "expected_output_path_invalid:../escape.json" in error
        for error in state["batches"][0]["errors"]
    )
