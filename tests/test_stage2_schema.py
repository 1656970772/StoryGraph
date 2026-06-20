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


def test_stage2_scaffold_ledgers_use_input_templates_and_artifact_paths():
    templates = [f"模板{i:02d}" for i in range(37)]
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
