import json

from storygraph_lib.coverage import make_chunk_ledger, write_coverage_outputs
from storygraph_lib.graph_schema import merge_template_supplements, validate_canonical_graph
from storygraph_lib.output_writer import OutputWriter
from storygraph_lib.template_aware import extract_template_aware_supplements


def _template_record(template_name, required_fields, **overrides):
    record = {
        "template_name": template_name,
        "required_fields": required_fields,
        "required_tables": [],
        "required_cards": [],
        "required_card_headings": [],
        "required_card_fields": [],
        "required_case_patterns": [],
        "graph_node_mapping": [f"{template_name}.node"],
        "graph_event_mapping": [f"{template_name}.event"],
        "graph_relation_mapping": [f"{template_name}.relation"],
    }
    record.update(overrides)
    return record


def test_make_chunk_ledger_reads_source_and_returns_chapter_aware_chunk_list(tmp_path):
    source = tmp_path / "novel.txt"
    source.write_text(
        "第一章 开端\n韩立获得小瓶。\n第二章 后续\n小瓶催熟灵草。\n",
        encoding="utf-8",
    )

    chunks = make_chunk_ledger(
        source,
        {
            "mode": "chapter-aware",
            "max_chars": 20,
            "overlap_chars": 0,
            "chapter_heading_patterns": ["^第.+章"],
        },
        processor="pytest",
    )

    assert [chunk["chunk_id"] for chunk in chunks] == ["chunk-0001", "chunk-0002"]
    assert chunks[0]["source_range"] == [0, len("第一章 开端\n韩立获得小瓶。\n")]
    assert chunks[0]["chapter_hint"] == "第一章 开端"
    assert chunks[0]["hash"]
    assert chunks[0]["scanned_at"] is None
    assert chunks[0]["processor"] == "pytest"
    assert chunks[0]["extraction_status"] == "pending"
    assert chunks[0]["failure"] is None
    assert chunks[0]["retry_count"] == 0
    assert chunks[0]["text"] == "第一章 开端\n韩立获得小瓶。\n"
    assert chunks[1]["chapter_hint"] == "第二章 后续"


def test_write_coverage_outputs_uses_writer_for_plan_coverage_artifacts(tmp_path):
    writer = OutputWriter(
        tmp_path,
        [
            "coverage/chunk-ledger.json",
            "coverage/evidence-index.json",
            "coverage/template-readiness.json",
            "coverage/agent-run-ledger.json",
            "coverage/gap-report.md",
        ],
    )

    paths = write_coverage_outputs(
        writer,
        chunks=[{"chunk_id": "chunk-0001"}],
        evidences=[{"evidence_id": "evidence:1"}],
        readiness=[{"template_name": "法宝分析"}],
        agent_runs=[{"run_id": "run-1"}],
        gap_lines=["# Gap Report", "- none"],
    )

    assert json.loads(paths["chunks"].read_text(encoding="utf-8")) == [{"chunk_id": "chunk-0001"}]
    assert json.loads(paths["agent_runs"].read_text(encoding="utf-8")) == [{"run_id": "run-1"}]
    assert paths["gap_report"].read_text(encoding="utf-8") == "# Gap Report\n- none\n"


