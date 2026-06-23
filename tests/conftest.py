import json
from pathlib import Path

import pytest


MANAGED_OUTPUTS = [
    "manifest.json",
    "graphify-out/graph.json",
    "graphify-out/GRAPH_REPORT.md",
    "graphify-out/graph.html",
    "requirements/template-requirements.json",
    "intermediate/agent-dispatch-plan.json",
    "intermediate/agent-dispatch-state.json",
    "intermediate/stage1-input-cache.json",
    "intermediate/task-packets/*/*.json",
    "intermediate/template-requirements-parts/*.json",
    "intermediate/chunks/*.txt",
    "intermediate/lane-outputs/*/*/*.json",
    "intermediate/reviewed-bundles/*.json",
    "intermediate/merge-queue.json",
    "coverage/review-findings.json",
    "coverage/chunk-ledger.json",
    "coverage/evidence-index.json",
    "coverage/template-readiness.json",
    "coverage/agent-run-ledger.json",
    "coverage/gap-report.md",
]


@pytest.fixture
def novel(tmp_path: Path) -> Path:
    path = tmp_path / "mini_novel.txt"
    path.write_text("第一章\n韩立获得小瓶。", encoding="utf-8")
    return path


@pytest.fixture
def template_dir(tmp_path: Path) -> Path:
    path = tmp_path / "templates"
    path.mkdir()
    (path / "法宝分析模板.md").write_text(
        "# 法宝分析模板\n## 字段\n- 法宝\n## 证据要求\n- 原文位置",
        encoding="utf-8",
    )
    return path


@pytest.fixture
def graph_dir(tmp_path: Path) -> Path:
    path = tmp_path / "mini_novel.storygraph"
    path.mkdir()
    return path


@pytest.fixture
def config(template_dir: Path) -> dict:
    return {
        "graph_dir_suffix": ".storygraph",
        "output_language": "zh-CN",
        "paths": {"template_dir": str(template_dir), "graphify_repo": None},
        "agent_platform": {
            "enabled": True,
            "default_agent_type": "codex",
            "agent_adapters": {
                "codex": {
                    "module": "storygraph_lib.adapters.codex_adapter",
                    "class": "CodexAdapter",
                    "config": {},
                }
            },
        },
        "template_discovery": {
            "glob": "*模板.md",
            "readme_index_file": "README.md",
            "exclude_files": ["README.md"],
            "readme_missing_policy": "warn",
        },
        "stage1_artifacts": {
            "requirements": "requirements/template-requirements.json",
            "agent_dispatch_plan": "intermediate/agent-dispatch-plan.json",
            "dispatch_state": "intermediate/agent-dispatch-state.json",
            "task_packet_dir": "intermediate/task-packets",
            "template_requirements_part_dir": "intermediate/template-requirements-parts",
            "input_cache": "intermediate/stage1-input-cache.json",
            "chunk_text_dir": "intermediate/chunks",
            "lane_output_dir": "intermediate/lane-outputs",
            "reviewed_bundle_dir": "intermediate/reviewed-bundles",
            "merge_queue": "intermediate/merge-queue.json",
            "review_findings": "coverage/review-findings.json",
            "canonical_graph": "graphify-out/graph.json",
            "agent_run_ledger": "coverage/agent-run-ledger.json",
        },
        "element_lanes": [
            {
                "lane_id": "entities_resources",
                "agent_role": "实体道具资源抽取 agent",
                "required": True,
                "schema": "lane-output.schema.json",
                "status_enum_ref": "status_enums.lane_output_statuses",
            }
        ],
        "status_enums": {
            "requirement_statuses": ["covered", "needs_review", "not_found_in_source"],
            "verification_statuses": ["verified", "needs_review", "rejected"],
            "confidence_levels": ["EXTRACTED", "INFERRED", "AMBIGUOUS"],
            "lane_output_statuses": ["pending", "completed", "blocked", "failed", "needs_repair"],
            "reviewer_statuses": ["pending", "passed", "failed", "blocked"],
            "finding_statuses": ["open", "closed", "waived"],
            "finding_severities": ["must_fix", "should_fix", "note"],
        },
        "review_policy": {"require_review_before_canonical_merge": True},
        "chunk_strategy": {
            "mode": "chapter-aware",
            "fallback_mode": "bounded-chars",
            "max_chars": 100,
            "overlap_chars": 0,
            "chapter_heading_patterns": ["^第.+章"],
        },
        "template_count_policy": {
            "expected_existing_templates": 1,
            "enforce_integration_count": False,
        },
        "writer_policy": {"managed_outputs": MANAGED_OUTPUTS},
    }


