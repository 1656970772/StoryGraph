from storygraph_lib.coverage import make_chunk_ledger
from storygraph_lib.graph_schema import merge_template_supplements, validate_canonical_graph
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


def test_make_chunk_ledger_reads_source_and_returns_chapter_aware_chunks(tmp_path):
    source = tmp_path / "novel.txt"
    source.write_text(
        "第一章 开端\n韩立获得小瓶。\n第二章 后续\n小瓶催熟灵草。\n",
        encoding="utf-8",
    )

    ledger = make_chunk_ledger(
        source,
        {
            "mode": "chapter-aware",
            "max_chars": 20,
            "overlap_chars": 0,
            "chapter_heading_patterns": ["^第.+章"],
        },
    )

    assert ledger["source_path"] == str(source)
    assert ledger["source_size"] == len(source.read_text(encoding="utf-8"))
    assert [chunk["chunk_id"] for chunk in ledger["chunks"]] == ["chunk-0001", "chunk-0002"]
    assert ledger["chunks"][0]["chapter"] == "第一章 开端"
    assert ledger["chunks"][0]["source_range"][0] == 0
    assert ledger["chunks"][0]["text"] == "第一章 开端\n韩立获得小瓶。\n"
    assert ledger["chunks"][1]["chapter"] == "第二章 后续"


def test_extract_template_aware_supplements_creates_graph_items_and_evidence(tmp_path):
    source = tmp_path / "novel.txt"
    source.write_text(
        "第一章 开端\n韩立获得小瓶。小瓶催熟灵草，持有者韩立。\n",
        encoding="utf-8",
    )
    chunk_ledger = make_chunk_ledger(
        source,
        {"mode": "chapter-aware", "max_chars": 200, "overlap_chars": 0},
    )
    requirement_matrix = {
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

    supplement = extract_template_aware_supplements(
        source_path=source,
        requirement_matrix=requirement_matrix,
        chunk_ledger=chunk_ledger,
        novel_name="凡人修仙传",
    )

    assert supplement["nodes"]
    assert supplement["edges"]
    assert supplement["events"]
    assert supplement["evidence_index"]
    assert supplement["template_readiness"] == [
        {
            "template_name": "法宝分析",
            "status": "needs_review",
            "covered_requirements": 3,
            "total_requirements": 5,
        }
    ]
    assert all(edge.get("source_location") or edge.get("source_range") for edge in supplement["edges"])
    evidence = supplement["evidence_index"][0]
    assert evidence["source_path"] == str(source)
    assert evidence["chunk_id"] == "chunk-0001"
    assert evidence["support"]
    assert evidence["confidence"] == "EXTRACTED"
    assert evidence["verification_status"] == "verified"
    assert evidence["supports_templates"]
    assert supplement["nodes"][0]["supports_templates"]
    assert supplement["events"][0]["supports_templates"]

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
    chunk_ledger = make_chunk_ledger(
        source,
        {"mode": "bounded-chars", "max_chars": 200, "overlap_chars": 0},
    )
    templates = []
    for index in range(37):
        fields = [f"需求{index:02d}"]
        if index == 1:
            fields = ["需求01A", "需求01B"]
        templates.append(_template_record(f"模板{index:02d}", fields))

    supplement = extract_template_aware_supplements(
        source_path=source,
        requirement_matrix={"templates": templates},
        chunk_ledger=chunk_ledger,
        novel_name="覆盖测试",
    )

    readiness = supplement["template_readiness"]
    assert len(readiness) == 37
    assert [record["template_name"] for record in readiness] == [f"模板{index:02d}" for index in range(37)]
    assert {record["status"] for record in readiness} == {
        "covered",
        "needs_review",
        "not_found_in_source",
    }
