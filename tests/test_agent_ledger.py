import json

import pytest

from storygraph_lib.agent_ledger import (
    make_agent_run_record,
    make_lane_agent_record,
    make_repair_agent_record,
    make_review_agent_record,
    make_stage_agent_records,
    make_template_agent_record,
    validate_repair_attempts,
    validate_single_writer,
)
from storygraph_lib.output_writer import OutputWriteError, OutputWriter


def test_make_agent_run_record_uses_plan_contract_defaults():
    record = make_agent_run_record(
        "run-001",
        "图抽取",
        "stage1",
        ["chunk-0001"],
        ["法宝分析"],
        ["coverage/chunk-ledger.json"],
        ["graphify-out/graph.json"],
        ["graphify-out/graph.json"],
    )

    assert record == {
        "run_id": "run-001",
        "agent_role": "图抽取",
        "stage": "stage1",
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


def test_make_lane_agent_record_requires_task_packet_and_output_path():
    record = make_lane_agent_record(
        run_id="run-001",
        chunk_id="chunk-0001",
        lane_id="entities_resources",
        agent_role="实体道具资源抽取 agent",
        task_packet_path="intermediate/task-packets/chunk-0001/entities_resources.json",
        output_path="intermediate/lane-outputs/chunk-0001/entities_resources/run-001.json",
        attempt=1,
    )

    assert record["stage"] == "stage1"
    assert record["chunk_id"] == "chunk-0001"
    assert record["lane_id"] == "entities_resources"
    assert record["prompt_or_input_packet"].endswith("entities_resources.json")
    assert record["status"] == "pending"
    assert record["attempt"] == 1


def test_make_lane_agent_record_defaults_attempt_to_first_try():
    record = make_lane_agent_record(
        run_id="run-default-attempt",
        chunk_id="chunk-0001",
        lane_id="entities_resources",
        agent_role="probe agent",
        task_packet_path="intermediate/task-packets/chunk-0001/entities_resources.json",
        output_path="intermediate/lane-outputs/chunk-0001/entities_resources/run-default-attempt.json",
    )

    assert record["stage"] == "stage1"
    assert record["status"] == "pending"
    assert record["attempt"] == 1


def test_agent_record_factories_include_required_rewrite_fields():
    required_keys = {
        "run_id",
        "chunk_id",
        "lane_id",
        "agent_role",
        "prompt_or_input_packet",
        "input_paths",
        "output_paths",
        "write_scope",
        "status",
        "errors",
        "reviewer_status",
        "repair_of",
        "attempt",
        "started_at",
        "ended_at",
    }

    records = [
        make_template_agent_record(
            run_id="run-template-001",
            chunk_id="chunk-0001",
            lane_id="template_requirements",
            agent_role="模板需求分析 agent",
            template_name="人物分析",
            task_packet_path="intermediate/task-packets/chunk-0001/template_requirements.json",
            output_path="intermediate/template-outputs/chunk-0001/run-template-001.json",
            attempt=1,
        ),
        make_review_agent_record(
            run_id="run-review-001",
            chunk_id="chunk-0001",
            lane_id="entities_resources",
            agent_role="实体道具资源审查 agent",
            review_input_path="intermediate/lane-outputs/chunk-0001/entities_resources/run-001.json",
            output_path="intermediate/reviews/chunk-0001/entities_resources/run-review-001.json",
            attempt=1,
        ),
        make_repair_agent_record(
            run_id="run-repair-001",
            chunk_id="chunk-0001",
            lane_id="entities_resources",
            agent_role="实体道具资源修复 agent",
            task_packet_path="intermediate/task-packets/chunk-0001/entities_resources.json",
            output_path="intermediate/lane-outputs/chunk-0001/entities_resources/run-repair-001.json",
            repair_of="finding-001",
            attempt=2,
        ),
    ]

    for record in records:
        assert required_keys <= record.keys()
        assert record["status"] == "pending"
        assert record["errors"] == []
        assert record["started_at"] is None
        assert record["ended_at"] is None
        assert validate_single_writer([record]).ok is True
    assert records[0]["template_name"] == "人物分析"
    assert records[2]["repair_of"] == "finding-001"
    assert records[2]["attempt"] == 2


@pytest.mark.parametrize(
    "factory, factory_kwargs",
    [
        (
            make_lane_agent_record,
            {
                "task_packet_path": "intermediate/task-packets/chunk-0001/entities_resources.json",
            },
        ),
        (
            make_template_agent_record,
            {
                "template_name": "人物分析",
                "task_packet_path": "intermediate/task-packets/chunk-0001/template_requirements.json",
            },
        ),
        (
            make_review_agent_record,
            {
                "review_input_path": "intermediate/reviews/chunk-0001/entities_resources/input.json",
            },
        ),
        (
            make_repair_agent_record,
            {
                "task_packet_path": "intermediate/task-packets/chunk-0001/entities_resources.json",
                "repair_of": "finding-001",
            },
        ),
    ],
)
@pytest.mark.parametrize("output_path", [None, []])
def test_agent_record_factories_reject_missing_output_paths(factory, factory_kwargs, output_path):
    kwargs = {
        "run_id": "run-missing-output",
        "chunk_id": "chunk-0001",
        "lane_id": "entities_resources",
        "agent_role": "实体道具资源抽取 agent",
        "output_path": output_path,
        "attempt": 1,
        **factory_kwargs,
    }

    with pytest.raises(OutputWriteError, match="unmanaged_output:output_paths"):
        factory(**kwargs)


@pytest.mark.parametrize(
    "factory, factory_kwargs",
    [
        (
            make_lane_agent_record,
            {
                "task_packet_path": "intermediate/task-packets/chunk-0001/entities_resources.json",
            },
        ),
        (
            make_template_agent_record,
            {
                "template_name": "人物分析",
                "task_packet_path": "intermediate/task-packets/chunk-0001/template_requirements.json",
            },
        ),
        (
            make_review_agent_record,
            {
                "review_input_path": "intermediate/reviews/chunk-0001/entities_resources/input.json",
            },
        ),
        (
            make_repair_agent_record,
            {
                "task_packet_path": "intermediate/task-packets/chunk-0001/entities_resources.json",
                "repair_of": "finding-001",
            },
        ),
    ],
)
def test_agent_record_factories_reject_malformed_input_path_items_without_stringifying(
    factory, factory_kwargs
):
    kwargs = {
        "run_id": "run-bad-items",
        "chunk_id": "chunk-0001",
        "lane_id": "entities_resources",
        "agent_role": "实体道具资源抽取 agent",
        "output_path": "intermediate/lane-outputs/chunk-0001/entities_resources/run-001.json",
        "input_paths": [{"not": "path"}],
        "attempt": 1,
        **factory_kwargs,
    }

    with pytest.raises(OutputWriteError) as exc_info:
        factory(**kwargs)

    message = str(exc_info.value)
    assert message == "invalid_path_item:input_paths"
    assert "{'not': 'path'}" not in message


@pytest.mark.parametrize(
    "factory, factory_kwargs, prompt_key",
    [
        (
            make_lane_agent_record,
            {
                "task_packet_path": "intermediate/task-packets/chunk-0001/entities_resources.json",
            },
            "task_packet_path",
        ),
        (
            make_template_agent_record,
            {
                "template_name": "人物分析",
                "task_packet_path": "intermediate/task-packets/chunk-0001/template_requirements.json",
            },
            "task_packet_path",
        ),
        (
            make_review_agent_record,
            {
                "review_input_path": "intermediate/reviews/chunk-0001/entities_resources/input.json",
            },
            "review_input_path",
        ),
        (
            make_repair_agent_record,
            {
                "task_packet_path": "intermediate/task-packets/chunk-0001/entities_resources.json",
                "repair_of": "finding-001",
            },
            "task_packet_path",
        ),
    ],
)
@pytest.mark.parametrize("bad_prompt", [{"not": "path"}, ["not-a-scalar"]])
def test_agent_record_factories_reject_malformed_prompt_paths_without_stringifying(
    factory, factory_kwargs, prompt_key, bad_prompt
):
    kwargs = {
        "run_id": "run-bad-prompt",
        "chunk_id": "chunk-0001",
        "lane_id": "entities_resources",
        "agent_role": "实体道具资源抽取 agent",
        "output_path": "intermediate/lane-outputs/chunk-0001/entities_resources/run-001.json",
        "attempt": 1,
        **factory_kwargs,
    }
    kwargs[prompt_key] = bad_prompt

    with pytest.raises(OutputWriteError) as exc_info:
        factory(**kwargs)

    message = str(exc_info.value)
    assert message == "invalid_path_item:prompt_or_input_packet"
    assert "{'not': 'path'}" not in message
    assert "['not-a-scalar']" not in message


@pytest.mark.parametrize("unsafe_path", ["/x.json", "C:/tmp/x.json", "../x.json", "x\0.json"])
def test_agent_record_factories_reject_unsafe_prompt_or_output_paths(unsafe_path):
    with pytest.raises(OutputWriteError):
        make_lane_agent_record(
            run_id="run-bad-input",
            chunk_id="chunk-0001",
            lane_id="entities_resources",
            agent_role="实体道具资源抽取 agent",
            task_packet_path=unsafe_path,
            output_path="intermediate/lane-outputs/chunk-0001/entities_resources/run-001.json",
            attempt=1,
        )

    with pytest.raises(OutputWriteError):
        make_lane_agent_record(
            run_id="run-bad-output",
            chunk_id="chunk-0001",
            lane_id="entities_resources",
            agent_role="实体道具资源抽取 agent",
            task_packet_path="intermediate/task-packets/chunk-0001/entities_resources.json",
            output_path=unsafe_path,
            attempt=1,
        )


def test_repair_agent_must_be_new_run_for_finding():
    finding = {"finding_id": "finding-001", "repair_required": True, "status": "open"}
    bad_records = [
        {"run_id": "run-001", "lane_id": "entities_resources", "repair_of": None},
        {"run_id": "run-001", "lane_id": "entities_resources", "repair_of": "finding-001"},
    ]

    result = validate_repair_attempts([finding], bad_records)

    assert result.ok is False
    assert "repair_agent_not_fresh:finding-001" in result.errors


@pytest.mark.parametrize(
    "finding, expected_error",
    [
        (
            {"finding_id": "finding-missing-status", "repair_required": True},
            "bad_review_finding_status:finding-missing-status",
        ),
        (
            {
                "finding_id": "finding-bad-status",
                "repair_required": True,
                "status": ["open"],
            },
            "bad_review_finding_status:finding-bad-status",
        ),
        (
            {"finding_id": {"bad": "id"}, "repair_required": True, "status": "open"},
            "bad_review_finding_id",
        ),
        (
            {"finding_id": "finding-bad-required", "repair_required": "yes", "status": "open"},
            "bad_review_finding_repair_required:finding-bad-required",
        ),
    ],
)
def test_validate_repair_attempts_rejects_malformed_findings_without_stringifying(
    finding, expected_error
):
    result = validate_repair_attempts([finding], [])

    assert result.ok is False
    assert expected_error in result.errors
    error_text = "\n".join(result.errors)
    assert "{'bad': 'id'}" not in error_text
    assert "['open']" not in error_text


@pytest.mark.parametrize(
    "records, expected_error",
    [
        (
            [{"run_id": {"bad": "id"}, "repair_of": "finding-001"}],
            "bad_repair_run_id:finding-001",
        ),
        (
            [{"run_id": "run-repair-001", "repair_of": {"bad": "id"}}],
            "bad_repair_of",
        ),
    ],
)
def test_validate_repair_attempts_rejects_malformed_repair_records_without_stringifying(
    records, expected_error
):
    finding = {"finding_id": "finding-001", "repair_required": True, "status": "open"}

    result = validate_repair_attempts([finding], records)

    assert result.ok is False
    assert expected_error in result.errors
    assert "{'bad': 'id'}" not in "\n".join(result.errors)


@pytest.mark.parametrize(
    "findings, records, expected_error",
    [
        (
            [],
            [{"run_id": {"bad": "id"}, "repair_of": "finding-missing"}],
            "bad_repair_run_id:finding-missing",
        ),
        (
            [{"finding_id": "finding-closed", "repair_required": True, "status": "closed"}],
            [{"run_id": {"bad": "id"}, "repair_of": "finding-closed"}],
            "bad_repair_run_id:finding-closed",
        ),
        (
            [{"finding_id": "finding-non-required", "repair_required": False, "status": "open"}],
            [{"run_id": ["bad-id"], "repair_of": "finding-non-required"}],
            "bad_repair_run_id:finding-non-required",
        ),
        (
            [],
            [{"repair_of": None}],
            "bad_agent_run_id",
        ),
    ],
)
def test_validate_repair_attempts_rejects_malformed_records_before_finding_filter(
    findings, records, expected_error
):
    result = validate_repair_attempts(findings, records)

    assert result.ok is False
    assert expected_error in result.errors
    error_text = "\n".join(result.errors)
    assert "{'bad': 'id'}" not in error_text
    assert "['bad-id']" not in error_text


def test_repair_agent_validation_accepts_fresh_repair_run():
    finding = {"finding_id": "finding-001", "repair_required": True, "status": "open"}
    records = [
        {"run_id": "run-001", "lane_id": "entities_resources", "repair_of": None},
        {
            "run_id": "run-repair-001",
            "lane_id": "entities_resources",
            "repair_of": "finding-001",
        },
    ]

    result = validate_repair_attempts([finding], records)

    assert result.ok is True
    assert result.errors == []


def test_validate_repair_attempts_ignores_closed_repair_required_findings():
    finding = {"finding_id": "finding-closed", "repair_required": True, "status": "closed"}

    result = validate_repair_attempts([finding], [])

    assert result.ok is True
    assert result.errors == []


def test_validate_single_writer_detects_duplicate_outputs_write_scopes_and_cross_conflicts():
    records = [
        make_agent_run_record(
            "run-coverage-a",
            "覆盖审查",
            "stage1",
            ["chunk-0001"],
            ["法宝分析"],
            ["requirements/template-requirements.json"],
            ["coverage/template-readiness.json"],
            ["coverage/template-readiness.json", "coverage/gap-report.md"],
        ),
        make_agent_run_record(
            "run-coverage-b",
            "质量审查",
            "stage1",
            ["chunk-0002"],
            ["人物分析"],
            ["graphify-out/graph.json"],
            ["coverage/template-readiness.json"],
            ["coverage/template-readiness.json"],
        ),
        make_agent_run_record(
            "run-cross",
            "图抽取",
            "stage1",
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


def test_validate_single_writer_normalizes_relative_paths_before_conflict_checks():
    records = [
        make_agent_run_record(
            "run-a",
            "覆盖审查",
            "stage1",
            ["chunk-0001"],
            ["法宝分析"],
            ["requirements/template-requirements.json"],
            ["coverage/./x.json"],
            ["coverage\\x.json"],
        ),
        make_agent_run_record(
            "run-b",
            "质量审查",
            "stage1",
            ["chunk-0002"],
            ["人物分析"],
            ["graphify-out/graph.json"],
            ["coverage/x.json"],
            ["coverage/./x.json"],
        ),
    ]

    result = validate_single_writer(records)

    assert result.ok is False
    assert "duplicate_output:coverage/x.json" in result.errors
    assert "write_conflict:coverage/x.json" in result.errors


def test_validate_single_writer_reports_absolute_and_out_of_bounds_paths():
    records = [
        make_agent_run_record(
            "run-bad",
            "覆盖审查",
            "stage1",
            ["chunk-0001"],
            ["法宝分析"],
            ["requirements/template-requirements.json"],
            ["C:/tmp/x.json", "../x.json"],
            ["/coverage/x.json"],
        )
    ]

    result = validate_single_writer(records)

    assert result.ok is False
    assert "invalid_path:C:/tmp/x.json" in result.errors
    assert "invalid_path:../x.json" in result.errors
    assert "invalid_path:/coverage/x.json" in result.errors


def test_validate_single_writer_rejects_embedded_nul_paths():
    records = [
        make_agent_run_record(
            "run-bad-nul",
            "覆盖审查",
            "stage1",
            ["chunk-0001"],
            ["法宝分析"],
            ["requirements/template-requirements.json"],
            ["coverage/x\0.json"],
            ["coverage/x\0.json"],
        )
    ]

    result = validate_single_writer(records)

    assert result.ok is False
    assert any(error.startswith("invalid_path:") for error in result.errors)


def test_validate_single_writer_reports_malformed_records_and_path_lists():
    records = [
        "not-a-record",
        {
            "run_id": "run-bad-output",
            "agent_role": "图抽取",
            "output_paths": 1,
            "write_scope": [],
        },
        {
            "run_id": "run-bad-scope",
            "agent_role": "覆盖审查",
            "output_paths": [],
            "write_scope": 1,
        },
    ]

    result = validate_single_writer(records)

    assert result.ok is False
    assert "bad_agent_ledger_record" in result.errors
    assert "invalid_path_list:run-bad-output:output_paths" in result.errors
    assert "invalid_path_list:run-bad-scope:write_scope" in result.errors


def test_validate_single_writer_rejects_malformed_path_items_without_stringifying():
    records = [
        {
            "run_id": "run-bad-items",
            "agent_role": "图抽取",
            "status": "completed",
            "output_paths": [{"not": "a path"}],
            "write_scope": [["also-not-a-path"]],
        }
    ]

    result = validate_single_writer(records)

    assert result.ok is False
    assert "invalid_path_item:run-bad-items:output_paths" in result.errors
    assert "invalid_path_item:run-bad-items:write_scope" in result.errors


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
        "stage1-template-requirements",
        "stage1-graph-extraction",
        "stage1-coverage-review",
        "stage1-quality-review",
    ]
    for record in records:
        assert record["stage"] == "stage1"
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


def test_output_writer_rejects_unsafe_managed_and_write_paths(tmp_path):
    unsafe_paths = ["/coverage/x.json", "C:/tmp/x.json", "../x.json"]
    for unsafe_path in unsafe_paths:
        with pytest.raises(OutputWriteError, match="unmanaged_output"):
            OutputWriter(tmp_path, [unsafe_path])

    writer = OutputWriter(tmp_path, ["coverage/x.json"])
    legal_path = writer.write_json("coverage/x.json", {"ok": True})

    assert legal_path == tmp_path / "coverage" / "x.json"
    for unsafe_path in unsafe_paths:
        unsafe_writer = OutputWriter(tmp_path, ["coverage/x.json"])
        with pytest.raises(OutputWriteError, match="unmanaged_output"):
            unsafe_writer.write_json(unsafe_path, {"ok": False})


def test_output_writer_rejects_embedded_nul_paths_before_filesystem(tmp_path):
    with pytest.raises(OutputWriteError, match="unmanaged_output"):
        OutputWriter(tmp_path, ["coverage/x\0.json"])

    writer = OutputWriter(tmp_path, ["coverage/x.json"])
    with pytest.raises(OutputWriteError, match="unmanaged_output"):
        writer.write_json("coverage/x\0.json", {})
