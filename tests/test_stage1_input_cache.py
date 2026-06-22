import copy
import json
from pathlib import Path


def _requirement(template_name: str, template_file: str | None = None, marker: str | None = None) -> dict:
    field = marker or template_name
    return {
        "template_name": template_name,
        "template_file": template_file or f"{template_name}模板.md",
        "required_fields": [field],
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


def _phase(dispatch: dict, phase_name: str) -> dict | None:
    return next(
        (phase for phase in dispatch["phases"] if phase.get("phase") == phase_name),
        None,
    )


def _template_packets(graph_dir: Path) -> list[dict]:
    root = graph_dir / "intermediate" / "task-packets" / "template-requirements"
    if not root.exists():
        return []
    return [
        json.loads(path.read_text(encoding="utf-8"))
        for path in sorted(root.glob("batch-*.json"))
    ]


def _lane_packet_path(graph_dir: Path) -> Path:
    return (
        graph_dir
        / "intermediate"
        / "task-packets"
        / "chunk-0001"
        / "entities_resources.json"
    )


def _lane_phase(dispatch: dict) -> dict:
    phase = _phase(dispatch, "lane_extraction")
    assert phase is not None
    return phase


def _write_requirement_parts(graph_dir: Path, markers: dict[str, str] | None = None) -> None:
    markers = markers or {}
    for packet in _template_packets(graph_dir):
        part_path = graph_dir / Path(*packet["output_path"].split("/"))
        part_path.parent.mkdir(parents=True, exist_ok=True)
        part_path.write_text(
            json.dumps(
                {
                    "template_count": len(packet["template_inventory"]),
                    "templates": [
                        _requirement(
                            item["template_name"],
                            item["template_file"],
                            markers.get(item["template_name"]),
                        )
                        for item in packet["template_inventory"]
                    ],
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )


def _prepare_and_ingest_requirements(novel, template_dir, graph_dir, config) -> None:
    from storygraph_lib.stage1 import ingest_template_requirements, prepare_stage1

    result = prepare_stage1(
        source_path=novel,
        template_dir=template_dir,
        graph_dir=graph_dir,
        config=config,
    )
    assert result["status"] == "prepared"
    _write_requirement_parts(graph_dir)
    ingest = ingest_template_requirements(graph_dir=graph_dir, config=config)
    assert ingest["status"] == "requirements_ingested"


def _enable_refinement(config: dict) -> dict:
    updated = copy.deepcopy(config)
    updated["stage1_artifacts"]["raw_template_requirements"] = (
        "intermediate/template-requirements-raw.json"
    )
    updated["stage1_artifacts"]["template_requirements_refinement_dir"] = (
        "intermediate/template-requirements-refinement"
    )
    updated["template_requirements_refinement"] = {
        "enabled": True,
        "passes": 3,
        "serial_gate": True,
        "agent_roles": [
            "template-requirements-refine-pass-1-agent",
            "template-requirements-refine-pass-2-agent",
            "template-requirements-refine-pass-3-agent",
        ],
        "summary_schema": "template-requirements-summary.schema.json",
    }
    managed = updated["writer_policy"]["managed_outputs"]
    for path in [
        "intermediate/template-requirements-raw.json",
        "intermediate/template-requirements-refinement/*.json",
        "intermediate/task-packets/template-requirements-refinement/*.json",
    ]:
        if path not in managed:
            managed.append(path)
    return updated


def _valid_refinement_summary(pass_number: int, template_names: list[str]) -> dict:
    return {
        "schema_version": "storygraph.template-requirements-summary.v1",
        "source_template_count": len(template_names),
        "summary_passes": 3,
        "categories": [
            {
                "category_id": "general",
                "category_name": "通用抽取要求",
                "purpose": f"第 {pass_number} 轮整理后的模板需求摘要。",
                "required_extraction_targets": ["法宝"],
                "evidence_requirements": ["原文位置"],
                "graph_mapping_summary": {"nodes": ["artifact"]},
                "template_coverage": template_names,
            }
        ],
        "global_rules": {
            "requirement_statuses": ["covered", "needs_review", "not_found_in_source"]
        },
        "refinement_notes": [f"pass {pass_number}"],
        "source_coverage": {
            "template_names": template_names,
            "covered_template_count": len(template_names),
        },
    }


def _write_refinement_summary(
    graph_dir: Path,
    pass_number: int,
    template_names: list[str],
    *,
    payload: dict | None = None,
) -> None:
    path = (
        graph_dir
        / "intermediate"
        / "template-requirements-refinement"
        / f"pass-{pass_number}.json"
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(
            payload
            if payload is not None
            else _valid_refinement_summary(pass_number, template_names),
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def test_template_requirements_refinement_claims_only_next_valid_pass(
    novel, template_dir, graph_dir, config
):
    from storygraph_lib.stage1 import (
        claim_agent_batches,
        ingest_template_requirements,
        prepare_stage1,
    )

    refined_config = _enable_refinement(config)
    prepare = prepare_stage1(
        source_path=novel,
        template_dir=template_dir,
        graph_dir=graph_dir,
        config=refined_config,
    )
    assert prepare["status"] == "prepared"
    _write_requirement_parts(graph_dir)
    pending = ingest_template_requirements(graph_dir=graph_dir, config=refined_config)
    assert pending["status"] == "requirements_refinement_pending"

    first = claim_agent_batches(
        graph_dir=graph_dir,
        phase="template_requirements_refinement",
        limit=3,
    )

    assert first["claimed_count"] == 1
    assert first["batches"][0]["refinement_pass"] == 1

    blocked_while_running = claim_agent_batches(
        graph_dir=graph_dir,
        phase="template_requirements_refinement",
        limit=3,
    )

    assert blocked_while_running["claimed_count"] == 0
    assert blocked_while_running["in_flight_count"] == 1

    _write_refinement_summary(graph_dir, 1, ["法宝分析"], payload={})
    invalid_previous = claim_agent_batches(
        graph_dir=graph_dir,
        phase="template_requirements_refinement",
        limit=3,
    )

    assert invalid_previous["status"] == "failed"
    assert invalid_previous["error"]["code"] == "template_requirements_refinement_previous_invalid"

    _write_refinement_summary(graph_dir, 1, ["法宝分析"])
    second = claim_agent_batches(
        graph_dir=graph_dir,
        phase="template_requirements_refinement",
        limit=3,
    )

    assert second["claimed_count"] == 1
    assert second["batches"][0]["refinement_pass"] == 2


def test_template_requirements_refinement_pass3_becomes_final_requirements(
    novel, template_dir, graph_dir, config
):
    from storygraph_lib.stage1 import ingest_template_requirements, prepare_stage1

    refined_config = _enable_refinement(config)
    prepare_stage1(
        source_path=novel,
        template_dir=template_dir,
        graph_dir=graph_dir,
        config=refined_config,
    )
    _write_requirement_parts(graph_dir)
    pending = ingest_template_requirements(graph_dir=graph_dir, config=refined_config)
    assert pending["status"] == "requirements_refinement_pending"

    for pass_number in range(1, 4):
        _write_refinement_summary(graph_dir, pass_number, ["法宝分析"])

    result = ingest_template_requirements(graph_dir=graph_dir, config=refined_config)
    requirements = json.loads(
        (graph_dir / "requirements" / "template-requirements.json").read_text(
            encoding="utf-8"
        )
    )

    assert result["status"] == "requirements_ingested"
    assert requirements["refinement_notes"] == ["pass 3"]


def test_prepare_stage1_reuses_template_requirements_when_template_md5_unchanged(
    novel, template_dir, graph_dir, config
):
    from storygraph_lib.stage1 import prepare_stage1

    _prepare_and_ingest_requirements(novel, template_dir, graph_dir, config)
    requirements_path = graph_dir / "requirements" / "template-requirements.json"
    before = requirements_path.read_text(encoding="utf-8")

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

    assert result["cache"]["template_requirements"] == "reused"
    assert _phase(dispatch, "template_requirements") is None
    assert requirements_path.read_text(encoding="utf-8") == before
    cache = json.loads(
        (graph_dir / "intermediate" / "stage1-input-cache.json").read_text(
            encoding="utf-8"
        )
    )
    assert cache["templates"][0]["md5"]
    assert cache["templates"][0]["sha256"]
    assert cache["templates"][0]["template_file"] == "法宝分析模板.md"


def test_prepare_stage1_refreshes_template_requirements_when_template_sha256_changes(
    novel, template_dir, graph_dir, config
):
    from storygraph_lib.stage1 import prepare_stage1

    _prepare_and_ingest_requirements(novel, template_dir, graph_dir, config)
    cache_path = graph_dir / "intermediate" / "stage1-input-cache.json"
    cache = json.loads(cache_path.read_text(encoding="utf-8"))
    cache["templates"][0]["sha256"] = "stale-sha256"
    cache_path.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")

    result = prepare_stage1(
        source_path=novel,
        template_dir=template_dir,
        graph_dir=graph_dir,
        config=config,
    )

    assert result["cache"]["template_requirements"] == "partial_refreshed"


def test_prepare_stage1_refreshes_missing_template_requirement_key(
    novel, template_dir, graph_dir, config
):
    from storygraph_lib.stage1 import prepare_stage1

    (template_dir / "人物分析模板.md").write_text("# 人物分析模板\n- 人物", encoding="utf-8")
    _prepare_and_ingest_requirements(novel, template_dir, graph_dir, config)
    requirements_path = graph_dir / "requirements" / "template-requirements.json"
    requirements = json.loads(requirements_path.read_text(encoding="utf-8"))
    requirements["templates"] = [
        item
        for item in requirements["templates"]
        if item["template_file"] == "法宝分析模板.md"
    ]
    requirements["template_count"] = len(requirements["templates"])
    requirements_path.write_text(
        json.dumps(requirements, ensure_ascii=False, indent=2),
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
    packets = _template_packets(graph_dir)

    assert result["cache"]["template_requirements"] == "partial_refreshed"
    assert _phase(dispatch, "template_requirements") is not None
    assert [[item["template_name"] for item in packet["template_inventory"]] for packet in packets] == [
        ["人物分析"]
    ]


def test_prepare_stage1_refreshes_duplicate_template_requirement_key(
    novel, template_dir, graph_dir, config
):
    from storygraph_lib.stage1 import prepare_stage1

    (template_dir / "人物分析模板.md").write_text("# 人物分析模板\n- 人物", encoding="utf-8")
    _prepare_and_ingest_requirements(novel, template_dir, graph_dir, config)
    requirements_path = graph_dir / "requirements" / "template-requirements.json"
    requirements = json.loads(requirements_path.read_text(encoding="utf-8"))
    duplicate = copy.deepcopy(requirements["templates"][0])
    duplicate["template_name"] = "法宝分析重复"
    requirements["templates"].append(duplicate)
    requirements["template_count"] = len(requirements["templates"])
    requirements_path.write_text(
        json.dumps(requirements, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    result = prepare_stage1(
        source_path=novel,
        template_dir=template_dir,
        graph_dir=graph_dir,
        config=config,
    )
    packets = _template_packets(graph_dir)

    assert result["cache"]["template_requirements"] == "partial_refreshed"
    assert [[item["template_name"] for item in packet["template_inventory"]] for packet in packets] == [
        ["人物分析", "法宝分析"]
    ]


def test_ingest_template_requirements_replaces_only_changed_template_by_file_key(
    novel, template_dir, graph_dir, config
):
    from storygraph_lib.stage1 import ingest_template_requirements, prepare_stage1

    (template_dir / "人物分析模板.md").write_text("# 人物分析模板\n- 人物", encoding="utf-8")
    _prepare_and_ingest_requirements(novel, template_dir, graph_dir, config)

    (template_dir / "人物分析模板.md").write_text(
        "# 人物分析模板\n- 人物\n- 新字段",
        encoding="utf-8",
    )
    result = prepare_stage1(
        source_path=novel,
        template_dir=template_dir,
        graph_dir=graph_dir,
        config=config,
    )
    packets = _template_packets(graph_dir)

    assert result["cache"]["template_requirements"] == "partial_refreshed"
    assert [[item["template_name"] for item in packet["template_inventory"]] for packet in packets] == [
        ["人物分析"]
    ]

    _write_requirement_parts(graph_dir, {"人物分析": "changed-marker"})
    ingest = ingest_template_requirements(graph_dir=graph_dir, config=config)
    requirements = json.loads(
        (graph_dir / "requirements" / "template-requirements.json").read_text(
            encoding="utf-8"
        )
    )

    assert ingest["status"] == "requirements_ingested"
    by_name = {item["template_name"]: item for item in requirements["templates"]}
    assert by_name["人物分析"]["required_fields"] == ["changed-marker"]
    assert by_name["法宝分析"]["required_fields"] == ["法宝分析"]


def test_ingest_template_requirements_appends_new_template_incrementally(
    novel, template_dir, graph_dir, config
):
    from storygraph_lib.stage1 import ingest_template_requirements, prepare_stage1

    _prepare_and_ingest_requirements(novel, template_dir, graph_dir, config)
    (template_dir / "人物分析模板.md").write_text("# 人物分析模板\n- 人物", encoding="utf-8")

    result = prepare_stage1(
        source_path=novel,
        template_dir=template_dir,
        graph_dir=graph_dir,
        config=config,
    )
    packets = _template_packets(graph_dir)

    assert result["cache"]["template_requirements"] == "partial_refreshed"
    assert [[item["template_name"] for item in packet["template_inventory"]] for packet in packets] == [
        ["人物分析"]
    ]

    _write_requirement_parts(graph_dir, {"人物分析": "new-marker"})
    ingest = ingest_template_requirements(graph_dir=graph_dir, config=config)
    requirements = json.loads(
        (graph_dir / "requirements" / "template-requirements.json").read_text(
            encoding="utf-8"
        )
    )

    assert ingest["status"] == "requirements_ingested"
    assert [item["template_name"] for item in requirements["templates"]] == [
        "人物分析",
        "法宝分析",
    ]


def test_ingest_template_requirements_removes_deleted_template_without_new_parts(
    novel, template_dir, graph_dir, config
):
    from storygraph_lib.stage1 import ingest_template_requirements, prepare_stage1

    (template_dir / "人物分析模板.md").write_text("# 人物分析模板\n- 人物", encoding="utf-8")
    _prepare_and_ingest_requirements(novel, template_dir, graph_dir, config)
    (template_dir / "人物分析模板.md").unlink()

    result = prepare_stage1(
        source_path=novel,
        template_dir=template_dir,
        graph_dir=graph_dir,
        config=config,
    )
    ingest = ingest_template_requirements(graph_dir=graph_dir, config=config)
    requirements = json.loads(
        (graph_dir / "requirements" / "template-requirements.json").read_text(
            encoding="utf-8"
        )
    )

    assert result["cache"]["template_requirements"] == "partial_refreshed"
    assert _template_packets(graph_dir) == []
    assert ingest["status"] == "requirements_ingested"
    assert [item["template_name"] for item in requirements["templates"]] == ["法宝分析"]


def test_prepare_stage1_reuses_source_flow_when_source_hash_and_chunk_artifacts_unchanged(
    novel, template_dir, graph_dir, config
):
    from storygraph_lib.stage1 import prepare_stage1

    _prepare_and_ingest_requirements(novel, template_dir, graph_dir, config)
    lane_packet_path = _lane_packet_path(graph_dir)
    lane_packet = json.loads(lane_packet_path.read_text(encoding="utf-8"))
    lane_packet["sentinel"] = "keep-existing-packet"
    lane_packet_path.write_text(
        json.dumps(lane_packet, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    result = prepare_stage1(
        source_path=novel,
        template_dir=template_dir,
        graph_dir=graph_dir,
        config=config,
    )
    reused_packet = json.loads(lane_packet_path.read_text(encoding="utf-8"))

    assert result["cache"]["source_flow"] == "reused"
    assert reused_packet["sentinel"] == "keep-existing-packet"


def test_prepare_stage1_rebuilds_source_flow_when_extraction_quality_rules_change(
    tmp_path, novel, template_dir, graph_dir, config
):
    from storygraph_lib.stage1 import prepare_stage1

    rules_path = tmp_path / "rules.md"
    rules_path.write_text("# 抽取规则\n旧规则", encoding="utf-8")
    config["agent_orchestration"] = {
        "extraction_quality_rules_path": str(rules_path),
    }
    _prepare_and_ingest_requirements(novel, template_dir, graph_dir, config)
    packet_path = _lane_packet_path(graph_dir)
    packet = json.loads(packet_path.read_text(encoding="utf-8"))
    packet["sentinel"] = "stale-rules"
    packet_path.write_text(
        json.dumps(packet, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    rules_path.write_text("# 抽取规则\n新规则", encoding="utf-8")
    result = prepare_stage1(
        source_path=novel,
        template_dir=template_dir,
        graph_dir=graph_dir,
        config=config,
    )
    rebuilt_packet = json.loads(packet_path.read_text(encoding="utf-8"))

    assert result["cache"]["source_flow"] == "refreshed"
    assert "sentinel" not in rebuilt_packet
    assert rebuilt_packet["extraction_quality_rules"] == {
        "path": str(rules_path),
        "content": "# 抽取规则\n新规则",
    }


def test_prepare_stage1_fails_closed_when_extraction_quality_rules_missing(
    tmp_path, novel, template_dir, graph_dir, config
):
    from storygraph_lib.stage1 import prepare_stage1

    config["agent_orchestration"] = {
        "extraction_quality_rules_path": str(tmp_path / "missing-rules.md"),
    }

    result = prepare_stage1(
        source_path=novel,
        template_dir=template_dir,
        graph_dir=graph_dir,
        config=config,
    )

    assert result["status"] == "failed"
    assert result["error"]["code"] == "extraction_quality_rules_unreadable"
    assert result["validation_errors"] == ["extraction_quality_rules_unreadable"]


def test_prepare_stage1_isolates_stale_lane_outputs_when_template_requirements_refresh(
    novel,
    template_dir,
    graph_dir,
    config,
    write_lane_output,
    write_review_finding,
):
    from storygraph_lib.stage1 import ingest_stage1, prepare_stage1

    (template_dir / "人物分析模板.md").write_text("# 人物分析模板\n- 人物", encoding="utf-8")
    _prepare_and_ingest_requirements(novel, template_dir, graph_dir, config)
    write_lane_output(graph_dir, status="completed")
    write_review_finding(graph_dir, status="passed")
    first_ingest = ingest_stage1(graph_dir=graph_dir, config=config)
    assert first_ingest["status"] == "ingested"

    stale_paths = [
        graph_dir
        / "intermediate"
        / "lane-outputs"
        / "chunk-0001"
        / "entities_resources"
        / "run-001.json",
        graph_dir / "intermediate" / "reviewed-bundles" / "chunk-0001.json",
        graph_dir / "intermediate" / "merge-queue.json",
    ]
    assert all(path.exists() for path in stale_paths)

    (template_dir / "人物分析模板.md").write_text(
        "# 人物分析模板\n- 人物\n- 新字段",
        encoding="utf-8",
    )
    result = prepare_stage1(
        source_path=novel,
        template_dir=template_dir,
        graph_dir=graph_dir,
        config=config,
    )
    _write_requirement_parts(graph_dir, {"人物分析": "changed-marker"})
    ingest = ingest_stage1(graph_dir=graph_dir, config=config)

    assert result["cache"]["template_requirements"] == "partial_refreshed"
    assert result["cache"]["source_flow"] == "reused"
    assert all(not path.exists() for path in stale_paths)
    assert ingest["status"] == "failed"
    assert ingest["error"]["code"] == "agent_lane_outputs_missing"


def test_prepare_stage1_delta_policy_keeps_unaffected_template_chunk_outputs(
    novel, template_dir, graph_dir, config
):
    from storygraph_lib.stage1 import prepare_stage1

    (template_dir / "人物分析模板.md").write_text("# 人物分析模板\n- 人物", encoding="utf-8")
    delta_config = copy.deepcopy(config)
    delta_config["stage1_delta_policy"] = {"scope": "changed-template-support"}
    _prepare_and_ingest_requirements(novel, template_dir, graph_dir, delta_config)

    affected_output = (
        graph_dir
        / "intermediate"
        / "lane-outputs"
        / "chunk-0001"
        / "entities_resources"
        / "run-001.json"
    )
    unaffected_output = (
        graph_dir
        / "intermediate"
        / "lane-outputs"
        / "chunk-0002"
        / "entities_resources"
        / "run-001.json"
    )
    affected_bundle = graph_dir / "intermediate" / "reviewed-bundles" / "chunk-0001.json"
    unaffected_bundle = graph_dir / "intermediate" / "reviewed-bundles" / "chunk-0002.json"
    for path in [affected_output, unaffected_output, affected_bundle, unaffected_bundle]:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("{}", encoding="utf-8")
    (graph_dir / "coverage" / "evidence-index.json").write_text(
        json.dumps(
            [
                {
                    "evidence_id": "evidence:artifact",
                    "chunk_id": "chunk-0001",
                    "supports_templates": [{"template_name": "法宝分析"}],
                },
                {
                    "evidence_id": "evidence:character",
                    "chunk_id": "chunk-0002",
                    "supports_templates": [{"template_name": "人物分析"}],
                },
            ],
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    (graph_dir / "intermediate" / "merge-queue.json").write_text(
        "{}", encoding="utf-8"
    )
    (graph_dir / "graphify-out").mkdir(exist_ok=True)
    (graph_dir / "graphify-out" / "graph.json").write_text("{}", encoding="utf-8")

    (template_dir / "法宝分析模板.md").write_text(
        "# 法宝分析模板\n- 法宝\n- 新增字段",
        encoding="utf-8",
    )
    result = prepare_stage1(
        source_path=novel,
        template_dir=template_dir,
        graph_dir=graph_dir,
        config=delta_config,
    )

    assert result["cache"]["template_requirements"] == "partial_refreshed"
    assert not affected_output.exists()
    assert not affected_bundle.exists()
    assert unaffected_output.exists()
    assert unaffected_bundle.exists()
    assert not (graph_dir / "intermediate" / "merge-queue.json").exists()
    assert not (graph_dir / "graphify-out" / "graph.json").exists()


def test_prepare_stage1_rebuilds_source_flow_when_required_evidence_policy_tampered(
    novel, template_dir, graph_dir, config
):
    from storygraph_lib.stage1 import prepare_stage1

    expected_policy = {
        "min_quote_chars": 12,
        "require_source_location": True,
    }
    config["required_evidence_policy"] = expected_policy
    _prepare_and_ingest_requirements(novel, template_dir, graph_dir, config)
    packet_path = _lane_packet_path(graph_dir)
    packet = json.loads(packet_path.read_text(encoding="utf-8"))
    packet["required_evidence_policy"] = {
        "min_quote_chars": 0,
        "require_source_location": False,
    }
    packet_path.write_text(
        json.dumps(packet, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    result = prepare_stage1(
        source_path=novel,
        template_dir=template_dir,
        graph_dir=graph_dir,
        config=config,
    )
    rebuilt_packet = json.loads(packet_path.read_text(encoding="utf-8"))

    assert result["cache"]["source_flow"] == "refreshed"
    assert rebuilt_packet["required_evidence_policy"] == expected_policy


def test_prepare_stage1_rebuilds_source_flow_when_chunk_text_hash_mismatches_ledger(
    novel, template_dir, graph_dir, config
):
    from storygraph_lib.stage1 import prepare_stage1

    _prepare_and_ingest_requirements(novel, template_dir, graph_dir, config)
    chunk_path = graph_dir / "intermediate" / "chunks" / "chunk-0001.txt"
    original_text = chunk_path.read_text(encoding="utf-8")
    chunk_path.write_text("CORRUPTED CHUNK TEXT", encoding="utf-8")

    result = prepare_stage1(
        source_path=novel,
        template_dir=template_dir,
        graph_dir=graph_dir,
        config=config,
    )

    assert result["cache"]["source_flow"] == "refreshed"
    assert chunk_path.read_text(encoding="utf-8") == original_text


def test_prepare_stage1_rebuilds_source_flow_when_required_lane_packet_missing(
    novel, template_dir, graph_dir, config
):
    from storygraph_lib.stage1 import prepare_stage1

    novel.write_text(
        "\n".join([f"第{index}章\n韩立获得物品{index}。" for index in range(1, 6)]),
        encoding="utf-8",
    )
    first = prepare_stage1(
        source_path=novel,
        template_dir=template_dir,
        graph_dir=graph_dir,
        config=config,
    )
    chunks = json.loads(
        (graph_dir / "coverage" / "chunk-ledger.json").read_text(encoding="utf-8")
    )
    assert first["cache"]["source_flow"] == "refreshed"
    assert len(chunks) == 5

    missing_packet = (
        graph_dir
        / "intermediate"
        / "task-packets"
        / "chunk-0005"
        / "entities_resources.json"
    )
    missing_packet.unlink()
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
    lane_packets = sorted(
        (graph_dir / "intermediate" / "task-packets").glob("chunk-*/*.json")
    )

    assert result["cache"]["source_flow"] == "refreshed"
    assert len(lane_packets) == 5
    assert len(_lane_phase(dispatch)["task_packets"]) == 5


def test_prepare_stage1_rebuilds_source_flow_when_lane_packet_contract_fields_missing(
    novel, template_dir, graph_dir, config
):
    from storygraph_lib.stage1 import prepare_stage1

    _prepare_and_ingest_requirements(novel, template_dir, graph_dir, config)
    packet_path = _lane_packet_path(graph_dir)
    original_packet = json.loads(packet_path.read_text(encoding="utf-8"))
    packet_path.write_text(
        json.dumps(
            {
                key: original_packet[key]
                for key in [
                    "stage",
                    "chunk_id",
                    "lane_id",
                    "agent_role",
                    "task_packet_path",
                    "attempt",
                ]
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    result = prepare_stage1(
        source_path=novel,
        template_dir=template_dir,
        graph_dir=graph_dir,
        config=config,
    )
    rebuilt_packet = json.loads(packet_path.read_text(encoding="utf-8"))

    assert result["cache"]["source_flow"] == "refreshed"
    assert rebuilt_packet["source_path"] == original_packet["source_path"]
    assert rebuilt_packet["source_range"] == original_packet["source_range"]
    assert rebuilt_packet["chunk_text_path"] == original_packet["chunk_text_path"]
    assert (
        rebuilt_packet["relevant_template_requirements"]["path"]
        == original_packet["relevant_template_requirements"]["path"]
    )
    assert rebuilt_packet["lane_contract"] == original_packet["lane_contract"]
    assert rebuilt_packet["allowed_output_schema"] == original_packet["allowed_output_schema"]
    assert rebuilt_packet["task_packet_path"] == original_packet["task_packet_path"]
    assert rebuilt_packet["stage"] == "stage1"
    assert rebuilt_packet["agent_role"] == original_packet["agent_role"]


def test_prepare_stage1_rebuilds_source_flow_when_chunk_ledger_is_truncated(
    novel, template_dir, graph_dir, config
):
    from storygraph_lib.stage1 import prepare_stage1

    novel.write_text(
        "\n".join([f"第{index}章\n韩立获得物品{index}。" for index in range(1, 6)]),
        encoding="utf-8",
    )
    _prepare_and_ingest_requirements(novel, template_dir, graph_dir, config)
    ledger_path = graph_dir / "coverage" / "chunk-ledger.json"
    chunks = json.loads(ledger_path.read_text(encoding="utf-8"))
    assert len(chunks) == 5
    ledger_path.write_text(
        json.dumps(chunks[:4], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    result = prepare_stage1(
        source_path=novel,
        template_dir=template_dir,
        graph_dir=graph_dir,
        config=config,
    )
    restored_chunks = json.loads(ledger_path.read_text(encoding="utf-8"))
    dispatch = json.loads(
        (graph_dir / "intermediate" / "agent-dispatch-plan.json").read_text(
            encoding="utf-8"
        )
    )

    assert result["cache"]["source_flow"] == "refreshed"
    assert len(restored_chunks) == 5
    assert len(_lane_phase(dispatch)["task_packets"]) == 5


def test_prepare_stage1_rebuilds_lane_packets_when_requirements_artifact_path_changes(
    novel, template_dir, graph_dir, config
):
    from storygraph_lib.stage1 import prepare_stage1

    prepare_stage1(
        source_path=novel,
        template_dir=template_dir,
        graph_dir=graph_dir,
        config=config,
    )
    config_v2 = copy.deepcopy(config)
    config_v2["stage1_artifacts"]["requirements"] = (
        "requirements-v2/template-requirements.json"
    )

    result = prepare_stage1(
        source_path=novel,
        template_dir=template_dir,
        graph_dir=graph_dir,
        config=config_v2,
    )
    packet = json.loads(_lane_packet_path(graph_dir).read_text(encoding="utf-8"))

    assert result["cache"]["source_flow"] == "refreshed"
    assert (
        packet["relevant_template_requirements"]["path"]
        == "requirements-v2/template-requirements.json"
    )


def test_prepare_stage1_rebuilds_source_flow_and_removes_stale_agent_outputs_when_source_changes(
    novel, template_dir, graph_dir, config
):
    from storygraph_lib.stage1 import ingest_stage1, prepare_stage1

    _prepare_and_ingest_requirements(novel, template_dir, graph_dir, config)
    lane_packet_path = _lane_packet_path(graph_dir)
    lane_packet = json.loads(lane_packet_path.read_text(encoding="utf-8"))
    lane_packet["sentinel"] = "stale"
    lane_packet_path.write_text(
        json.dumps(lane_packet, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    stale_paths = [
        graph_dir
        / "intermediate"
        / "lane-outputs"
        / "chunk-0001"
        / "entities_resources"
        / "run-001.json",
        graph_dir / "intermediate" / "reviewed-bundles" / "chunk-0001.json",
        graph_dir / "intermediate" / "merge-queue.json",
        graph_dir / "graphify-out" / "graph.json",
    ]
    for stale_path in stale_paths:
        stale_path.parent.mkdir(parents=True, exist_ok=True)
        stale_path.write_text("{}", encoding="utf-8")

    novel.write_text("第一章\n韩立获得小瓶。\n第二章\n韩立离开洞府。", encoding="utf-8")
    result = prepare_stage1(
        source_path=novel,
        template_dir=template_dir,
        graph_dir=graph_dir,
        config=config,
    )
    rebuilt_packet = json.loads(lane_packet_path.read_text(encoding="utf-8"))
    ingest = ingest_stage1(graph_dir=graph_dir, config=config)

    assert result["cache"]["source_flow"] == "refreshed"
    assert "sentinel" not in rebuilt_packet
    assert all(not stale_path.exists() for stale_path in stale_paths)
    assert ingest["status"] == "failed"
    assert "agent_lane_outputs_missing" in ingest["validation_errors"]


def test_incremental_template_ingest_fails_closed_when_existing_total_missing_or_invalid(
    novel, template_dir, graph_dir, config
):
    from storygraph_lib.stage1 import ingest_template_requirements, prepare_stage1

    (template_dir / "人物分析模板.md").write_text("# 人物分析模板\n- 人物", encoding="utf-8")
    _prepare_and_ingest_requirements(novel, template_dir, graph_dir, config)
    (template_dir / "人物分析模板.md").write_text(
        "# 人物分析模板\n- 人物\n- 新字段",
        encoding="utf-8",
    )
    prepare_stage1(
        source_path=novel,
        template_dir=template_dir,
        graph_dir=graph_dir,
        config=config,
    )
    _write_requirement_parts(graph_dir, {"人物分析": "changed-marker"})

    requirements_path = graph_dir / "requirements" / "template-requirements.json"
    requirements_path.unlink()
    missing = ingest_template_requirements(graph_dir=graph_dir, config=config)
    requirements_path.write_text("\ufeff{}", encoding="utf-8")
    bad = ingest_template_requirements(graph_dir=graph_dir, config=config)

    assert missing["status"] == "failed"
    assert "template_requirements_existing_total_missing" in missing["validation_errors"]
    assert bad["status"] == "failed"
    assert "template_requirements_existing_total_invalid" in bad["validation_errors"]


def test_incremental_template_ingest_fails_closed_on_duplicate_template_file_key(
    novel, template_dir, graph_dir, config
):
    from storygraph_lib.stage1 import ingest_template_requirements, prepare_stage1

    (template_dir / "人物分析模板.md").write_text("# 人物分析模板\n- 人物", encoding="utf-8")
    _prepare_and_ingest_requirements(novel, template_dir, graph_dir, config)
    duplicate = {
        "template_count": 2,
        "templates": [
            _requirement("法宝分析", "法宝分析模板.md", "one"),
            _requirement("法宝分析副本", "法宝分析模板.md", "two"),
        ],
    }
    (graph_dir / "requirements" / "template-requirements.json").write_text(
        json.dumps(duplicate, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (template_dir / "人物分析模板.md").write_text(
        "# 人物分析模板\n- 人物\n- 新字段",
        encoding="utf-8",
    )
    prepare_stage1(
        source_path=novel,
        template_dir=template_dir,
        graph_dir=graph_dir,
        config=config,
    )
    _write_requirement_parts(graph_dir, {"人物分析": "changed-marker"})

    result = ingest_template_requirements(graph_dir=graph_dir, config=config)

    assert result["status"] == "failed"
    assert "template_requirements_duplicate_template_key:法宝分析模板.md" in result[
        "validation_errors"
    ]


def test_prepare_stage1_template_packets_keep_recursive_template_relative_paths(
    novel, template_dir, graph_dir, config
):
    from storygraph_lib.stage1 import prepare_stage1

    config["template_discovery"]["glob"] = "**/*模板.md"
    (template_dir / "A").mkdir()
    (template_dir / "B").mkdir()
    (template_dir / "A" / "同名模板.md").write_text(
        "# 同名模板\n- A字段",
        encoding="utf-8",
    )
    (template_dir / "B" / "同名模板.md").write_text(
        "# 同名模板\n- B字段",
        encoding="utf-8",
    )

    result = prepare_stage1(
        source_path=novel,
        template_dir=template_dir,
        graph_dir=graph_dir,
        config=config,
    )
    cache = json.loads(
        (graph_dir / "intermediate" / "stage1-input-cache.json").read_text(
            encoding="utf-8"
        )
    )
    packets = _template_packets(graph_dir)
    packet_files = [
        item["template_file"]
        for packet in packets
        for item in packet["template_inventory"]
    ]
    cache_files = [item["template_file"] for item in cache["templates"]]

    assert result["status"] == "prepared"
    assert sorted(packet_files) == sorted(cache_files)
    assert "A/同名模板.md" in packet_files
    assert "B/同名模板.md" in packet_files