@pytest.fixture
def write_agent_template_requirements():
    def _write(graph_dir: Path) -> Path:
        path = graph_dir / "requirements" / "template-requirements.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "producer": "template-requirements-analysis-agent",
            "template_count": 1,
            "templates": [
                {
                    "template_name": "法宝分析",
                    "template_file": "templates/法宝分析模板.md",
                    "required_fields": ["法宝"],
                    "required_tables": [],
                    "required_cards": [],
                    "required_case_patterns": [],
                    "required_evidence_fields": ["原文位置"],
                    "graph_node_mapping": ["artifact"],
                    "graph_event_mapping": ["artifact_gain"],
                    "graph_relation_mapping": ["artifact_influence"],
                    "coverage_rules": {
                        "requirement_statuses": [
                            "covered",
                            "needs_review",
                            "not_found_in_source",
                        ]
                    },
                }
            ],
        }
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    return _write


@pytest.fixture
def write_lane_output():
    def _write(
        graph_dir: Path,
        *,
        chunk_id: str = "chunk-0001",
        lane_id: str = "entities_resources",
        status: str = "completed",
    ) -> Path:
        chunk_ledger = graph_dir / "coverage" / "chunk-ledger.json"
        if not chunk_ledger.exists():
            chunk_ledger.parent.mkdir(parents=True, exist_ok=True)
            chunk_ledger.write_text(
                json.dumps(
                    [
                        {
                            "chunk_id": chunk_id,
                            "source_path": "mini_novel.txt",
                            "source_range": [0, 12],
                            "chapter_hint": "第一章",
                            "hash": "test-hash",
                            "scanned_at": None,
                            "processor": "storygraph-stage1",
                            "extraction_status": "pending_agent_outputs",
                            "failure": None,
                            "retry_count": 0,
                            "target_lane_ids": [lane_id],
                            "required_lane_ids": [lane_id],
                            "lane_statuses": {lane_id: "pending_agent_outputs"},
                        }
                    ],
                    ensure_ascii=False,
                    indent=2,
                ),
                encoding="utf-8",
            )
        path = graph_dir / "intermediate" / "lane-outputs" / chunk_id / lane_id / "run-001.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "run_id": "run-001",
            "task_packet_id": f"{chunk_id}:{lane_id}:attempt-001",
            "chunk_id": chunk_id,
            "lane_id": lane_id,
            "agent_role": "实体道具资源抽取 agent",
            "model_or_agent_identity": "codex-subagent",
            "extracted_nodes": [],
            "extracted_edges": [],
            "extracted_events": [],
            "extracted_evidence": [],
            "supports_templates": [],
            "uncertainties": [],
            "rejected_candidates": [],
            "structured_failures": [],
            "output_status": status,
            "produced_at": "2026-06-20T00:00:00Z",
        }
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    return _write


@pytest.fixture
def write_review_finding():
    def _write(
        graph_dir: Path,
        *,
        chunk_id: str = "chunk-0001",
        lane_id: str = "entities_resources",
        status: str = "passed",
    ) -> Path:
        path = graph_dir / "coverage" / "review-findings.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = [
            {
                "review_id": "review-001",
                "chunk_id": chunk_id,
                "lane_id": lane_id,
                "reviewer_status": status,
                "findings": [],
            }
        ]
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        return path

    return _write
