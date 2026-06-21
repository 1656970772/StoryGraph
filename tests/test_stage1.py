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


def _template_requirement(template_name: str, template_file: str | None = None) -> dict:
    return {
        "template_name": template_name,
        "template_file": template_file or f"templates/{template_name}模板.md",
        "required_fields": ["字段"],
        "required_tables": [],
        "required_cards": [],
        "required_case_patterns": [],
        "required_evidence_fields": ["原文位置"],
        "graph_node_mapping": ["node"],
        "graph_event_mapping": ["event"],
        "graph_relation_mapping": ["relation"],
        "coverage_rules": {
            "requirement_statuses": ["covered", "needs_review", "not_found_in_source"]
        },
    }


def _write_template_requirement_parts(graph_dir: Path) -> list[dict]:
    packets = [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(
            (graph_dir / "intermediate" / "task-packets" / "template-requirements").glob(
                "batch-*.json"
            )
        )
    ]
    for packet in packets:
        part_path = graph_dir / Path(*packet["output_path"].split("/"))
        part_path.parent.mkdir(parents=True, exist_ok=True)
        part_path.write_text(
            json.dumps(
                {
                    "templates": [
                        _template_requirement(item["template_name"], item["template_file"])
                        for item in packet["template_inventory"]
                    ]
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
    return packets


def _template_requirements_summary(template_names: list[str], *, note: str = "pass") -> dict:
    return {
        "schema_version": "storygraph.template-requirements-summary.v1",
        "source_template_count": len(template_names),
        "summary_passes": 3,
        "categories": [
            {
                "category_id": "general",
                "category_name": "通用抽取要求",
                "purpose": "归纳所有模板的共同抽取目标。",
                "required_extraction_targets": ["人物", "事件", "证据"],
                "evidence_requirements": ["原文位置", "判断依据"],
                "graph_mapping_summary": {
                    "nodes": ["character"],
                    "events": ["event"],
                    "relations": ["related_to"],
                },
                "template_coverage": template_names,
            }
        ],
        "global_rules": {
            "requirement_statuses": ["covered", "needs_review", "not_found_in_source"]
        },
        "refinement_notes": [note],
        "source_coverage": {
            "template_names": template_names,
            "covered_template_count": len(template_names),
        },
    }


def _write_refinement_pass(graph_dir: Path, pass_number: int, payload: dict) -> None:
    path = (
        graph_dir
        / "intermediate"
        / "template-requirements-refinement"
        / f"pass-{pass_number}.json"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _enable_template_requirements_refinement(config: dict) -> None:
    config["stage1_artifacts"]["raw_template_requirements"] = (
        "intermediate/template-requirements-raw.json"
    )
    config["stage1_artifacts"]["template_requirements_refinement_dir"] = (
        "intermediate/template-requirements-refinement"
    )
    config["template_requirements_refinement"] = {
        "enabled": True,
        "passes": 3,
        "agent_roles": [
            "template-requirements-refine-pass-1-agent",
            "template-requirements-refine-pass-2-agent",
            "template-requirements-refine-pass-3-agent",
        ],
        "summary_schema": "template-requirements-summary.schema.json",
    }
    config["writer_policy"]["managed_outputs"].extend(
        [
            "intermediate/template-requirements-raw.json",
            "intermediate/template-requirements-refinement/*.json",
        ]
    )


def _write_five_chapter_novel(path: Path) -> Path:
    path.write_text(
        "\n".join(
            [
                "第一章\n韩立获得小瓶。",
                "第二章\n韩立进入坊市。",
                "第三章\n韩立遭遇敌人。",
                "第四章\n韩立炼制丹药。",
                "第五章\n韩立返回洞府。",
            ]
        ),
        encoding="utf-8",
    )
    return path


def _three_required_lanes() -> list[dict]:
    return [
        {
            "lane_id": "characters",
            "agent_role": "character-element-agent",
            "required": True,
            "schema": "lane-output.schema.json",
        },
        {
            "lane_id": "events",
            "agent_role": "event-element-agent",
            "required": True,
            "schema": "lane-output.schema.json",
        },
        {
            "lane_id": "relations",
            "agent_role": "relation-element-agent",
            "required": True,
            "schema": "lane-output.schema.json",
        },
    ]


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


def test_prepare_stage1_writes_template_requirements_agent_task_packets(
    novel, template_dir, graph_dir, config
):
    from storygraph_lib.stage1 import prepare_stage1

    config["stage1_artifacts"]["task_packet_dir"] = "custom/task-packets"
    config["stage1_artifacts"][
        "template_requirements_part_dir"
    ] = "custom/template-requirements-parts"
    config["writer_policy"]["managed_outputs"].append(
        "custom/template-requirements-parts/*.json"
    )
    config["template_requirements_strategy"] = {
        "mode": "auto-from-templates",
        "agent_role": "template-requirements-analysis-agent",
        "lane_id": "template_requirements",
        "schema": "template-requirements.schema.json",
        "templates_per_packet": 3,
        "allow_manual_overrides": True,
        "python_validate_only": True,
    }
    for index in range(2, 7):
        (template_dir / f"模板{index}模板.md").write_text(
            f"# 模板{index}模板\n## 字段\n- 字段{index}",
            encoding="utf-8",
        )

    result = prepare_stage1(
        source_path=novel,
        template_dir=template_dir,
        graph_dir=graph_dir,
        config=config,
    )

    assert result["status"] == "prepared"
    task_packet_paths = [
        graph_dir
        / "custom"
        / "task-packets"
        / "template-requirements"
        / f"batch-{index:04d}.json"
        for index in (1, 2)
    ]
    assert all(path.exists() for path in task_packet_paths)
    packets = [
        json.loads(path.read_text(encoding="utf-8")) for path in task_packet_paths
    ]
    assert [packet["batch_id"] for packet in packets] == ["batch-0001", "batch-0002"]
    assert [len(packet["template_inventory"]) for packet in packets] == [3, 3]
    assert packets[0]["stage"] == "stage1"
    assert packets[0]["lane_id"] == "template_requirements"
    assert packets[0]["agent_role"] == "template-requirements-analysis-agent"
    assert packets[0]["source_path"] == str(novel.resolve())
    assert packets[0]["allowed_output_schema"] == "template-requirements.schema.json"
    assert packets[0]["relevant_template_requirements"] == {
        "path": "requirements/template-requirements.json",
    }
    assert packets[0]["lane_contract"]["output_path"] == (
        "custom/template-requirements-parts/batch-0001.json"
    )
    assert packets[0]["output_path"] == (
        "custom/template-requirements-parts/batch-0001.json"
    )
    assert packets[0]["write_scope"] == [
        "custom/template-requirements-parts/batch-0001.json"
    ]
    assert packets[0]["chunk_ids"] == ["chunk-0001"]
    assert packets[0]["template_names"] == [
        item["template_name"] for item in packets[0]["template_inventory"]
    ]

    ledger = json.loads(
        (graph_dir / "coverage" / "agent-run-ledger.json").read_text(encoding="utf-8")
    )
    template_runs = [
        record
        for record in ledger
        if record["run_id"].startswith("stage1-template-requirements:")
    ]
    assert [record["run_id"] for record in template_runs] == [
        "stage1-template-requirements:batch-0001",
        "stage1-template-requirements:batch-0002",
    ]
    assert template_runs[0]["prompt_or_input_packet"] == (
        "custom/task-packets/template-requirements/batch-0001.json"
    )
    assert template_runs[0]["input_paths"][0] == (
        "custom/task-packets/template-requirements/batch-0001.json"
    )
    assert template_runs[0]["output_paths"] == [
        "custom/template-requirements-parts/batch-0001.json"
    ]
    assert template_runs[0]["write_scope"] == [
        "custom/template-requirements-parts/batch-0001.json"
    ]


def test_prepare_stage1_uses_configured_template_requirements_strategy(
    novel, template_dir, graph_dir, config
):
    from storygraph_lib.stage1 import prepare_stage1

    config["template_requirements_strategy"] = {
        "mode": "auto-from-templates",
        "allow_manual_overrides": True,
        "python_validate_only": True,
        "agent_role": "custom-template-agent",
        "lane_id": "custom_template_requirements",
        "schema": "custom-template.schema.json",
        "templates_per_packet": 5,
    }

    result = prepare_stage1(
        source_path=novel,
        template_dir=template_dir,
        graph_dir=graph_dir,
        config=config,
    )

    assert result["status"] == "prepared"
    packet = json.loads(
        (
            graph_dir
            / "intermediate"
            / "task-packets"
            / "template-requirements"
            / "batch-0001.json"
        ).read_text(encoding="utf-8")
    )
    assert packet["agent_role"] == "custom-template-agent"
    assert packet["lane_id"] == "custom_template_requirements"
    assert packet["allowed_output_schema"] == "custom-template.schema.json"
    assert "producer" not in packet["relevant_template_requirements"]
    assert packet["lane_contract"]["agent_role"] == "custom-template-agent"
    assert packet["lane_contract"]["lane_id"] == "custom_template_requirements"
    assert packet["lane_contract"]["schema"] == "custom-template.schema.json"

    ledger = json.loads(
        (graph_dir / "coverage" / "agent-run-ledger.json").read_text(encoding="utf-8")
    )
    template_run = next(
        record
        for record in ledger
        if record["run_id"] == "stage1-template-requirements:batch-0001"
    )
    assert template_run["agent_role"] == packet["agent_role"]
    assert template_run["lane_id"] == packet["lane_id"]
    assert template_run["chunk_id"] == packet["chunk_id"]
    assert template_run["attempt"] == packet["attempt"]


def test_prepare_stage1_writes_agent_dispatch_plan(
    novel, template_dir, graph_dir, config
):
    from storygraph_lib.stage1 import prepare_stage1

    config["agent_policy"] = {"max_parallel": 4}
    result = prepare_stage1(
        source_path=novel,
        template_dir=template_dir,
        graph_dir=graph_dir,
        config=config,
    )

    dispatch_path = graph_dir / "intermediate" / "agent-dispatch-plan.json"
    dispatch = json.loads(dispatch_path.read_text(encoding="utf-8"))

    assert result["status"] == "prepared"
    assert result["next_action"] == "dispatch_template_requirements_agents"
    assert result["agent_dispatch"]["dispatch_plan_path"] == (
        "intermediate/agent-dispatch-plan.json"
    )
    assert result["agent_dispatch"]["max_parallel"] == config["agent_policy"]["max_parallel"]
    assert [phase["phase"] for phase in dispatch["phases"]] == [
        "template_requirements",
        "lane_extraction",
        "review",
    ]
    assert dispatch["phases"][0]["next_action"] == "dispatch_template_requirements_agents"
    assert dispatch["phases"][0]["task_packets"][0]["output_path"] == (
        "intermediate/template-requirements-parts/batch-0001.json"
    )
    assert dispatch["phases"][1]["next_action"] == "dispatch_lane_agents"
    assert dispatch["phases"][1]["task_packets"][0]["task_packet_path"].startswith(
        "intermediate/task-packets/chunk-0001/"
    )
    assert dispatch["phases"][2]["next_action"] == "dispatch_reviewer_agents"
    assert dispatch["phases"][2]["review_findings_path"] == "coverage/review-findings.json"


def test_prepare_stage1_adds_sequential_template_requirements_refinement_phase(
    novel, template_dir, graph_dir, config
):
    from storygraph_lib.stage1 import next_agent_batches, prepare_stage1

    _enable_template_requirements_refinement(config)
    result = prepare_stage1(
        source_path=novel,
        template_dir=template_dir,
        graph_dir=graph_dir,
        config=config,
    )
    dispatch = json.loads(
        (graph_dir / "intermediate" / "agent-dispatch-plan.json").read_text(
            encoding="utf-8"
        )
    )

    assert result["next_action"] == "dispatch_template_requirements_agents"
    assert [phase["phase"] for phase in dispatch["phases"]] == [
        "template_requirements",
        "template_requirements_refinement",
        "lane_extraction",
        "review",
    ]
    refinement_phase = dispatch["phases"][1]
    assert refinement_phase["next_action"] == "dispatch_template_requirements_refinement_agents"
    assert [batch["batch_id"] for batch in refinement_phase["execution_batches"]] == [
        "template-requirements-refinement-pass-1",
        "template-requirements-refinement-pass-2",
        "template-requirements-refinement-pass-3",
    ]

    first = next_agent_batches(
        graph_dir=graph_dir, phase="template_requirements_refinement", limit=3
    )
    assert first["returned_count"] == 1
    assert first["batches"][0]["expected_output_paths"] == [
        "intermediate/template-requirements-refinement/pass-1.json"
    ]

    _write_refinement_pass(
        graph_dir,
        1,
        _template_requirements_summary(["法宝分析"], note="pass 1"),
    )
    second = next_agent_batches(
        graph_dir=graph_dir, phase="template_requirements_refinement", limit=3
    )
    assert second["returned_count"] == 1
    assert second["batches"][0]["expected_output_paths"] == [
        "intermediate/template-requirements-refinement/pass-2.json"
    ]


def test_default_config_prepares_one_comprehensive_packet_per_chunk(
    tmp_path, template_dir, graph_dir
):
    from storygraph_lib.stage1 import prepare_stage1

    default_config_path = (
        Path(__file__).resolve().parents[1]
        / "skill-src"
        / "storygraph"
        / "config"
        / "storygraph.default.json"
    )
    config = json.loads(default_config_path.read_text(encoding="utf-8"))
    config["template_count_policy"]["expected_existing_templates"] = 1
    config["template_count_policy"]["enforce_integration_count"] = False
    novel = _write_five_chapter_novel(tmp_path / "five_chapters.txt")

    result = prepare_stage1(
        source_path=novel,
        template_dir=template_dir,
        graph_dir=graph_dir,
        config=config,
    )
    dispatch = json.loads(
        (graph_dir / "intermediate" / "agent-dispatch-plan.json").read_text(
            encoding="utf-8"
        )
    )
    lane_phase = next(phase for phase in dispatch["phases"] if phase["phase"] == "lane_extraction")

    assert result["status"] == "prepared"
    assert [phase["phase"] for phase in dispatch["phases"]] == [
        "template_requirements",
        "template_requirements_refinement",
        "lane_extraction",
    ]
    refinement_phase = next(
        phase
        for phase in dispatch["phases"]
        if phase["phase"] == "template_requirements_refinement"
    )
    assert len(refinement_phase["execution_batches"]) == 3
    assert len(lane_phase["task_packets"]) == 5
    assert {
        packet["lane_id"] for packet in lane_phase["task_packets"]
    } == {"comprehensive_extraction"}
    assert len(lane_phase["execution_batches"]) == 3
    assert [batch["chunk_ids"] for batch in lane_phase["execution_batches"]] == [
        ["chunk-0001", "chunk-0002"],
        ["chunk-0003", "chunk-0004"],
        ["chunk-0005"],
    ]
    assert [
        path
        for batch in lane_phase["execution_batches"]
        for path in batch["expected_output_paths"]
    ] == [
        f"intermediate/lane-outputs/chunk-000{index}/comprehensive_extraction/run-001.json"
        for index in range(1, 6)
    ]


def test_default_config_large_corpus_batches_are_chunks_not_chunks_times_lanes(
    tmp_path, template_dir, graph_dir
):
    from storygraph_lib.stage1 import prepare_stage1

    default_config_path = (
        Path(__file__).resolve().parents[1]
        / "skill-src"
        / "storygraph"
        / "config"
        / "storygraph.default.json"
    )
    config = json.loads(default_config_path.read_text(encoding="utf-8"))
    config["template_count_policy"]["expected_existing_templates"] = 1
    config["template_count_policy"]["enforce_integration_count"] = False
    config["chunk_strategy"]["overlap_chars"] = 0
    novel = tmp_path / "many_chapters.txt"
    novel.write_text(
        "\n".join(f"第{index}章\n韩立记录第{index}段。" for index in range(1, 2453)),
        encoding="utf-8",
    )

    result = prepare_stage1(
        source_path=novel,
        template_dir=template_dir,
        graph_dir=graph_dir,
        config=config,
    )
    dispatch = json.loads(
        (graph_dir / "intermediate" / "agent-dispatch-plan.json").read_text(
            encoding="utf-8"
        )
    )
    lane_phase = next(phase for phase in dispatch["phases"] if phase["phase"] == "lane_extraction")
    output_paths = [
        path
        for batch in lane_phase["execution_batches"]
        for path in batch["expected_output_paths"]
    ]

    assert result["status"] == "prepared"
    assert len(lane_phase["task_packets"]) == 2452
    assert len(output_paths) == len(set(output_paths)) == 2452
    assert len(lane_phase["execution_batches"]) == 1226
    assert output_paths[0] == (
        "intermediate/lane-outputs/chunk-0001/comprehensive_extraction/run-001.json"
    )
    assert output_paths[-1] == (
        "intermediate/lane-outputs/chunk-2452/comprehensive_extraction/run-001.json"
    )


def test_prepare_stage1_groups_lane_execution_batches_by_configured_chunk_count(
    tmp_path, template_dir, graph_dir, config
):
    from storygraph_lib.stage1 import prepare_stage1

    novel = _write_five_chapter_novel(tmp_path / "five_chapters.txt")
    config["element_lanes"] = _three_required_lanes()
    config["agent_orchestration"] = {
        "lane_batch_strategy": "by-lane-contiguous-chunks",
        "lane_chunks_per_agent": 2,
        "max_parallel_agents": 4,
    }

    result = prepare_stage1(
        source_path=novel,
        template_dir=template_dir,
        graph_dir=graph_dir,
        config=config,
    )
    dispatch = json.loads(
        (graph_dir / "intermediate" / "agent-dispatch-plan.json").read_text(
            encoding="utf-8"
        )
    )
    lane_phase = next(phase for phase in dispatch["phases"] if phase["phase"] == "lane_extraction")
    batches = lane_phase["execution_batches"]

    assert result["agent_dispatch"]["max_parallel"] == 4
    assert len(lane_phase["task_packets"]) == 15
    assert len(batches) == 9
    assert {
        lane_id: len([batch for batch in batches if batch["lane_id"] == lane_id])
        for lane_id in ["characters", "events", "relations"]
    } == {"characters": 3, "events": 3, "relations": 3}
    assert batches[0]["batch_id"] == "lane-characters-batch-0001"
    assert batches[0]["chunk_ids"] == ["chunk-0001", "chunk-0002"]
    assert len(batches[0]["task_packet_paths"]) == 2
    assert len(batches[0]["expected_output_paths"]) == 2
    assert batches[0]["write_scope"] == batches[0]["expected_output_paths"]


def test_lane_execution_batches_expected_outputs_cover_task_packets_once(
    tmp_path, template_dir, graph_dir, config
):
    from storygraph_lib.stage1 import prepare_stage1

    novel = _write_five_chapter_novel(tmp_path / "five_chapters.txt")
    config["element_lanes"] = _three_required_lanes()
    config["agent_orchestration"] = {
        "lane_batch_strategy": "by-lane-contiguous-chunks",
        "lane_chunks_per_agent": 2,
    }

    prepare_stage1(
        source_path=novel,
        template_dir=template_dir,
        graph_dir=graph_dir,
        config=config,
    )
    dispatch = json.loads(
        (graph_dir / "intermediate" / "agent-dispatch-plan.json").read_text(
            encoding="utf-8"
        )
    )
    lane_phase = next(phase for phase in dispatch["phases"] if phase["phase"] == "lane_extraction")
    task_paths = [
        packet["task_packet_path"] for packet in lane_phase["task_packets"]
    ]
    batch_task_paths = [
        path
        for batch in lane_phase["execution_batches"]
        for path in batch["task_packet_paths"]
    ]
    batch_output_paths = [
        path
        for batch in lane_phase["execution_batches"]
        for path in batch["expected_output_paths"]
    ]

    assert sorted(batch_task_paths) == sorted(task_paths)
    assert len(batch_task_paths) == len(set(batch_task_paths)) == 15
    assert len(batch_output_paths) == len(set(batch_output_paths)) == 15
    assert all(
        path.startswith("intermediate/lane-outputs/") and path.endswith("/run-001.json")
        for path in batch_output_paths
    )


def test_next_agent_batches_returns_only_pending_batches(
    tmp_path, template_dir, graph_dir, config
):
    from storygraph_lib.stage1 import next_agent_batches, prepare_stage1

    novel = _write_five_chapter_novel(tmp_path / "five_chapters.txt")
    config["element_lanes"] = _three_required_lanes()
    config["agent_orchestration"] = {
        "lane_batch_strategy": "by-lane-contiguous-chunks",
        "lane_chunks_per_agent": 2,
    }
    prepare_stage1(
        source_path=novel,
        template_dir=template_dir,
        graph_dir=graph_dir,
        config=config,
    )
    first = next_agent_batches(graph_dir=graph_dir, phase="lane_extraction", limit=1)
    for output_path in first["batches"][0]["expected_output_paths"]:
        path = graph_dir / Path(*output_path.split("/"))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}", encoding="utf-8")

    result = next_agent_batches(graph_dir=graph_dir, phase="lane_extraction", limit=2)

    assert result["status"] == "pending_agent_batches"
    assert result["pending_count"] == 8
    assert result["returned_count"] == 2
    assert first["batches"][0]["batch_id"] not in [
        batch["batch_id"] for batch in result["batches"]
    ]


def test_claim_agent_batches_uses_sliding_window_dispatch_state(
    tmp_path, template_dir, graph_dir, config
):
    from storygraph_lib.stage1 import claim_agent_batches, prepare_stage1

    novel = _write_five_chapter_novel(tmp_path / "five_chapters.txt")
    config["element_lanes"] = _three_required_lanes()
    config["agent_orchestration"] = {
        "lane_batch_strategy": "by-lane-contiguous-chunks",
        "lane_chunks_per_agent": 2,
        "max_parallel_agents": 6,
    }
    prepare_stage1(
        source_path=novel,
        template_dir=template_dir,
        graph_dir=graph_dir,
        config=config,
    )

    first = claim_agent_batches(graph_dir=graph_dir, phase="lane_extraction", limit=6)
    second = claim_agent_batches(graph_dir=graph_dir, phase="lane_extraction", limit=6)

    assert first["status"] == "agent_batches_claimed"
    assert first["phase"] == "lane_extraction"
    assert first["claimed_count"] == 6
    assert first["in_flight_count"] == 6
    assert first["available_slots"] == 6
    assert first["pending_count"] == 3
    assert first["completed_count"] == 0
    assert len(first["batches"]) == 6
    assert second["claimed_count"] == 0
    assert second["in_flight_count"] == 6
    assert second["available_slots"] == 0
    assert second["pending_count"] == 3
    assert second["batches"] == []

    first_batch = first["batches"][0]
    _write_batch_outputs(graph_dir, first_batch)

    third = claim_agent_batches(graph_dir=graph_dir, phase="lane_extraction", limit=1)

    assert third["claimed_count"] == 1
    assert third["in_flight_count"] == 6
    assert third["available_slots"] == 1
    assert third["pending_count"] == 2
    assert third["completed_count"] == 1
    assert third["batches"][0]["batch_id"] not in {
        batch["batch_id"] for batch in first["batches"]
    }

    partial_batch = first["batches"][1]
    partial_path = graph_dir / Path(*partial_batch["expected_output_paths"][0].split("/"))
    partial_path.parent.mkdir(parents=True, exist_ok=True)
    partial_path.write_text("{}", encoding="utf-8")

    partial = claim_agent_batches(graph_dir=graph_dir, phase="lane_extraction", limit=6)

    assert partial["claimed_count"] == 0
    assert partial["in_flight_count"] == 6
    assert partial["pending_count"] == 2
    assert partial["completed_count"] == 1

    known_batches = {
        batch["batch_id"]: batch for batch in [*first["batches"], *third["batches"]]
    }
    for batch in known_batches.values():
        _write_batch_outputs(graph_dir, batch)

    fourth = claim_agent_batches(graph_dir=graph_dir, phase="lane_extraction", limit=6)
    for batch in fourth["batches"]:
        known_batches[batch["batch_id"]] = batch
        _write_batch_outputs(graph_dir, batch)

    final = claim_agent_batches(graph_dir=graph_dir, phase="lane_extraction", limit=6)

    assert final["claimed_count"] == 0
    assert final["in_flight_count"] == 0
    assert final["pending_count"] == 0
    assert final["completed_count"] == 9
    state = json.loads(
        (graph_dir / "intermediate" / "agent-dispatch-state.json").read_text(
            encoding="utf-8"
        )
    )
    lane_state = state["phases"]["lane_extraction"]["batches"]
    assert {item["status"] for item in lane_state.values()} == {"completed"}


def test_claim_agent_batches_reclaims_stale_completed_state_when_outputs_are_missing(
    novel, template_dir, graph_dir, config
):
    from storygraph_lib.stage1 import claim_agent_batches, prepare_stage1

    prepare_stage1(
        source_path=novel,
        template_dir=template_dir,
        graph_dir=graph_dir,
        config=config,
    )
    dispatch_path = graph_dir / "intermediate" / "agent-dispatch-plan.json"
    dispatch = json.loads(dispatch_path.read_text(encoding="utf-8"))
    batch = dispatch["phases"][1]["execution_batches"][0]
    state_path = graph_dir / "intermediate" / "agent-dispatch-state.json"
    state_path.write_text(
        json.dumps(
            {
                "schema_version": "storygraph.agent-dispatch-state.v1",
                "stage": "stage1",
                "phases": {
                    "lane_extraction": {
                        "batches": {
                            batch["batch_id"]: {
                                "batch_id": batch["batch_id"],
                                "phase": "lane_extraction",
                                "status": "completed",
                                "expected_output_paths": batch["expected_output_paths"],
                                "task_packet_paths": batch["task_packet_paths"],
                            }
                        }
                    }
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = claim_agent_batches(graph_dir=graph_dir, phase="lane_extraction", limit=1)

    assert result["status"] == "agent_batches_claimed"
    assert result["claimed_count"] == 1
    assert result["in_flight_count"] == 1
    assert result["pending_count"] == 0
    assert result["completed_count"] == 0
    assert result["batches"][0]["batch_id"] == batch["batch_id"]
    assert not (graph_dir / Path(*batch["expected_output_paths"][0].split("/"))).exists()


def test_claim_agent_batches_fails_closed_for_unsafe_expected_output_paths(
    novel, template_dir, graph_dir, config
):
    from storygraph_lib.stage1 import claim_agent_batches, prepare_stage1

    prepare_stage1(
        source_path=novel,
        template_dir=template_dir,
        graph_dir=graph_dir,
        config=config,
    )
    dispatch_path = graph_dir / "intermediate" / "agent-dispatch-plan.json"
    dispatch = json.loads(dispatch_path.read_text(encoding="utf-8"))
    batch = dispatch["phases"][1]["execution_batches"][0]
    batch["expected_output_paths"] = ["../escape.json"]
    batch["write_scope"] = ["../escape.json"]
    dispatch_path.write_text(json.dumps(dispatch, ensure_ascii=False), encoding="utf-8")

    result = claim_agent_batches(graph_dir=graph_dir, phase="lane_extraction", limit=1)

    assert result["status"] == "failed"
    assert result["error"]["code"] == "dispatch_batch_path_invalid"
    assert "unmanaged_output:../escape.json" in result["validation_errors"]
    assert not (graph_dir / "intermediate" / "agent-dispatch-state.json").exists()


def test_claim_agent_batches_fails_closed_for_unsafe_dispatch_state_path(graph_dir):
    from storygraph_lib.stage1 import claim_agent_batches

    dispatch_path = graph_dir / "intermediate" / "agent-dispatch-plan.json"
    task_packet_path = (
        graph_dir
        / "intermediate"
        / "task-packets"
        / "chunk-0001"
        / "comprehensive_extraction.json"
    )
    dispatch_path.parent.mkdir(parents=True, exist_ok=True)
    task_packet_path.parent.mkdir(parents=True, exist_ok=True)
    task_packet_path.write_text("{}", encoding="utf-8")
    safe_output_path = (
        "intermediate/lane-outputs/chunk-0001/comprehensive_extraction/run-001.json"
    )
    dispatch_path.write_text(
        json.dumps(
            {
                "stage": "stage1",
                "max_parallel": 1,
                "dispatch_state_path": "../escape.json",
                "phases": [
                    {
                        "phase": "lane_extraction",
                        "execution_batches": [
                            {
                                "batch_id": "batch-0001",
                                "phase": "lane_extraction",
                                "expected_output_paths": [safe_output_path],
                                "task_packet_paths": [
                                    "intermediate/task-packets/chunk-0001/comprehensive_extraction.json"
                                ],
                                "write_scope": [safe_output_path],
                            }
                        ],
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = claim_agent_batches(graph_dir=graph_dir, phase="lane_extraction", limit=1)

    assert result["status"] == "failed"
    assert result["error"]["code"] in {
        "dispatch_state_path_invalid",
        "dispatch_state_invalid",
    }
    assert "unmanaged_output:../escape.json" in result["validation_errors"]
    assert not (graph_dir.parent / "escape.json").exists()


def _write_batch_outputs(graph_dir: Path, batch: dict) -> None:
    for output_path in batch["expected_output_paths"]:
        path = graph_dir / Path(*output_path.split("/"))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}", encoding="utf-8")


def test_ingest_stage1_requires_agent_template_requirements_before_lane_merge(
    graph_dir, config
):
    from storygraph_lib.stage1 import ingest_stage1

    result = ingest_stage1(graph_dir=graph_dir, config=config)

    assert result["status"] == "failed"
    assert result["error"]["code"] == "template_requirements_missing"


def test_ingest_template_requirements_does_not_require_lane_outputs_or_reviews(
    novel,
    template_dir,
    graph_dir,
    config,
):
    from storygraph_lib.stage1 import ingest_template_requirements, prepare_stage1

    prepare_stage1(
        source_path=novel,
        template_dir=template_dir,
        graph_dir=graph_dir,
        config=config,
    )
    _write_template_requirement_parts(graph_dir)

    result = ingest_template_requirements(graph_dir=graph_dir, config=config)

    assert result["status"] == "requirements_ingested"
    requirements = json.loads(
        (graph_dir / "requirements" / "template-requirements.json").read_text(
            encoding="utf-8"
        )
    )
    assert [item["template_name"] for item in requirements["templates"]] == ["法宝分析"]
    assert not (graph_dir / "intermediate" / "merge-queue.json").exists()


def test_ingest_template_requirements_writes_raw_then_finalizes_pass_three_summary(
    novel,
    template_dir,
    graph_dir,
    config,
):
    from storygraph_lib.stage1 import ingest_template_requirements, prepare_stage1

    _enable_template_requirements_refinement(config)
    prepare_stage1(
        source_path=novel,
        template_dir=template_dir,
        graph_dir=graph_dir,
        config=config,
    )
    _write_template_requirement_parts(graph_dir)

    first = ingest_template_requirements(graph_dir=graph_dir, config=config)

    assert first["status"] == "requirements_refinement_pending"
    assert first["next_action"] == "dispatch_template_requirements_refinement_agents"
    raw = json.loads(
        (graph_dir / "intermediate" / "template-requirements-raw.json").read_text(
            encoding="utf-8"
        )
    )
    assert [item["template_name"] for item in raw["templates"]] == ["法宝分析"]
    assert not (graph_dir / "requirements" / "template-requirements.json").exists()

    _write_refinement_pass(
        graph_dir,
        1,
        _template_requirements_summary(["法宝分析"], note="pass 1"),
    )
    _write_refinement_pass(
        graph_dir,
        2,
        _template_requirements_summary(["法宝分析"], note="pass 2"),
    )
    final_summary = _template_requirements_summary(["法宝分析"], note="pass 3")
    _write_refinement_pass(graph_dir, 3, final_summary)

    second = ingest_template_requirements(graph_dir=graph_dir, config=config)

    assert second["status"] == "requirements_ingested"
    requirements = json.loads(
        (graph_dir / "requirements" / "template-requirements.json").read_text(
            encoding="utf-8"
        )
    )
    assert requirements["refinement_notes"] == ["pass 3"]
    assert requirements["categories"][0]["template_coverage"] == ["法宝分析"]


def test_ingest_template_requirements_rejects_refinement_summary_with_missing_template(
    novel,
    template_dir,
    graph_dir,
    config,
):
    from storygraph_lib.stage1 import ingest_template_requirements, prepare_stage1

    _enable_template_requirements_refinement(config)
    (template_dir / "人物关系模板.md").write_text(
        "# 人物关系模板\n## 字段\n- 人物", encoding="utf-8"
    )
    prepare_stage1(
        source_path=novel,
        template_dir=template_dir,
        graph_dir=graph_dir,
        config=config,
    )
    _write_template_requirement_parts(graph_dir)
    first = ingest_template_requirements(graph_dir=graph_dir, config=config)
    assert first["status"] == "requirements_refinement_pending"

    _write_refinement_pass(
        graph_dir,
        1,
        _template_requirements_summary(["法宝分析"], note="pass 1"),
    )
    _write_refinement_pass(
        graph_dir,
        2,
        _template_requirements_summary(["法宝分析"], note="pass 2"),
    )
    _write_refinement_pass(
        graph_dir,
        3,
        _template_requirements_summary(["法宝分析"], note="pass 3"),
    )

    result = ingest_template_requirements(graph_dir=graph_dir, config=config)

    assert result["status"] == "failed"
    assert result["error"]["code"] == "template_requirements_summary_invalid"
    assert (
        "template_requirements_summary_missing_expected_template:人物关系"
        in result["validation_errors"]
    )
    assert not (graph_dir / "requirements" / "template-requirements.json").exists()


def test_ingest_stage1_aggregates_template_requirements_parts_before_lane_merge(
    novel,
    template_dir,
    graph_dir,
    config,
    write_lane_output,
    write_review_finding,
):
    from storygraph_lib.stage1 import ingest_stage1, prepare_stage1

    config["template_requirements_strategy"] = {
        "agent_role": "template-requirements-analysis-agent",
        "lane_id": "template_requirements",
        "schema": "template-requirements.schema.json",
        "templates_per_packet": 3,
        "allow_manual_overrides": True,
        "python_validate_only": True,
    }
    for index in range(2, 7):
        (template_dir / f"模板{index}模板.md").write_text(
            f"# 模板{index}模板\n## 字段\n- 字段{index}",
            encoding="utf-8",
        )
    prepare_stage1(
        source_path=novel,
        template_dir=template_dir,
        graph_dir=graph_dir,
        config=config,
    )
    _write_template_requirement_parts(graph_dir)
    write_lane_output(graph_dir, status="completed")
    write_review_finding(graph_dir, status="passed")

    result = ingest_stage1(graph_dir=graph_dir, config=config)

    assert result["status"] == "ingested"
    requirements = json.loads(
        (graph_dir / "requirements" / "template-requirements.json").read_text(
            encoding="utf-8"
        )
    )
    assert "producer" not in requirements
    assert [item["template_name"] for item in requirements["templates"]] == [
        "模板2",
        "模板3",
        "模板4",
        "模板5",
        "模板6",
        "法宝分析",
    ]


def test_ingest_stage1_ignores_existing_requirements_and_requires_parts(
    novel,
    template_dir,
    graph_dir,
    config,
    write_lane_output,
    write_review_finding,
):
    from storygraph_lib.stage1 import ingest_stage1, prepare_stage1

    config["template_requirements_strategy"] = {
        "agent_role": "template-requirements-analysis-agent",
        "lane_id": "template_requirements",
        "schema": "template-requirements.schema.json",
        "templates_per_packet": 3,
        "allow_manual_overrides": True,
        "python_validate_only": True,
    }
    for index in range(2, 7):
        (template_dir / f"模板{index}模板.md").write_text(
            f"# 模板{index}模板\n## 字段\n- 字段{index}",
            encoding="utf-8",
        )
    prepare_stage1(
        source_path=novel,
        template_dir=template_dir,
        graph_dir=graph_dir,
        config=config,
    )
    requirements_path = graph_dir / "requirements" / "template-requirements.json"
    requirements_path.parent.mkdir(parents=True, exist_ok=True)
    requirements_path.write_text(
        json.dumps(
            {
                "templates": [
                    _template_requirement("法宝分析", "templates/法宝分析模板.md")
                ],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    write_lane_output(graph_dir, status="completed")
    write_review_finding(graph_dir, status="passed")

    result = ingest_stage1(graph_dir=graph_dir, config=config)

    assert result["status"] == "failed"
    assert result["error"]["code"] == "template_requirements_part_missing"
    assert "template_requirements_part_missing" in result["validation_errors"]


def test_ingest_stage1_fails_closed_when_template_requirement_packet_file_swapped(
    novel,
    template_dir,
    graph_dir,
    config,
    write_lane_output,
    write_review_finding,
):
    from storygraph_lib.stage1 import ingest_stage1, prepare_stage1

    config["template_requirements_strategy"] = {
        "agent_role": "template-requirements-analysis-agent",
        "lane_id": "template_requirements",
        "schema": "template-requirements.schema.json",
        "templates_per_packet": 3,
        "allow_manual_overrides": True,
        "python_validate_only": True,
    }
    for index in range(2, 7):
        (template_dir / f"模板{index}模板.md").write_text(
            f"# 模板{index}模板\n## 字段\n- 字段{index}",
            encoding="utf-8",
        )
    prepare_stage1(
        source_path=novel,
        template_dir=template_dir,
        graph_dir=graph_dir,
        config=config,
    )
    _write_template_requirement_parts(graph_dir)
    packet_dir = graph_dir / "intermediate" / "task-packets" / "template-requirements"
    first_packet = packet_dir / "batch-0001.json"
    second_packet = packet_dir / "batch-0002.json"
    first_content = first_packet.read_text(encoding="utf-8")
    second_content = second_packet.read_text(encoding="utf-8")
    first_packet.write_text(second_content, encoding="utf-8")
    second_packet.write_text(first_content, encoding="utf-8")
    write_lane_output(graph_dir, status="completed")
    write_review_finding(graph_dir, status="passed")

    result = ingest_stage1(graph_dir=graph_dir, config=config)

    assert result["status"] == "failed"
    assert result["error"]["code"] == "template_requirements_part_invalid"
    assert "template_requirements_task_packet_path_mismatch:batch-0002" in result["validation_errors"]
    assert "template_requirements_task_packet_filename_mismatch:batch-0002" in result["validation_errors"]
    assert not (graph_dir / "requirements" / "template-requirements.json").exists()


def test_ingest_stage1_fails_closed_when_template_requirement_part_missing(
    novel,
    template_dir,
    graph_dir,
    config,
):
    from storygraph_lib.stage1 import ingest_stage1, prepare_stage1

    config["template_requirements_strategy"] = {
        "agent_role": "template-requirements-analysis-agent",
        "lane_id": "template_requirements",
        "schema": "template-requirements.schema.json",
        "templates_per_packet": 3,
        "allow_manual_overrides": True,
        "python_validate_only": True,
    }
    for index in range(2, 7):
        (template_dir / f"模板{index}模板.md").write_text(
            f"# 模板{index}模板\n## 字段\n- 字段{index}",
            encoding="utf-8",
        )
    prepare_stage1(
        source_path=novel,
        template_dir=template_dir,
        graph_dir=graph_dir,
        config=config,
    )
    packets = _write_template_requirement_parts(graph_dir)
    missing_part = graph_dir / Path(*packets[-1]["output_path"].split("/"))
    missing_part.unlink()

    result = ingest_stage1(graph_dir=graph_dir, config=config)

    assert result["status"] == "failed"
    assert result["error"]["code"] == "template_requirements_part_missing"
    assert "template_requirements_part_missing" in result["validation_errors"]
    assert not (graph_dir / "requirements" / "template-requirements.json").exists()


def test_ingest_stage1_fails_closed_when_template_requirement_part_invalid(
    novel,
    template_dir,
    graph_dir,
    config,
):
    from storygraph_lib.stage1 import ingest_stage1, prepare_stage1

    config["template_requirements_strategy"] = {
        "agent_role": "template-requirements-analysis-agent",
        "lane_id": "template_requirements",
        "schema": "template-requirements.schema.json",
        "templates_per_packet": 3,
        "allow_manual_overrides": True,
        "python_validate_only": True,
    }
    for index in range(2, 7):
        (template_dir / f"模板{index}模板.md").write_text(
            f"# 模板{index}模板\n## 字段\n- 字段{index}",
            encoding="utf-8",
        )
    prepare_stage1(
        source_path=novel,
        template_dir=template_dir,
        graph_dir=graph_dir,
        config=config,
    )
    packets = _write_template_requirement_parts(graph_dir)
    invalid_part = graph_dir / Path(*packets[0]["output_path"].split("/"))
    invalid_part.write_text(
        json.dumps({"producer": "python-template-parser", "templates": []}),
        encoding="utf-8",
    )

    result = ingest_stage1(graph_dir=graph_dir, config=config)

    assert result["status"] == "failed"
    assert result["error"]["code"] == "template_requirements_part_invalid"
    assert "template_requirements_not_agent_produced" in result["validation_errors"]
    assert not (graph_dir / "requirements" / "template-requirements.json").exists()


def test_ingest_stage1_fails_closed_when_template_requirement_ledger_output_path_unsafe(
    novel,
    template_dir,
    graph_dir,
    config,
):
    from storygraph_lib.stage1 import ingest_stage1, prepare_stage1

    config["template_requirements_strategy"] = {
        "agent_role": "template-requirements-analysis-agent",
        "lane_id": "template_requirements",
        "schema": "template-requirements.schema.json",
        "templates_per_packet": 3,
        "allow_manual_overrides": True,
        "python_validate_only": True,
    }
    for index in range(2, 7):
        (template_dir / f"模板{index}模板.md").write_text(
            f"# 模板{index}模板\n## 字段\n- 字段{index}",
            encoding="utf-8",
        )
    prepare_stage1(
        source_path=novel,
        template_dir=template_dir,
        graph_dir=graph_dir,
        config=config,
    )
    _write_template_requirement_parts(graph_dir)
    ledger_path = graph_dir / "coverage" / "agent-run-ledger.json"
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    template_run = next(
        record
        for record in ledger
        if record["run_id"] == "stage1-template-requirements:batch-0001"
    )
    template_run["output_paths"] = ["../escape.json"]
    template_run["write_scope"] = ["../escape.json"]
    ledger_path.write_text(json.dumps(ledger, ensure_ascii=False, indent=2), encoding="utf-8")

    result = ingest_stage1(graph_dir=graph_dir, config=config)

    assert result["status"] == "failed"
    assert result["error"]["code"] == "template_requirements_part_invalid"
    assert "unmanaged_output:../escape.json" in result["validation_errors"]
    assert not (graph_dir / "requirements" / "template-requirements.json").exists()


def test_ingest_stage1_fails_closed_when_template_requirement_ledger_batch_missing(
    novel,
    template_dir,
    graph_dir,
    config,
):
    from storygraph_lib.stage1 import ingest_stage1, prepare_stage1

    config["template_requirements_strategy"] = {
        "agent_role": "template-requirements-analysis-agent",
        "lane_id": "template_requirements",
        "schema": "template-requirements.schema.json",
        "templates_per_packet": 3,
        "allow_manual_overrides": True,
        "python_validate_only": True,
    }
    for index in range(2, 7):
        (template_dir / f"模板{index}模板.md").write_text(
            f"# 模板{index}模板\n## 字段\n- 字段{index}",
            encoding="utf-8",
        )
    prepare_stage1(
        source_path=novel,
        template_dir=template_dir,
        graph_dir=graph_dir,
        config=config,
    )
    _write_template_requirement_parts(graph_dir)
    ledger_path = graph_dir / "coverage" / "agent-run-ledger.json"
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    ledger = [
        record
        for record in ledger
        if record.get("run_id") != "stage1-template-requirements:batch-0002"
    ]
    ledger_path.write_text(json.dumps(ledger, ensure_ascii=False, indent=2), encoding="utf-8")

    result = ingest_stage1(graph_dir=graph_dir, config=config)

    assert result["status"] == "failed"
    assert result["error"]["code"] == "template_requirements_part_invalid"
    assert "template_requirements_ledger_batch_mismatch" in result["validation_errors"]
    assert not (graph_dir / "requirements" / "template-requirements.json").exists()


def test_ingest_stage1_fails_closed_when_template_requirement_batch_sequence_has_gap(
    novel,
    template_dir,
    graph_dir,
    config,
    write_lane_output,
    write_review_finding,
):
    from storygraph_lib.stage1 import ingest_stage1, prepare_stage1

    config["template_requirements_strategy"] = {
        "agent_role": "template-requirements-analysis-agent",
        "lane_id": "template_requirements",
        "schema": "template-requirements.schema.json",
        "templates_per_packet": 2,
        "allow_manual_overrides": True,
        "python_validate_only": True,
    }
    for index in range(2, 7):
        (template_dir / f"模板{index}模板.md").write_text(
            f"# 模板{index}模板\n## 字段\n- 字段{index}",
            encoding="utf-8",
        )
    prepare_stage1(
        source_path=novel,
        template_dir=template_dir,
        graph_dir=graph_dir,
        config=config,
    )
    _write_template_requirement_parts(graph_dir)
    (
        graph_dir
        / "intermediate"
        / "task-packets"
        / "template-requirements"
        / "batch-0002.json"
    ).unlink()
    (graph_dir / "intermediate" / "template-requirements-parts" / "batch-0002.json").unlink()
    ledger_path = graph_dir / "coverage" / "agent-run-ledger.json"
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    ledger = [
        record
        for record in ledger
        if record.get("run_id") != "stage1-template-requirements:batch-0002"
    ]
    ledger_path.write_text(json.dumps(ledger, ensure_ascii=False, indent=2), encoding="utf-8")
    write_lane_output(graph_dir, status="completed")
    write_review_finding(graph_dir, status="passed")

    result = ingest_stage1(graph_dir=graph_dir, config=config)

    assert result["status"] == "failed"
    assert result["error"]["code"] == "template_requirements_part_invalid"
    assert "template_requirements_batch_sequence_invalid" in result["validation_errors"]
    assert not (graph_dir / "requirements" / "template-requirements.json").exists()


def test_ingest_stage1_fails_closed_when_template_requirement_ledger_duplicates_batch_output(
    novel,
    template_dir,
    graph_dir,
    config,
):
    from storygraph_lib.stage1 import ingest_stage1, prepare_stage1

    config["template_requirements_strategy"] = {
        "agent_role": "template-requirements-analysis-agent",
        "lane_id": "template_requirements",
        "schema": "template-requirements.schema.json",
        "templates_per_packet": 3,
        "allow_manual_overrides": True,
        "python_validate_only": True,
    }
    for index in range(2, 7):
        (template_dir / f"模板{index}模板.md").write_text(
            f"# 模板{index}模板\n## 字段\n- 字段{index}",
            encoding="utf-8",
        )
    prepare_stage1(
        source_path=novel,
        template_dir=template_dir,
        graph_dir=graph_dir,
        config=config,
    )
    _write_template_requirement_parts(graph_dir)
    ledger_path = graph_dir / "coverage" / "agent-run-ledger.json"
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    template_runs = [
        record
        for record in ledger
        if record["run_id"].startswith("stage1-template-requirements:")
    ]
    template_runs[1]["output_paths"] = list(template_runs[0]["output_paths"])
    template_runs[1]["write_scope"] = list(template_runs[0]["write_scope"])
    template_runs[1]["assigned_template_names"] = list(
        template_runs[0]["assigned_template_names"]
    )
    ledger_path.write_text(json.dumps(ledger, ensure_ascii=False, indent=2), encoding="utf-8")

    result = ingest_stage1(graph_dir=graph_dir, config=config)

    assert result["status"] == "failed"
    assert result["error"]["code"] == "template_requirements_part_invalid"
    assert "template_requirements_packet_ledger_mismatch:batch-0002" in result["validation_errors"]
    assert not (graph_dir / "requirements" / "template-requirements.json").exists()


def test_ingest_stage1_fails_closed_when_template_requirement_write_scope_overbroad(
    novel,
    template_dir,
    graph_dir,
    config,
):
    from storygraph_lib.stage1 import ingest_stage1, prepare_stage1

    config["template_requirements_strategy"] = {
        "agent_role": "template-requirements-analysis-agent",
        "lane_id": "template_requirements",
        "schema": "template-requirements.schema.json",
        "templates_per_packet": 3,
        "allow_manual_overrides": True,
        "python_validate_only": True,
    }
    for index in range(2, 7):
        (template_dir / f"模板{index}模板.md").write_text(
            f"# 模板{index}模板\n## 字段\n- 字段{index}",
            encoding="utf-8",
        )
    prepare_stage1(
        source_path=novel,
        template_dir=template_dir,
        graph_dir=graph_dir,
        config=config,
    )
    _write_template_requirement_parts(graph_dir)

    packet_path = (
        graph_dir
        / "intermediate"
        / "task-packets"
        / "template-requirements"
        / "batch-0001.json"
    )
    packet = json.loads(packet_path.read_text(encoding="utf-8"))
    packet["write_scope"] = [
        packet["output_path"],
        "requirements/template-requirements.json",
    ]
    packet_path.write_text(json.dumps(packet, ensure_ascii=False, indent=2), encoding="utf-8")

    ledger_path = graph_dir / "coverage" / "agent-run-ledger.json"
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    template_run = next(
        record
        for record in ledger
        if record["run_id"] == "stage1-template-requirements:batch-0001"
    )
    template_run["write_scope"] = [
        template_run["output_paths"][0],
        "requirements/template-requirements.json",
    ]
    ledger_path.write_text(json.dumps(ledger, ensure_ascii=False, indent=2), encoding="utf-8")

    result = ingest_stage1(graph_dir=graph_dir, config=config)

    assert result["status"] == "failed"
    assert result["error"]["code"] == "template_requirements_part_invalid"
    assert "template_requirements_task_packet_write_scope_mismatch:batch-0001" in result[
        "validation_errors"
    ]
    assert "template_requirements_ledger_write_scope_mismatch:batch-0001" in result[
        "validation_errors"
    ]
    assert not (graph_dir / "requirements" / "template-requirements.json").exists()


def test_ingest_stage1_fails_closed_when_template_requirement_batch_has_too_many_templates(
    novel,
    template_dir,
    graph_dir,
    config,
):
    from storygraph_lib.stage1 import ingest_stage1, prepare_stage1

    config["template_requirements_strategy"] = {
        "agent_role": "template-requirements-analysis-agent",
        "lane_id": "template_requirements",
        "schema": "template-requirements.schema.json",
        "templates_per_packet": 5,
        "allow_manual_overrides": True,
        "python_validate_only": True,
    }
    for index in range(2, 8):
        (template_dir / f"模板{index}模板.md").write_text(
            f"# 模板{index}模板\n## 字段\n- 字段{index}",
            encoding="utf-8",
        )
    prepare_stage1(
        source_path=novel,
        template_dir=template_dir,
        graph_dir=graph_dir,
        config=config,
    )

    packet_dir = graph_dir / "intermediate" / "task-packets" / "template-requirements"
    first_packet_path = packet_dir / "batch-0001.json"
    second_packet_path = packet_dir / "batch-0002.json"
    first_packet = json.loads(first_packet_path.read_text(encoding="utf-8"))
    second_packet = json.loads(second_packet_path.read_text(encoding="utf-8"))
    assert len(first_packet["template_names"]) == 5
    assert len(second_packet["template_names"]) == 2

    moved_template = second_packet["template_inventory"].pop(0)
    second_packet["template_names"].remove(moved_template["template_name"])
    first_packet["template_inventory"].append(moved_template)
    first_packet["template_names"].append(moved_template["template_name"])
    first_packet_path.write_text(
        json.dumps(first_packet, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    second_packet_path.write_text(
        json.dumps(second_packet, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    ledger_path = graph_dir / "coverage" / "agent-run-ledger.json"
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    for record in ledger:
        if record.get("run_id") == "stage1-template-requirements:batch-0001":
            record["assigned_template_names"] = list(first_packet["template_names"])
        if record.get("run_id") == "stage1-template-requirements:batch-0002":
            record["assigned_template_names"] = list(second_packet["template_names"])
    ledger_path.write_text(json.dumps(ledger, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_template_requirement_parts(graph_dir)

    result = ingest_stage1(graph_dir=graph_dir, config=config)

    assert result["status"] == "failed"
    assert result["error"]["code"] == "template_requirements_part_invalid"
    assert "template_requirements_task_packet_template_count_invalid:batch-0001" in result[
        "validation_errors"
    ]
    assert "template_requirements_task_packet_template_inventory_count_invalid:batch-0001" in result[
        "validation_errors"
    ]
    assert "template_requirements_ledger_template_count_invalid:batch-0001" in result[
        "validation_errors"
    ]
    assert not (graph_dir / "requirements" / "template-requirements.json").exists()


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


def test_ingest_stage1_accepts_refined_template_requirements_summary(
    graph_dir,
    config,
    write_lane_output,
    write_review_finding,
):
    from storygraph_lib.stage1 import ingest_stage1

    requirements_path = graph_dir / "requirements" / "template-requirements.json"
    requirements_path.parent.mkdir(parents=True, exist_ok=True)
    requirements_path.write_text(
        json.dumps(
            _template_requirements_summary(["法宝分析"], note="pass 3"),
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
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


def test_ingest_stage1_allows_unreviewed_outputs_in_post_merge_incremental_mode(
    graph_dir,
    config,
    write_agent_template_requirements,
    write_lane_output,
):
    from storygraph_lib.stage1 import ingest_stage1

    config["review_policy"] = {
        "mode": "post_merge_incremental",
        "require_review_before_canonical_merge": False,
        "unreviewed_merge_status": "unreviewed_usable",
    }
    write_agent_template_requirements(graph_dir)
    write_lane_output(
        graph_dir,
        chunk_id="chunk-0001",
        lane_id="entities_resources",
        status="completed",
    )

    result = ingest_stage1(graph_dir=graph_dir, config=config)

    assert result["status"] == "ingested"
    bundle = json.loads(
        (graph_dir / "intermediate" / "reviewed-bundles" / "chunk-0001.json").read_text(
            encoding="utf-8"
        )
    )
    assert bundle["merge_gate_status"] == "unreviewed_usable"
    assert bundle["review_state"] == "unreviewed_usable"
    assert bundle.get("reviewer_status") != "passed"
    queue = json.loads(
        (graph_dir / "intermediate" / "merge-queue.json").read_text(encoding="utf-8")
    )
    assert queue["review_policy_mode"] == "post_merge_incremental"
    assert queue["review_state_summary"] == {"unreviewed_usable": 1}


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
    _write_template_requirement_parts(graph_dir)
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


def test_stage1_merge_success_records_unreviewed_post_merge_status(
    novel,
    template_dir,
    graph_dir,
    config,
    write_lane_output,
):
    from storygraph_lib.stage1 import ingest_stage1, merge_stage1, prepare_stage1

    config["review_policy"] = {
        "mode": "post_merge_incremental",
        "require_review_before_canonical_merge": False,
        "unreviewed_merge_status": "unreviewed_usable",
    }
    prepare_stage1(
        source_path=novel,
        template_dir=template_dir,
        graph_dir=graph_dir,
        config=config,
    )
    _write_template_requirement_parts(graph_dir)
    write_lane_output(
        graph_dir,
        chunk_id="chunk-0001",
        lane_id="entities_resources",
        status="completed",
    )

    ingest = ingest_stage1(graph_dir=graph_dir, config=config)
    merge = merge_stage1(graph_dir=graph_dir, config=config)

    assert ingest["status"] == "ingested"
    assert merge["status"] == "success"
    graph = json.loads((graph_dir / "graphify-out" / "graph.json").read_text(encoding="utf-8"))
    assert graph["metadata"]["review_policy_mode"] == "post_merge_incremental"
    assert graph["metadata"]["review_status"] == "unreviewed_usable"
    assert graph["metadata"]["unreviewed_bundle_count"] == 1


def test_stage1_incremental_attempt_uses_latest_valid_lane_output(
    graph_dir,
    config,
    write_agent_template_requirements,
    write_lane_output,
):
    from storygraph_lib.stage1 import ingest_stage1, merge_stage1

    config["review_policy"] = {
        "mode": "post_merge_incremental",
        "require_review_before_canonical_merge": False,
        "unreviewed_merge_status": "unreviewed_usable",
    }
    write_agent_template_requirements(graph_dir)
    write_lane_output(graph_dir, lane_id="entities_resources", status="completed")
    second = graph_dir / "intermediate" / "lane-outputs" / "chunk-0001" / "entities_resources" / "run-002.json"
    payload = json.loads(
        (
            graph_dir
            / "intermediate"
            / "lane-outputs"
            / "chunk-0001"
            / "entities_resources"
            / "run-001.json"
        ).read_text(encoding="utf-8")
    )
    payload["run_id"] = "run-002"
    payload["task_packet_id"] = "chunk-0001:entities_resources:attempt-002"
    payload["extracted_nodes"] = [
        {
            "id": "node:character:hanli",
            "label": "韩立",
            "node_type": "character",
            "source_range": [0, 2],
            "evidence_ids": ["evidence:hanli"],
            "supports_templates": [
                {"template_name": "法宝分析", "requirement_id": "r1", "status": "covered"}
            ],
            "confidence": "EXTRACTED",
            "verification_status": "verified",
        }
    ]
    payload["extracted_evidence"] = [
        {
            "evidence_id": "evidence:hanli",
            "source_range": [0, 2],
            "source_locator": "mini_novel.txt#char=0-2",
            "chunk_id": "chunk-0001",
            "fact_summary": "韩立出现",
            "supports_templates": [
                {"template_name": "法宝分析", "requirement_id": "r1", "status": "covered"}
            ],
            "confidence": "EXTRACTED",
            "verification_status": "verified",
        }
    ]
    second.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    ingest = ingest_stage1(graph_dir=graph_dir, config=config)
    merge = merge_stage1(graph_dir=graph_dir, config=config)

    assert ingest["status"] == "ingested"
    assert merge["status"] == "success"
    graph = json.loads((graph_dir / "graphify-out" / "graph.json").read_text(encoding="utf-8"))
    assert graph["nodes"][0]["provenance"]["lane_output_paths"] == [
        "intermediate/lane-outputs/chunk-0001/entities_resources/run-002.json"
    ]


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
    assert payload["status"] == "prepared"
    assert payload["next_action"] == "dispatch_template_requirements_agents"
    assert "pending_reason" not in payload
    assert "template_requirements_missing" not in payload.get("validation_errors", [])
    assert payload["agent_dispatch"]["dispatch_plan_path"] == (
        "intermediate/agent-dispatch-plan.json"
    )
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
