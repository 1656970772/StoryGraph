import json

import pytest

from storygraph_lib.agent_ledger import (
    make_agent_run_record,
    make_stage_agent_records,
    validate_single_writer,
)
from storygraph_lib.output_writer import OutputWriteError, OutputWriter


def test_make_agent_run_record_defaults_pending_single_writer():
    record = make_agent_run_record(
        role="图抽取",
        input=["novel.txt"],
        output=["graphify-out/graph.json"],
        write_scope=["graphify-out/graph.json"],
    )

    assert record["status"] == "pending"
    assert record["merge_owner"] == "single-writer"
    assert record["input"] == ["novel.txt"]
    assert record["output"] == ["graphify-out/graph.json"]
    assert record["write_scope"] == ["graphify-out/graph.json"]
    assert record["run_id"].startswith("agent-run:")


def test_validate_single_writer_detects_duplicate_output_and_write_conflicts():
    records = [
        make_agent_run_record(
            role="覆盖审查",
            input=["requirements/template-requirements.json"],
            output=["coverage/template-readiness.json"],
            write_scope=["coverage/template-readiness.json"],
        ),
        make_agent_run_record(
            role="质量审查",
            input=["graphify-out/graph.json"],
            output=["coverage/template-readiness.json"],
            write_scope=["coverage/template-readiness.json"],
        ),
    ]

    result = validate_single_writer(records)

    assert result.ok is False
    assert "duplicate_output:coverage/template-readiness.json" in result.errors
    assert "write_conflict:coverage/template-readiness.json" in result.errors


def test_make_stage_agent_records_returns_required_roles_and_io_scope():
    records = make_stage_agent_records(
        source_path="novel.txt",
        graph_dir="novel.storygraph",
    )

    assert [record["role"] for record in records] == [
        "模板需求分析",
        "图抽取",
        "覆盖审查",
        "质量审查",
    ]
    for record in records:
        assert record["input"]
        assert record["output"]
        assert record["write_scope"]
        assert record["merge_owner"] == "single-writer"


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
