import pytest

from storygraph_lib.stage2_schema import (
    make_extraction_record,
    make_template_evidence_usage,
    make_template_gap_report,
    make_template_run_ledger,
    validate_extraction_record,
)


POLICY = {
    "output_language": "zh-CN",
    "stage2_categories": {
        "facts": "事实-A",
        "judgments": "判断-B",
        "pending_verifications": "待查-C",
        "not_found_items": "缺口-D",
    },
    "stage2_output_policy": {
        "default_dir": "drafts",
        "allowed_policies": ["draft", "backup-and-overwrite", "merge"],
        "draft_action": "write_draft",
    },
}


def _record():
    return make_extraction_record(
        template_name="法宝分析",
        template_file="法宝分析模板.md",
        source_graph="凡人修仙传.storygraph/graphify-out/graph.json",
        source_novel="凡人修仙传.txt",
        requirement_id="法宝分析.required_fields.法宝",
        evidence_id="evidence:abc",
        policy=POLICY,
    )


def test_stage2_extraction_record_uses_policy_categories_and_default_coverage_scope():
    record = _record()

    assert record["facts"][0]["category"] == "事实-A"
    assert record["judgments"][0]["category"] == "判断-B"
    assert record["pending_verifications"][0]["category"] == "待查-C"
    assert record["not_found_items"][0]["category"] == "缺口-D"
    assert record["coverage_scope"]["stage1_chunk_ledger"] == "coverage/chunk-ledger.json"
    assert record["coverage_scope"]["chunk_ranges"] == []
    assert validate_extraction_record(record).ok is True


def test_stage2_validation_rejects_fact_without_evidence():
    record = _record()
    record["facts"][0]["evidence_ids"] = []

    result = validate_extraction_record(record)

    assert result.ok is False
    assert "facts[0].evidence_ids_required" in result.errors


def test_stage2_validation_rejects_missing_required_fields_and_bad_coverage_scope():
    record = _record()
    del record["source_graph"]
    record["coverage_scope"]["stage1_chunk_ledger"] = "coverage/wrong.json"

    result = validate_extraction_record(record)

    assert result.ok is False
    assert "missing:source_graph" in result.errors
    assert "coverage_scope.stage1_chunk_ledger_invalid" in result.errors


def test_stage2_validation_rejects_missing_policy_and_category_coverage():
    record = _record()
    del record["stage2_policy"]
    del record["not_found_items"][0]["category"]

    result = validate_extraction_record(record)

    assert result.ok is False
    assert "missing:stage2_policy" in result.errors
    assert "not_found_items[0].category_required" in result.errors


@pytest.mark.parametrize("bad_record", [None, []])
def test_stage2_validation_rejects_non_object_record_without_crashing(bad_record):
    result = validate_extraction_record(bad_record)

    assert result.ok is False
    assert "record.must_be_object" in result.errors


def test_stage2_validation_rejects_bad_allowed_policies_shape_and_unsupported_overwrite():
    record = _record()
    record["overwrite_policy"] = "replace"
    record["stage2_policy"]["stage2_output_policy"]["allowed_policies"] = "draft"

    result = validate_extraction_record(record)

    assert result.ok is False
    assert "stage2_policy.stage2_output_policy.allowed_policies_must_be_list" in result.errors
    assert "overwrite_policy.unsupported" in result.errors


def test_stage2_validation_accepts_document_sections_with_known_evidence():
    record = _record()
    record["document_sections"] = [
        {
            "heading": "法宝来源",
            "markdown": "小瓶来自可靠原文证据。",
            "evidence_ids": ["evidence:abc"],
            "requirement_ids": ["法宝分析.required_fields.法宝"],
            "confidence": "EXTRACTED",
        }
    ]

    result = validate_extraction_record(record, evidence_ids={"evidence:abc"})

    assert result.ok is True


def test_stage2_validation_rejects_document_section_with_unknown_evidence():
    record = _record()
    record["document_sections"] = [
        {
            "heading": "法宝来源",
            "markdown": "小瓶来自可靠原文证据。",
            "evidence_ids": ["evidence:missing"],
            "requirement_ids": ["法宝分析.required_fields.法宝"],
            "confidence": "EXTRACTED",
        }
    ]

    result = validate_extraction_record(record, evidence_ids={"evidence:abc"})

    assert result.ok is False
    assert "document_sections[0].evidence_ids.unknown:evidence:missing" in result.errors


def test_stage2_validation_rejects_unknown_fact_and_citation_evidence():
    record = _record()
    record["facts"][0]["evidence_ids"] = ["evidence:missing-fact"]
    record["evidence_citations"] = ["evidence:missing-citation"]

    result = validate_extraction_record(record, evidence_ids={"evidence:abc"})

    assert result.ok is False
    assert "facts[0].evidence_ids.unknown:evidence:missing-fact" in result.errors
    assert "evidence_citations[0].unknown:evidence:missing-citation" in result.errors


def test_stage2_validation_can_require_document_sections_for_ingest():
    record = _record()

    result = validate_extraction_record(
        record,
        evidence_ids={"evidence:abc"},
        require_document_sections=True,
    )

    assert result.ok is False
    assert "document_sections.required" in result.errors


def test_stage2_scaffold_ledgers_use_input_templates_and_artifact_paths():
    sample_template_count = 37
    templates = [f"模板{i:02d}" for i in range(sample_template_count)]
    chunk_ranges = [{"chunk_id": "chunk-0001", "source_range": [0, 100]}]

    ledger = make_template_run_ledger(templates, chunk_ranges=chunk_ranges)

    assert [task["template_name"] for task in ledger["template_tasks"]] == templates
    assert ledger["artifact_paths"]["template_run_ledger"] == "coverage/template-run-ledger.json"
    assert (
        ledger["artifact_paths"]["template_evidence_usage"]
        == "coverage/template-evidence-usage.json"
    )
    assert ledger["artifact_paths"]["template_gap_report"] == "coverage/template-gap-report.md"
    assert ledger["coverage_scope"]["stage1_chunk_ledger"] == "coverage/chunk-ledger.json"
    assert ledger["coverage_scope"]["chunk_ranges"][0]["source_range"] == [0, 100]


def test_stage2_evidence_usage_and_gap_report_paths_and_status():
    usage = make_template_evidence_usage("模板00", "evidence:abc", "chunk-0001", [0, 100])
    gap = make_template_gap_report("模板00", "模板00.required_fields.法宝", "not_found_in_source")

    assert usage["artifact_path"] == "coverage/template-evidence-usage.json"
    assert usage["evidence_id"] == "evidence:abc"
    assert usage["source_range"] == [0, 100]
    assert gap["artifact_path"] == "coverage/template-gap-report.md"
    assert gap["gaps"][0]["status"] == "not_found_in_source"
