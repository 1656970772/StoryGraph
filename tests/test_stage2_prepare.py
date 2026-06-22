import json
from pathlib import Path

import pytest

from storygraph_lib.stage2 import prepare_stage2


def _stage2_config() -> dict:
    return {
        "output_language": "zh-CN",
        "stage2_categories": {
            "facts": "原作事实",
            "judgments": "我的判断",
            "pending_verifications": "待核验",
            "not_found_items": "未见可靠证据",
        },
        "overwrite_policy": "draft",
        "stage2_output_policy": {
            "default_dir": "drafts",
            "allowed_policies": ["draft", "backup-and-overwrite", "merge"],
            "draft_action": "write_draft",
        },
        "stage2_artifacts": {
            "task_packet_dir": "intermediate/stage2/task-packets",
            "dispatch_state": "intermediate/stage2/dispatch-state.json",
            "extraction_record_dir": "intermediate/stage2/extraction-records",
        },
        "stage2_agent_orchestration": {
            "grouping_strategy": "by_template_document",
            "agent_role": "stage2-template-document-agent",
            "max_parallel_agents": 2,
        },
        "stage2_render_policy": {
            "citation_format": "[{evidence_id}]",
            "include_unreviewed_warning": True,
        },
        "writer_policy": {
            "managed_outputs": [
                "intermediate/stage2/task-packets/*.json",
                "intermediate/stage2/dispatch-state.json",
                "intermediate/stage2/extraction-records/*/*.json",
                "coverage/template-run-ledger.json",
                "coverage/template-evidence-usage.json",
                "coverage/template-gap-report.md",
                "drafts/*.md",
                "manifest.json",
            ]
        },
    }


