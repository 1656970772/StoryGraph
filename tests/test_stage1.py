import json
import sys
from pathlib import Path

import pytest


def _valid_embedded_lane_output(**overrides):
    payload = {
        "run_id": "run-001",
        "task_packet_id": "chunk-0001:entities_resources:attempt-001",
        "chunk_id": "chunk-0001",
        "lane_id": "entities_resources",
        "agent_role": "stage1 lane extraction agent",
        "model_or_agent_identity": "codex-subagent",
        "extracted_nodes": [],
        "extracted_edges": [],
        "extracted_events": [],
        "extracted_evidence": [],
        "supports_templates": [],
        "uncertainties": [],
        "rejected_candidates": [],
        "structured_failures": [],
        "output_status": "completed",
        "produced_at": "2026-06-20T00:00:00Z",
    }
    payload.update(overrides)
    return payload


def _write_merge_ready_bundle(
    graph_dir: Path,
    *,
    queue_status: str = "ready",
    required_lane_ids: list[str] | None = None,
    lane_outputs: list[dict] | None = None,
    bundle_paths: list[str] | None = None,
) -> None:
    queue = graph_dir / "intermediate" / "merge-queue.json"
    queue.parent.mkdir(parents=True, exist_ok=True)
    paths = bundle_paths or ["intermediate/reviewed-bundles/chunk-0001.json"]
    queue.write_text(
        json.dumps(
            {
                "status": queue_status,
                "bundle_paths": paths,
                "required_lane_ids": required_lane_ids
                if required_lane_ids is not None
                else ["entities_resources"],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    bundle = graph_dir / "intermediate" / "reviewed-bundles" / "chunk-0001.json"
    bundle.parent.mkdir(parents=True, exist_ok=True)
    bundle.write_text(
        json.dumps(
            {
                "chunk_id": "chunk-0001",
                "source_range": [0, 12],
                "lane_outputs": lane_outputs
                if lane_outputs is not None
                else [_valid_embedded_lane_output()],
                "review_findings": [],
                "errors": [],
                "ready_for_merge": True,
                "reviewer_status": "passed",
                "lane_output_paths": [
                    "intermediate/lane-outputs/chunk-0001/entities_resources/run-001.json"
                ],
                "normalized_nodes": [],
                "normalized_edges": [],
                "normalized_events": [],
                "normalized_evidence": [],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


@pytest.fixture
def graph_dir_without_agent_outputs(graph_dir):
    return graph_dir


@pytest.fixture
def graph_dir_with_reviewed_outputs(graph_dir):
    _write_merge_ready_bundle(graph_dir)
    return graph_dir


@pytest.fixture
def config_with_graphify_success(config):
    config["graphify_adapter"] = {
        "mode": "cli",
        "input_strategy": "canonical-graph-or-graph-dir-only",
        "failure_policy": "blocking",
        "command": [
            sys.executable,
            "-c",
            (
                "import pathlib,sys; "
                "canonical=pathlib.Path(sys.argv[1]); "
                "out=pathlib.Path(sys.argv[2]); "
                "out.mkdir(parents=True, exist_ok=True); "
                "(out/'GRAPH_REPORT.md').write_text('# Graph Report\\n' + canonical.read_text(encoding='utf-8')[:1], encoding='utf-8'); "
                "(out/'graph.html').write_text('<!doctype html><title>graph</title>', encoding='utf-8')"
            ),
            "{canonical_graph}",
            "{output_dir}",
        ],
        "timeout_seconds": 5,
    }
    return config


def test_stage1_does_not_import_template_aware_semantic_extractor():
    import inspect
    import storygraph_lib.stage1 as stage1

    source = inspect.getsource(stage1)
    assert "extract_template_aware_supplements" not in source
    assert "template_aware" not in source


def test_prepare_stage1_writes_task_packets_but_no_canonical_graph(
    novel, template_dir, graph_dir, config
):
    from storygraph_lib.stage1 import prepare_stage1

    result = prepare_stage1(
        source_path=novel,
        template_dir=template_dir,
        graph_dir=graph_dir,
        config=config,
    )

    assert result["status"] == "prepared"
    assert (graph_dir / "intermediate" / "task-packets").exists()
    assert (graph_dir / "coverage" / "chunk-ledger.json").exists()
    assert (graph_dir / "coverage" / "agent-run-ledger.json").exists()
    assert not (graph_dir / "graphify-out" / "graph.json").exists()


def test_ingest_stage1_requires_agent_template_requirements_before_lane_merge(
    graph_dir, config
):
    from storygraph_lib.stage1 import ingest_stage1

    result = ingest_stage1(graph_dir=graph_dir, config=config)

    assert result["status"] == "failed"
    assert result["error"]["code"] == "template_requirements_missing"


def test_ingest_stage1_writes_reviewed_chunk_bundle_from_reviewed_agent_artifacts(
    graph_dir,
    config,
    write_agent_template_requirements,
    write_lane_output,
    write_review_finding,
):
    from storygraph_lib.stage1 import ingest_stage1

    write_agent_template_requirements(graph_dir)
    write_lane_output(
        graph_dir,
        chunk_id="chunk-0001",
        lane_id="entities_resources",
        status="completed",
    )
    write_review_finding(graph_dir, status="passed")

    result = ingest_stage1(graph_dir=graph_dir, config=config)

    assert result["status"] == "ingested"
    assert (graph_dir / "intermediate" / "reviewed-bundles" / "chunk-0001.json").exists()
    assert (graph_dir / "intermediate" / "merge-queue.json").exists()
    assert not (graph_dir / "graphify-out" / "graph.json").exists()


def test_ingest_stage1_rejects_reviewer_status_outside_config(
    graph_dir, config, write_agent_template_requirements, write_lane_output, write_review_finding
):
    import json
    from storygraph_lib.stage1 import ingest_stage1

    assert "closed" not in config["status_enums"]["reviewer_statuses"]
    write_agent_template_requirements(graph_dir)
    write_lane_output(graph_dir, status="completed")
    write_review_finding(graph_dir, status="closed")

    result = ingest_stage1(graph_dir=graph_dir, config=config)

    assert result["status"] == "failed"
    assert "closed" in json.dumps(result, ensure_ascii=False)
    assert not (graph_dir / "intermediate" / "merge-queue.json").exists()


def test_ingest_stage1_keeps_chunk_validation_errors_local_to_each_chunk(
    graph_dir,
    config,
    write_agent_template_requirements,
    write_lane_output,
    write_review_finding,
):
    from storygraph_lib.stage1 import ingest_stage1

    write_agent_template_requirements(graph_dir)
    chunk_ledger = graph_dir / "coverage" / "chunk-ledger.json"
    chunk_ledger.parent.mkdir(parents=True, exist_ok=True)
    chunk_ledger.write_text(
        json.dumps(
            [
                {
                    "chunk_id": "chunk-0001",
                    "source_path": "mini_novel.txt",
                    "source_range": [0, 6],
                    "chapter_hint": "第一章",
                    "hash": "chunk-1",
                    "scanned_at": None,
                    "processor": "storygraph-stage1",
                    "extraction_status": "pending_agent_outputs",
                    "failure": None,
                    "retry_count": 0,
                    "target_lane_ids": ["entities_resources"],
                    "required_lane_ids": ["entities_resources"],
                    "lane_statuses": {"entities_resources": "pending_agent_outputs"},
                },
                {
                    "chunk_id": "chunk-0002",
                    "source_path": "mini_novel.txt",
                    "source_range": [6, 12],
                    "chapter_hint": "第一章",
                    "hash": "chunk-2",
                    "scanned_at": None,
                    "processor": "storygraph-stage1",
                    "extraction_status": "pending_agent_outputs",
                    "failure": None,
                    "retry_count": 0,
                    "target_lane_ids": ["entities_resources"],
                    "required_lane_ids": ["entities_resources"],
                    "lane_statuses": {"entities_resources": "pending_agent_outputs"},
                },
            ],
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    write_lane_output(
        graph_dir,
        chunk_id="chunk-0002",
        lane_id="entities_resources",
        status="completed",
    )
    write_review_finding(
        graph_dir,
        chunk_id="chunk-0002",
        lane_id="entities_resources",
        status="passed",
    )

    result = ingest_stage1(graph_dir=graph_dir, config=config)

    assert result["status"] == "failed"
    assert "required_lane_missing" in result["validation_errors"]
    assert (graph_dir / "intermediate" / "reviewed-bundles" / "chunk-0002.json").exists()


def test_merge_stage1_fails_when_required_lane_output_missing(graph_dir, config):
    from storygraph_lib.stage1 import merge_stage1

    result = merge_stage1(graph_dir=graph_dir, config=config)

    assert result["status"] == "failed"
    assert "required_lane_missing" in result["validation_errors"]


def test_graphify_adapter_does_not_produce_semantic_success_without_agent_outputs(
    graph_dir_without_agent_outputs,
    config_with_graphify_success,
):
    from storygraph_lib.stage1 import merge_stage1

    result = merge_stage1(
        graph_dir=graph_dir_without_agent_outputs,
        config=config_with_graphify_success,
    )

    assert result["status"] == "failed"
    assert "missing_reviewed_agent_outputs" in result["validation_errors"]


def test_graphify_failure_degrades_visualization_when_policy_allows(
    graph_dir_with_reviewed_outputs, config
):
    from storygraph_lib.stage1 import merge_stage1

    config["graphify_adapter"] = {
        "mode": "cli",
        "input_strategy": "canonical-graph-or-graph-dir-only",
        "failure_policy": "degrade-visualization-and-query",
        "command": [sys.executable, "-c", "raise SystemExit(7)", "{canonical_graph}", "{output_dir}"],
        "timeout_seconds": 5,
    }

    result = merge_stage1(graph_dir=graph_dir_with_reviewed_outputs, config=config)

    assert result["status"] in {"success", "warning"}
    assert "graphify_degraded" in result["warnings"]
    ledger = json.loads(
        (graph_dir_with_reviewed_outputs / "coverage" / "agent-run-ledger.json").read_text(
            encoding="utf-8"
        )
    )
    adapter_records = [
        record for record in ledger if record.get("run_id") == "stage1-graphify-adapter"
    ]
    assert adapter_records
    adapter_record = adapter_records[-1]
    assert not (
        adapter_record["status"] == "completed"
        and adapter_record["warnings"] == []
        and adapter_record["errors"] == []
    )
    failure_detail = json.dumps(
        {
            "warnings": adapter_record["warnings"],
            "errors": adapter_record["errors"],
        },
        ensure_ascii=False,
    )
    assert "graphify_failed" in failure_detail


def test_stage1_success_path_ignores_source_as_graphify_semantic_base(
    novel,
    template_dir,
    graph_dir_with_reviewed_outputs,
    config_with_graphify_success,
):
    import json

    from storygraph_lib.stage1 import merge_stage1

    merge = merge_stage1(
        graph_dir=graph_dir_with_reviewed_outputs,
        config=config_with_graphify_success,
    )

    assert merge["status"] in {"success", "warning"}
    graph = json.loads(
        (graph_dir_with_reviewed_outputs / "graphify-out" / "graph.json").read_text(
            encoding="utf-8"
        )
    )
    assert graph["metadata"]["semantic_generation"] == "agent-produced"
    assert (
        graph["metadata"]["graphify_input_strategy"]
        == "canonical-graph-or-graph-dir-only"
    )
    assert "source_semantic_base_graph" not in graph["metadata"]


def test_merge_stage1_rejects_reviewed_bundle_missing_required_lane(graph_dir, config):
    import json
    from storygraph_lib.stage1 import merge_stage1

    queue = graph_dir / "intermediate" / "merge-queue.json"
    queue.parent.mkdir(parents=True, exist_ok=True)
    queue.write_text(json.dumps({
        "status": "ready",
        "bundle_paths": ["intermediate/reviewed-bundles/chunk-0001.json"],
        "required_lane_ids": ["entities_resources"],
    }), encoding="utf-8")

    bundle = graph_dir / "intermediate" / "reviewed-bundles" / "chunk-0001.json"
    bundle.parent.mkdir(parents=True, exist_ok=True)
    bundle.write_text(json.dumps({
        "chunk_id": "chunk-0001",
        "source_range": [0, 6],
        "lane_outputs": [],
        "review_findings": [],
        "errors": [],
        "ready_for_merge": True,
        "reviewer_status": "passed",
        "lane_output_paths": [],
        "normalized_nodes": [],
        "normalized_edges": [],
        "normalized_events": [],
        "normalized_evidence": [],
    }), encoding="utf-8")

    result = merge_stage1(graph_dir=graph_dir, config=config)

    assert result["status"] == "failed"
    assert "required_lane_missing" in result["validation_errors"]
    assert not (graph_dir / "graphify-out" / "graph.json").exists()


def test_merge_stage1_rejects_queue_that_clears_config_required_lanes(graph_dir, config):
    from storygraph_lib.stage1 import merge_stage1

    _write_merge_ready_bundle(graph_dir, required_lane_ids=[], lane_outputs=[])

    result = merge_stage1(graph_dir=graph_dir, config=config)

    assert result["status"] == "failed"
    assert set(result["validation_errors"]) & {"required_lane_missing", "merge_queue_invalid"}
    assert not (graph_dir / "graphify-out" / "graph.json").exists()


def test_merge_stage1_rejects_queue_that_replaces_required_lane_with_optional_lane(
    graph_dir, config
):
    from storygraph_lib.stage1 import merge_stage1

    config["element_lanes"].append(
        {
            "lane_id": "optional_notes",
            "agent_role": "可选备注抽取 agent",
            "required": False,
            "schema": "lane-output.schema.json",
            "status_enum_ref": "status_enums.lane_output_statuses",
        }
    )
    _write_merge_ready_bundle(
        graph_dir,
        required_lane_ids=["optional_notes"],
        lane_outputs=[
            _valid_embedded_lane_output(
                task_packet_id="chunk-0001:optional_notes:attempt-001",
                lane_id="optional_notes",
                agent_role="可选备注抽取 agent",
            )
        ],
    )

    result = merge_stage1(graph_dir=graph_dir, config=config)

    assert result["status"] == "failed"
    assert set(result["validation_errors"]) & {"required_lane_missing", "merge_queue_invalid"}
    assert not (graph_dir / "graphify-out" / "graph.json").exists()


def test_merge_stage1_rejects_forged_reviewed_bundle_lane_output(graph_dir, config):
    from storygraph_lib.stage1 import merge_stage1

    _write_merge_ready_bundle(
        graph_dir,
        lane_outputs=[
            {
                "chunk_id": "chunk-0001",
                "lane_id": "entities_resources",
                "output_status": "completed",
            }
        ],
    )

    result = merge_stage1(graph_dir=graph_dir, config=config)

    assert result["status"] == "failed"
    assert "lane_output_invalid" in result["validation_errors"]
    assert not (graph_dir / "graphify-out" / "graph.json").exists()


def test_merge_stage1_rejects_merge_queue_not_ready(graph_dir, config):
    from storygraph_lib.stage1 import merge_stage1

    _write_merge_ready_bundle(graph_dir, queue_status="pending")

    result = merge_stage1(graph_dir=graph_dir, config=config)

    assert result["status"] == "failed"
    assert "merge_queue_not_ready" in result["validation_errors"]
    assert not (graph_dir / "graphify-out" / "graph.json").exists()


def test_merge_stage1_rejects_invalid_bundle_path_in_queue(graph_dir, config):
    from storygraph_lib.stage1 import merge_stage1

    _write_merge_ready_bundle(
        graph_dir,
        bundle_paths=[
            "intermediate/reviewed-bundles/chunk-0001.json",
            "../outside.json",
        ],
    )

    result = merge_stage1(graph_dir=graph_dir, config=config)

    assert result["status"] == "failed"
    assert "merge_queue_invalid" in result["validation_errors"]
    assert not (graph_dir / "graphify-out" / "graph.json").exists()


def test_stage1_merge_success_uses_reviewed_agent_outputs(
    novel,
    template_dir,
    graph_dir,
    config,
    write_agent_template_requirements,
    write_lane_output,
    write_review_finding,
):
    from storygraph_lib.stage1 import ingest_stage1, merge_stage1, prepare_stage1

    prepare_stage1(
        source_path=novel,
        template_dir=template_dir,
        graph_dir=graph_dir,
        config=config,
    )
    write_agent_template_requirements(graph_dir)
    write_lane_output(
        graph_dir,
        chunk_id="chunk-0001",
        lane_id="entities_resources",
        status="completed",
    )
    write_review_finding(graph_dir, status="passed")

    ingest = ingest_stage1(graph_dir=graph_dir, config=config)
    merge = merge_stage1(graph_dir=graph_dir, config=config)

    assert ingest["status"] == "ingested"
    assert merge["status"] == "success"
    graph = json.loads((graph_dir / "graphify-out" / "graph.json").read_text(encoding="utf-8"))
    assert graph["metadata"]["semantic_generation"] == "agent-produced"


def test_build_stage1_cli_returns_pending_when_agent_outputs_missing(
    capsys, novel, template_dir, graph_dir
):
    from storygraph_lib.cli import main

    code = main(
        [
            "build-stage1",
            "--source",
            str(novel),
            "--template-dir",
            str(template_dir),
            "--graph-dir",
            str(graph_dir),
        ]
    )

    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["status"] in {"prepared", "pending_agent_outputs"}
    assert payload["next_action"] == "run_agent_task_packets"
    assert not (graph_dir / "graphify-out" / "graph.json").exists()


def test_prepare_stage1_writes_chunk_text_under_configured_artifact_dir(
    novel, template_dir, graph_dir, config
):
    from storygraph_lib.stage1 import prepare_stage1

    config["stage1_artifacts"]["chunk_text_dir"] = "intermediate/chunk-text"

    prepare_stage1(
        source_path=novel,
        template_dir=template_dir,
        graph_dir=graph_dir,
        config=config,
    )

    assert (graph_dir / "intermediate" / "chunk-text" / "chunk-0001.txt").exists()


def test_prepare_stage1_pending_ledger_does_not_mark_agent_runs_completed(
    novel, template_dir, graph_dir, config
):
    from storygraph_lib.stage1 import prepare_stage1

    prepare_stage1(
        source_path=novel,
        template_dir=template_dir,
        graph_dir=graph_dir,
        config=config,
    )

    ledger = json.loads(
        (graph_dir / "coverage" / "agent-run-ledger.json").read_text(encoding="utf-8")
    )
    assert ledger
    assert {record["status"] for record in ledger} == {"pending"}
    assert all(record.get("finished_at") is None for record in ledger if "finished_at" in record)
    assert all(record.get("ended_at") is None for record in ledger if "ended_at" in record)
