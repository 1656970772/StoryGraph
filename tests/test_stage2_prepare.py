import json
from pathlib import Path

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
            "grouping_strategy": "by_requirement_category",
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


def _write_stage1_inputs(graph_dir: Path, template_dir: Path) -> None:
    (template_dir / "法宝分析模板.md").write_text(
        "# 法宝分析\n\n## 来源\n\n## 用途\n",
        encoding="utf-8",
    )
    (graph_dir / "requirements").mkdir(parents=True)
    (graph_dir / "requirements" / "template-requirements.json").write_text(
        json.dumps(
            {
                "schema_version": "storygraph.template-requirements-summary.v1",
                "source_template_count": 1,
                "categories": [
                    {
                        "category_id": "resources_items_economy",
                        "category_name": "资源、物品与交易经济",
                        "template_coverage": ["法宝分析"],
                        "required_extraction_targets": ["法宝"],
                        "evidence_requirements": ["原文位置"],
                    }
                ],
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
                    }
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
                }
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


def test_prepare_stage2_groups_templates_by_requirement_category_and_writes_ledgers(tmp_path):
    graph_dir = tmp_path / "book.storygraph"
    template_dir = tmp_path / "templates"
    graph_dir.mkdir()
    template_dir.mkdir()
    _write_stage1_inputs(graph_dir, template_dir)

    result = prepare_stage2(graph_dir, template_dir, _stage2_config())

    assert result["status"] == "prepared"
    assert result["batch_count"] == 1
    packet_path = graph_dir / "intermediate" / "stage2" / "task-packets" / "resources_items_economy.json"
    packet = json.loads(packet_path.read_text(encoding="utf-8"))
    assert packet["category_id"] == "resources_items_economy"
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

    packet = json.loads(
        (
            graph_dir
            / "intermediate"
            / "stage2"
            / "task-packets"
            / "resources_items_economy.json"
        ).read_text(encoding="utf-8")
    )
    assert packet["evidence_ids"] == ["evidence:abc"]