def _write_stage1_inputs(
    graph_dir: Path,
    template_dir: Path,
    *,
    include_second_template: bool = False,
    include_second_category_for_first_template: bool = False,
) -> None:
    (template_dir / "法宝分析模板.md").write_text(
        "# 法宝分析\n\n## 来源\n\n## 用途\n",
        encoding="utf-8",
    )
    if include_second_template:
        (template_dir / "角色分析模板.md").write_text(
            "# 角色分析\n\n## 身份\n\n## 行动\n",
            encoding="utf-8",
        )
    categories = [
        {
            "category_id": "resources_items_economy",
            "category_name": "资源、物品与交易经济",
            "template_coverage": [
                "法宝分析",
                *(["角色分析"] if include_second_template else []),
            ],
            "required_extraction_targets": ["法宝"],
            "evidence_requirements": ["原文位置"],
        }
    ]
    if include_second_category_for_first_template:
        categories.append(
            {
                "category_id": "characters_relationships",
                "category_name": "角色与关系",
                "template_coverage": ["法宝分析"],
                "required_extraction_targets": ["持有人"],
                "evidence_requirements": ["角色证据"],
            }
        )
    (graph_dir / "requirements").mkdir(parents=True)
    (graph_dir / "requirements" / "template-requirements.json").write_text(
        json.dumps(
            {
                "schema_version": "storygraph.template-requirements-summary.v1",
                "source_template_count": 1 + int(include_second_template),
                "categories": categories,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    (graph_dir / "intermediate").mkdir()
    (graph_dir / "intermediate" / "stage1-input-cache.json").write_text(
        json.dumps(
            {
                "templates": [
                    {
                        "template_name": "法宝分析",
                        "template_file": "法宝分析模板.md",
                        "md5": "abc",
                        "sha256": "def",
                    },
                    *(
                        [
                            {
                                "template_name": "角色分析",
                                "template_file": "角色分析模板.md",
                                "md5": "role-md5",
                                "sha256": "role-sha",
                            }
                        ]
                        if include_second_template
                        else []
                    ),
                ]
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    (graph_dir / "coverage").mkdir()
    (graph_dir / "coverage" / "template-readiness.json").write_text(
        json.dumps(
            [
                {
                    "template_name": "法宝分析",
                    "readiness_score": 1,
                    "evidence_count": 1,
                    "missing_requirement_types": [],
                }
            ],
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    (graph_dir / "coverage" / "evidence-index.json").write_text(
        json.dumps(
            [
                {
                    "evidence_id": "evidence:abc",
                    "chunk_id": "chunk-0001",
                    "source_range": [0, 10],
                    "fact_summary": "韩立获得小瓶。",
                    "supports_templates": [
                        {
                            "template_name": "资源、物品与交易经济",
                            "requirement_id": "resources_items_economy",
                            "status": "covered",
                        }
                    ],
                },
                *(
                    [
                        {
                            "evidence_id": "evidence:role",
                            "chunk_id": "chunk-0002",
                            "source_range": [11, 30],
                            "fact_summary": "韩立保管小瓶。",
                            "supports_templates": [
                                {
                                    "template_name": "法宝分析",
                                    "requirement_id": "characters_relationships",
                                    "status": "covered",
                                }
                            ],
                        }
                    ]
                    if include_second_category_for_first_template
                    else []
                ),
            ],
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    (graph_dir / "graphify-out").mkdir()
    (graph_dir / "graphify-out" / "graph.json").write_text(
        json.dumps(
            {
                "nodes": [],
                "edges": [],
                "events": [],
                "evidence_index": [],
                "metadata": {"review_status": "unreviewed_usable"},
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def _read_single_packet(graph_dir: Path) -> dict:
    packet_paths = list((graph_dir / "intermediate" / "stage2" / "task-packets").glob("*.json"))
    assert len(packet_paths) == 1
    return json.loads(packet_paths[0].read_text(encoding="utf-8"))


def _valid_stage2_record(template_name="法宝分析", template_file="法宝分析模板.md"):
    return {
        "schema": "stage2-extraction-record.v1",
        "template_name": template_name,
        "template_file": template_file,
        "source_graph": "graphify-out/graph.json",
        "source_novel": "book.txt",
        "stage2_policy": {
            "stage2_categories": {
                "facts": "原作事实",
                "judgments": "我的判断",
                "pending_verifications": "待核验",
                "not_found_items": "未见可靠证据",
            },
            "stage2_output_policy": {
                "default_dir": "drafts",
                "allowed_policies": ["draft", "backup-and-overwrite", "merge"],
                "draft_action": "write_draft",
            },
        },
        "coverage_scope": {
            "scope": "whole_novel",
            "stage1_chunk_ledger": "coverage/chunk-ledger.json",
            "chunk_ranges": [{"chunk_id": "chunk-0001", "source_range": [0, 10]}],
            "ledger_path": "coverage/template-run-ledger.json",
        },
        "fulfilled_sections": [],
        "facts": [
            {
                "content": "韩立获得小瓶。",
                "category": "原作事实",
                "evidence_ids": ["evidence:abc"],
                "source_locations": [],
                "confidence": "EXTRACTED",
            }
        ],
        "judgments": [],
        "pending_verifications": [],
        "not_found_items": [],
        "document_sections": [
            {
                "heading": "来源",
                "markdown": "韩立获得小瓶。",
                "evidence_ids": ["evidence:abc"],
                "requirement_ids": ["resources_items_economy"],
                "confidence": "EXTRACTED",
            }
        ],
        "evidence_citations": ["evidence:abc"],
        "overwrite_policy": "draft",
    }


def _record_path(graph_dir: Path, template_name="法宝分析") -> Path:
    return (
        graph_dir
        / "intermediate"
        / "stage2"
        / "extraction-records"
        / template_name
        / "run-001.json"
    )


def test_prepare_stage2_creates_one_batch_per_template_document_and_writes_ledgers(tmp_path):
    graph_dir = tmp_path / "book.storygraph"
    template_dir = tmp_path / "templates"
    graph_dir.mkdir()
    template_dir.mkdir()
    _write_stage1_inputs(graph_dir, template_dir)

    result = prepare_stage2(graph_dir, template_dir, _stage2_config())

    assert result["status"] == "prepared"
    assert result["batch_count"] == 1
    packet = _read_single_packet(graph_dir)
    assert packet["batch_id"].startswith("template-batch-0001-")
    assert packet["grouping_strategy"] == "by_template_document"
    assert packet["category_id"] == "resources_items_economy"
    assert packet["requirement_categories"][0]["category_id"] == "resources_items_economy"
    assert len(packet["templates"]) == 1
    assert packet["templates"][0]["template_name"] == "法宝分析"
    assert packet["templates"][0]["template_headings"] == ["法宝分析", "来源", "用途"]
    assert packet["evidence_ids"] == ["evidence:abc"]
    normalized_output_path = packet["expected_output_paths"][0].replace("\\", "/")
    assert normalized_output_path.endswith(
        "intermediate/stage2/extraction-records/法宝分析/run-001.json"
    )

    dispatch = json.loads(
        (graph_dir / "intermediate" / "stage2" / "dispatch-state.json").read_text(
            encoding="utf-8"
        )
    )
    assert dispatch["pending_count"] == 1
    assert dispatch["batches"][0]["status"] == "pending"

    ledger = json.loads(
        (graph_dir / "coverage" / "template-run-ledger.json").read_text(encoding="utf-8")
    )
    assert ledger["template_tasks"][0]["template_name"] == "法宝分析"
    assert ledger["template_tasks"][0]["status"] == "pending"
    assert ledger["template_tasks"][0]["batch_id"] == packet["batch_id"]


def test_prepare_stage2_changed_or_missing_skips_completed_unchanged_templates(tmp_path):
    graph_dir = tmp_path / "book.storygraph"
    template_dir = tmp_path / "templates"
    graph_dir.mkdir()
    template_dir.mkdir()
    _write_stage1_inputs(graph_dir, template_dir, include_second_template=True)
    prepare_stage2(graph_dir, template_dir, _stage2_config())

    record_path = _record_path(graph_dir, "法宝分析")
    record_path.parent.mkdir(parents=True)
    record_path.write_text(
        json.dumps(_valid_stage2_record("法宝分析", "法宝分析模板.md"), ensure_ascii=False),
        encoding="utf-8",
    )
    draft_path = graph_dir / "drafts" / "法宝分析.md"
    draft_path.parent.mkdir()
    draft_path.write_text("# 法宝分析\n", encoding="utf-8")
    ledger_path = graph_dir / "coverage" / "template-run-ledger.json"
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    for task in ledger["template_tasks"]:
        if task["template_name"] == "法宝分析":
            task["status"] = "completed"
            task["output_record"] = "intermediate/stage2/extraction-records/法宝分析/run-001.json"
        else:
            task["status"] = "pending"
            task["output_record"] = None
    ledger_path.write_text(json.dumps(ledger, ensure_ascii=False, indent=2), encoding="utf-8")

    config = _stage2_config()
    config["stage2_incremental_policy"] = {"selection": "changed-or-missing"}
    result = prepare_stage2(
        graph_dir,
        template_dir,
        config,
        selection="changed-or-missing",
    )
    dispatch = json.loads(
        (graph_dir / "intermediate" / "stage2" / "dispatch-state.json").read_text(
            encoding="utf-8"
        )
    )

    assert result["batch_count"] == 1
    assert [batch["templates"][0]["template_name"] for batch in dispatch["batches"]] == [
        "角色分析"
    ]


def test_prepare_stage2_changed_or_missing_reruns_changed_template_hash(tmp_path):
    graph_dir = tmp_path / "book.storygraph"
    template_dir = tmp_path / "templates"
    graph_dir.mkdir()
    template_dir.mkdir()
    _write_stage1_inputs(graph_dir, template_dir)
    prepare_stage2(graph_dir, template_dir, _stage2_config())

    record_path = _record_path(graph_dir, "法宝分析")
    record_path.parent.mkdir(parents=True)
    record_path.write_text(
        json.dumps(_valid_stage2_record("法宝分析", "法宝分析模板.md"), ensure_ascii=False),
        encoding="utf-8",
    )
    ledger_path = graph_dir / "coverage" / "template-run-ledger.json"
    ledger = json.loads(ledger_path.read_text(encoding="utf-8"))
    ledger["template_tasks"][0]["status"] = "completed"
    ledger["template_tasks"][0]["output_record"] = (
        "intermediate/stage2/extraction-records/法宝分析/run-001.json"
    )
    ledger_path.write_text(json.dumps(ledger, ensure_ascii=False, indent=2), encoding="utf-8")
    (template_dir / "法宝分析模板.md").write_text(
        "# 法宝分析\n\n## 来源\n\n## 新用途\n",
        encoding="utf-8",
    )
    cache_path = graph_dir / "intermediate" / "stage1-input-cache.json"
    cache = json.loads(cache_path.read_text(encoding="utf-8"))
    cache["templates"][0]["sha256"] = "changed-stage1-template-hash"
    cache_path.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")

    result = prepare_stage2(
        graph_dir,
        template_dir,
        _stage2_config(),
        selection="changed-or-missing",
    )

    assert result["batch_count"] == 1


def test_prepare_stage2_splits_templates_in_same_category_into_independent_batches(tmp_path):
    graph_dir = tmp_path / "book.storygraph"
    template_dir = tmp_path / "templates"
    graph_dir.mkdir()
    template_dir.mkdir()
    _write_stage1_inputs(graph_dir, template_dir, include_second_template=True)

    result = prepare_stage2(graph_dir, template_dir, _stage2_config())

    assert result["status"] == "prepared"
    assert result["batch_count"] == 2
    dispatch = json.loads(
        (graph_dir / "intermediate" / "stage2" / "dispatch-state.json").read_text(
            encoding="utf-8"
        )
    )
    assert dispatch["pending_count"] == 2
    templates_by_batch = [
        [template["template_name"] for template in batch["templates"]]
        for batch in dispatch["batches"]
    ]
    assert templates_by_batch == [["法宝分析"], ["角色分析"]]
    assert all(len(batch["expected_output_rel_paths"]) == 1 for batch in dispatch["batches"])


def test_prepare_stage2_template_packet_aggregates_multiple_requirement_categories(tmp_path):
    graph_dir = tmp_path / "book.storygraph"
    template_dir = tmp_path / "templates"
    graph_dir.mkdir()
    template_dir.mkdir()
    _write_stage1_inputs(
        graph_dir,
        template_dir,
        include_second_category_for_first_template=True,
    )

    prepare_stage2(graph_dir, template_dir, _stage2_config())

    packet = _read_single_packet(graph_dir)
    assert [item["category_id"] for item in packet["requirement_categories"]] == [
        "resources_items_economy",
        "characters_relationships",
    ]
    assert packet["requirements"]["required_extraction_targets"] == ["法宝", "持有人"]
    assert packet["requirements"]["evidence_requirements"] == ["原文位置", "角色证据"]
    assert packet["evidence_ids"] == ["evidence:abc", "evidence:role"]


def test_prepare_stage2_rejects_legacy_requirement_category_grouping(tmp_path):
    graph_dir = tmp_path / "book.storygraph"
    template_dir = tmp_path / "templates"
    graph_dir.mkdir()
    template_dir.mkdir()
    _write_stage1_inputs(graph_dir, template_dir)
    config = _stage2_config()
    config["stage2_agent_orchestration"]["grouping_strategy"] = "by_requirement_category"

    result = prepare_stage2(graph_dir, template_dir, config)

    assert result == {
        "status": "failed",
        "error": "unsupported_stage2_grouping_strategy",
        "grouping_strategy": "by_requirement_category",
    }


@pytest.mark.parametrize("overwrite_policy", ["backup-and-overwrite", "merge"])
def test_prepare_stage2_formal_policies_still_create_single_template_packets(
    tmp_path,
    overwrite_policy,
):
    graph_dir = tmp_path / "book.storygraph"
    template_dir = tmp_path / "templates"
    graph_dir.mkdir()
    template_dir.mkdir()
    _write_stage1_inputs(graph_dir, template_dir)
    config = _stage2_config()
    config["overwrite_policy"] = overwrite_policy

    result = prepare_stage2(graph_dir, template_dir, config, overwrite_policy=overwrite_policy)

    assert result["status"] == "prepared"
    packet = _read_single_packet(graph_dir)
    assert packet["overwrite_policy"] == overwrite_policy
    assert len(packet["templates"]) == 1
    assert len(packet["expected_output_rel_paths"]) == 1


def test_prepare_stage2_falls_back_to_template_support_when_category_support_is_sparse(
    tmp_path,
):
    graph_dir = tmp_path / "book.storygraph"
    template_dir = tmp_path / "templates"
    graph_dir.mkdir()
    template_dir.mkdir()
    _write_stage1_inputs(graph_dir, template_dir)
    evidence_path = graph_dir / "coverage" / "evidence-index.json"
    evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
    evidence[0]["supports_templates"] = [
        {
            "template_name": "法宝分析",
            "requirement_id": "法宝分析.required_fields.法宝",
            "status": "covered",
        }
    ]
    evidence_path.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")

    prepare_stage2(graph_dir, template_dir, _stage2_config())

    packet = _read_single_packet(graph_dir)
    assert packet["evidence_ids"] == ["evidence:abc"]
