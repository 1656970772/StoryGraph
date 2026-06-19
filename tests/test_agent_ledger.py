import json

import pytest

from storygraph_lib.agent_ledger import (
    make_agent_run_record,
    make_stage_agent_records,
    validate_single_writer,
)
from storygraph_lib.output_writer import OutputWriteError, OutputWriter


def test_make_agent_run_record_uses_plan_contract_defaults():
    record = make_agent_run_record(
        "run-001",
        "图抽取",
        "stage-1",
        ["chunk-0001"],
        ["法宝分析"],
        ["coverage/chunk-ledger.json"],
        ["graphify-out/graph.json"],
        ["graphify-out/graph.json"],
    )

    assert record == {
        "run_id": "run-001",
        "agent_role": "图抽取",
        "stage": "stage-1",
        "assigned_chunk_ids": ["chunk-0001"],
        "assigned_template_names": ["法宝分析"],
        "input_paths": ["coverage/chunk-ledger.json"],
        "output_paths": ["graphify-out/graph.json"],
        "write_scope": ["graphify-out/graph.json"],
        "status": "pending",
        "errors": [],
        "merge_owner": "single-writer",
        "reviewer_status": "pending",
        "started_at": None,
        "finished_at": None,
    }


def test_validate_single_writer_detects_duplicate_outputs_write_scopes_and_cross_conflicts():
    records = [
        make_agent_run_record(
            "run-coverage-a",
            "覆盖审查",
            "stage-1",
            ["chunk-0001"],
            ["法宝分析"],
            ["requirements/template-requirements.json"],
            ["coverage/template-readiness.json"],
            ["coverage/template-readiness.json", "coverage/gap-report.md"],
        ),
        make_agent_run_record(
            "run-coverage-b",
            "质量审查",
            "stage-1",
            ["chunk-0002"],
            ["人物分析"],
            ["graphify-out/graph.json"],
            ["coverage/template-readiness.json"],
            ["coverage/template-readiness.json"],
        ),
        make_agent_run_record(
            "run-cross",
            "图抽取",
            "stage-1",
            ["chunk-0003"],
            ["事件分析"],
            ["novel.txt"],
            ["coverage/gap-report.md"],
            ["graphify-out/graph.json"],
        ),
    ]

    result = validate_single_writer(records)

    assert result.ok is False
    assert "duplicate_output:coverage/template-readiness.json" in result.errors
    assert "write_conflict:coverage/template-readiness.json" in result.errors
    assert "write_conflict:coverage/gap-report.md" in result.errors


def test_make_stage_agent_records_returns_required_roles_and_io_scope():
    records = make_stage_agent_records(
        chunk_ids=["chunk-0001", "chunk-0002"],
        template_names=["法宝分析", "人物分析"],
    )

    assert [record["agent_role"] for record in records] == [
        "模板需求分析",
        "图抽取",
        "覆盖审查",
        "质量审查",
    ]
    assert [record["run_id"] for record in records] == [
        "stage-1-template-requirements",
        "stage-1-graph-extraction",
        "stage-1-coverage-review",
        "stage-1-quality-review",
    ]
    for record in records:
        assert record["stage"] == "stage-1"
        assert record["assigned_chunk_ids"] == ["chunk-0001", "chunk-0002"]
        assert record["assigned_template_names"] == ["法宝分析", "人物分析"]
        assert record["input_paths"]
        assert record["output_paths"]
        assert record["write_scope"]
        assert record["merge_owner"] == "single-writer"
    assert validate_single_writer(records).ok is True


def test_output_writer_allows_managed_outputs_and_rejects_unmanaged_outputs(tmp_path):
    writer = OutputWriter(
        graph_dir=str(tmp_path),
        managed_outputs=[
            "coverage/chunk-ledger.json",
            "coverage/gap-report.md",
        ],
    )

    json_path = writer.write_json("coverage/chunk-ledger.json", {"ok": True})
    text_path = writer.write_text("coverage/gap-report.md", "no gaps\n")

    assert json.loads(json_path.read_text(encoding="utf-8")) == {"ok": True}
    assert text_path.read_text(encoding="utf-8") == "no gaps\n"
    with pytest.raises(OutputWriteError, match="unmanaged_output"):
        writer.write_json("coverage/unmanaged.json", {})
    with pytest.raises(OutputWriteError, match="duplicate_write"):
        writer.write_json("coverage/chunk-ledger.json", {"again": True})
