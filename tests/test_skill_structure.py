from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skill-src" / "storygraph"
USER_FACING_DOCS = [
    SKILL / "SKILL.md",
    SKILL / "references" / "workflow.md",
    SKILL / "references" / "graph-schema.md",
    ROOT / "docs" / "storygraph-cli.md",
]
LEGACY_USER_FACING_TERMS = [
    "substring",
    "template_aware",
    "default_mapping",
    "template_graph_mappings",
    "evidence_matching_strategy",
]
UNSUPPORTED_STABLE_FAILURE_CODES = [
    "chunk_extraction_failure",
    "unparsable_subagent_json",
    "readiness_below_threshold",
    "template_without_reliable_evidence",
]


def test_skill_source_structure_exists():
    required = [
        "SKILL.md",
        "agents/openai.yaml",
        "references/workflow.md",
        "references/graph-schema.md",
        "references/extraction-workflow.md",
        "scripts/storygraph.py",
        "scripts/storygraph_lib/__init__.py",
        "scripts/storygraph_lib/cli.py",
    ]
    missing = [path for path in required if not (SKILL / path).exists()]
    assert missing == []


def test_stage1_docs_describe_agent_driven_not_python_semantic_extraction():
    text = (SKILL / "references" / "workflow.md").read_text(encoding="utf-8")

    assert "Codex 主 agent" in text
    assert "Python 只做 deterministic tool layer" in text
    assert "substring" not in text
    assert "template_aware" not in text


def test_cli_docs_include_prepare_ingest_merge_commands():
    text = (ROOT / "docs" / "storygraph-cli.md").read_text(encoding="utf-8")

    assert "prepare-stage1" in text
    assert "ingest-stage1" in text
    assert "merge-stage1" in text


def test_graph_schema_requires_agent_provenance_for_storygraph_items():
    text = (SKILL / "references" / "graph-schema.md").read_text(encoding="utf-8")

    assert "provenance" in text
    assert "semantic_generation" in text
    assert "chunk_ids" in text
    assert "lane_output_paths" in text
    assert "source_bundle_paths" in text
    assert "`semantic_generation`: `agent-produced`" in text
    assert "provenance` 校验必须失败关闭" in text


def test_user_facing_docs_do_not_describe_legacy_extraction_contracts():
    hits = []
    for path in USER_FACING_DOCS:
        text = path.read_text(encoding="utf-8")
        hits.extend(term for term in LEGACY_USER_FACING_TERMS if term in text)

    assert hits == []


def test_cli_docs_describe_stage1_exit_behavior():
    text = (ROOT / "docs" / "storygraph-cli.md").read_text(encoding="utf-8")

    for command in ["prepare-stage1", "ingest-stage1", "merge-stage1", "validate-graph"]:
        assert command in text
    assert "exit code `0`" in text
    assert "exit code `2`" in text
    assert "结构化 JSON" in text
    assert "Stage 1 动作命令" in text
    for field in ["`status`", "`error`", "`validation_errors`"]:
        assert field in text
    assert "`next_action`" in text
    assert "`validate-graph`" in text
    assert "`ok`" in text
    assert "`errors`" in text
    assert 'Stage 1 动作命令包含 `"ok": true`' not in text
    assert '失败输出包含 `"ok": false`' not in text


def test_stage1_docs_assign_template_requirements_to_agent_before_ingest():
    docs = [
        (ROOT / "docs" / "storygraph-cli.md").read_text(encoding="utf-8"),
        (SKILL / "references" / "workflow.md").read_text(encoding="utf-8"),
    ]

    for text in docs:
        prepare_lines = [line for line in text.splitlines() if "prepare-stage1" in line]
        assert all("模板需求矩阵" not in line for line in prepare_lines)
        assert "template-requirements-analysis-agent" in text
        assert "requirements/template-requirements.json" in text
        assert "在 `ingest-stage1` 前" in text


def test_stage1_workflow_documents_parallel_dispatch_plan_contract():
    text = (SKILL / "references" / "workflow.md").read_text(encoding="utf-8")

    assert "intermediate/agent-dispatch-plan.json" in text
    assert "execution_batches" in text
    assert "next-agent-batches" in text
    assert "stage1_runner_unavailable" in text
    assert "max_parallel_tasks" in text
    assert "并行" in text
    assert "等待所有 template requirements 分片产物" in text
    assert "不得在未派发 agent 时调用 ingest/merge 宣称完成" in text
    assert "ingest-template-requirements" in text


def test_repair_protocol_requires_reproduce_red_test_minimal_fix_and_regression():
    workflow = (SKILL / "references" / "workflow.md").read_text(encoding="utf-8")
    cli_docs = (ROOT / "docs" / "storygraph-cli.md").read_text(encoding="utf-8")

    for text in [workflow, cli_docs]:
        assert "repair agent 必须先复现 reviewer probe" in text
        assert "记录 actual 输出" in text
        assert "固化成 RED 测试" in text
        assert "最小修复" in text
        assert "目标测试" in text
        assert "回归测试" in text


def test_cli_docs_stable_failure_codes_are_implemented_subset_only():
    text = (ROOT / "docs" / "storygraph-cli.md").read_text(encoding="utf-8")
    hits = [code for code in UNSUPPORTED_STABLE_FAILURE_CODES if code in text]

    assert hits == []