def test_extract_template_aware_supplements_creates_graph_items_readiness_and_evidence_links(tmp_path):
    source = tmp_path / "novel.txt"
    source.write_text(
        "第一章 开端\n韩立获得小瓶。小瓶催熟灵草，持有者韩立。\n",
        encoding="utf-8",
    )
    chunks = make_chunk_ledger(
        source,
        {"mode": "chapter-aware", "max_chars": 200, "overlap_chars": 0},
        processor="pytest",
    )
    matrix = {
        "templates": [
            _template_record(
                "法宝分析",
                ["小瓶"],
                required_tables=["名称|效果"],
                required_cards=["法宝卡片"],
                required_card_fields=["持有者"],
                required_case_patterns=["小瓶催熟灵草"],
                graph_node_mapping=["artifact"],
                graph_event_mapping=["artifact_discovery"],
                graph_relation_mapping=["supports_requirement"],
            )
        ]
    }

    supplement, readiness = extract_template_aware_supplements(
        "凡人修仙传",
        source,
        chunks,
        matrix,
        {"case_sensitive": False, "minimum_confidence": "EXTRACTED"},
    )

    assert supplement["nodes"]
    assert supplement["edges"]
    assert supplement["events"]
    assert supplement["evidence_index"]
    assert all(edge.get("source_location") or edge.get("source_range") for edge in supplement["edges"])

    record = readiness[0]
    assert record["template_name"] == "法宝分析"
    assert record["readiness_score"] == 0.6
    assert record["supporting_node_count"] == len(supplement["nodes"])
    assert record["supporting_edge_count"] == len(supplement["edges"])
    assert record["supporting_event_count"] == len(supplement["events"])
    assert record["evidence_count"] == len(supplement["evidence_index"])
    assert record["missing_requirement_types"] == ["tables", "cards"]
    assert record["notes"]
    assert {item["status"] for item in record["requirement_statuses"]} == {
        "covered",
        "not_found_in_source",
    }

    covered = [item for item in record["requirement_statuses"] if item["status"] == "covered"]
    assert covered
    for item in covered:
        assert item["linked_node_ids"]
        assert item["linked_edge_ids"]
        assert item["linked_event_ids"]
        assert item["evidence_ids"]
        assert item["requirement_kind"] in {"fields", "cards", "cases"}
    missing = [item for item in record["requirement_statuses"] if item["status"] == "not_found_in_source"]
    assert missing
    for item in missing:
        assert item["linked_node_ids"] == []
        assert item["linked_edge_ids"] == []
        assert item["linked_event_ids"] == []
        assert item["evidence_ids"] == []
        assert item["notes"]

    evidence = supplement["evidence_index"][0]
    assert evidence["source_path"] == str(source)
    assert evidence["source_range"]
    assert evidence["chapter_hint"] == "第一章 开端"
    assert evidence["support"]
    assert evidence["supports_templates"]
    assert evidence["confidence"] == "EXTRACTED"
    assert evidence["verification_status"] == "verified"
    assert evidence["linked_node_ids"]
    assert evidence["linked_edge_ids"]
    assert evidence["linked_event_ids"]

    graph = merge_template_supplements(
        {
            "schema_version": "1.0",
            "graphify_schema_version": "test",
            "storygraph_schema_version": "1.0",
            "nodes": [],
            "edges": [],
            "hyperedges": [],
            "events": [],
            "evidence_index": [],
            "metadata": {},
        },
        supplement,
    )
    validation = validate_canonical_graph(graph)
    assert validation.ok, validation.errors


def test_extract_template_aware_supplements_reports_one_readiness_record_per_37_templates(tmp_path):
    source = tmp_path / "novel.txt"
    source.write_text("第一章 开端\n需求00出现。需求01A出现。\n", encoding="utf-8")
    chunks = make_chunk_ledger(
        source,
        {"mode": "bounded-chars", "max_chars": 200, "overlap_chars": 0},
        processor="pytest",
    )
    templates = []
    for index in range(37):
        fields = [f"需求{index:02d}"]
        if index == 1:
            fields = ["需求01A", "需求01B"]
        templates.append(_template_record(f"模板{index:02d}", fields))

    supplement, readiness = extract_template_aware_supplements(
        "覆盖测试",
        source,
        chunks,
        {"templates": templates},
        {"case_sensitive": False},
    )

    assert len(readiness) == 37
    assert [record["template_name"] for record in readiness] == [f"模板{index:02d}" for index in range(37)]
    scores = {record["readiness_score"] for record in readiness}
    assert scores == {1.0, 0.5, 0.0}
    assert {status["status"] for record in readiness for status in record["requirement_statuses"]} == {
        "covered",
        "not_found_in_source",
    }
    assert supplement["nodes"]
