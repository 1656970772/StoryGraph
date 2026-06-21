# StoryGraph Stage 1 Agent-Driven Rewrite Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 StoryGraph Stage 1 从旧的 Python 模板/规则/substring 语义抽取路径，重写为 agent-driven 建图流程：Codex 主 agent/子 agent 产出语义抽取，Python 只承担确定性工具层。

**Architecture:** Stage 1 采用 Orchestrator + Fan-out/Fan-in + Review-before-merge 架构。Python 负责配置加载、路径解析、分块、task packet、schema 校验、归一化、去重、写盘、ledger、manifest、canonical merge 和 graphify adapter；模板需求、lane outputs、review findings、repair outputs 必须来自真实 agent 产物文件，Python 不再根据模板、规则、substring、mapping 直接制造实体/事件/证据。

**Tech Stack:** Python 3 标准库、pytest、JSON artifacts、PowerShell UTF-8 命令、现有 StoryGraph skill 目录结构、可选 graphify adapter。

---

## Scope Check

本计划只覆盖 Stage 1 agent-driven rewrite。它不实现 Stage 2 文档渲染，不调用外部 graphify 仓库做语义抽取，不修改 `E:\Github_Projects\graphify`；实施本计划前的计划修订阶段不改代码、不执行删除。

本次开发、测试和最终交付的硬性语料范围：

- 原文必须使用完整《凡人修仙传》原文：`E:\AI_Projects\CultivationWorld\docs\世界观参考\凡人修仙传\凡人修仙传.txt`
- 模板必须使用完整模板目录：`E:\AI_Projects\CultivationWorld\docs\世界观参考\模板`
- 最终结果必须基于全文，不能只基于局部章节、局部段落、单个 chunk 或 `tests/fixtures/mini_novel.txt`。
- 最终结果必须包含全部模板，所有模板都要处理，并且都要进入最终结果覆盖范围，不能用单模板结果冒充完成。
- 中间调试允许临时使用一个模板，或截取“第几章第几段”、单个 chunk、分块内容做小范围验证；这些只允许作为中间诊断手段，不能替代最终验收。
- 不要求中间执行时间长短，但必须完整、准确、按 agent-driven 流程执行；不允许为了省时间跳过 Agent 产物、review、repair、全量覆盖校验，也不允许用局部样例代替最终交付。

成功标准：

- 旧 Python 语义抽取路径被删除，不保留“降级为 schema/validation 工具”的兼容路径。
- `template_aware.py` 从代码库删除。
- `template_rules.py` 不再从模板 Markdown 推断需求矩阵；模板需求矩阵只能来自 agent output 或显式手工 override。
- `build-stage1` 或拆分后的 Stage 1 CLI 不会在缺少 reviewed agent outputs 时写出“成功”的 canonical graph。
- canonical graph 只从 reviewed lane outputs / reviewed chunk bundles / reviewed merge queue 构建。
- agent-run-ledger 能追溯 task packet、lane output、review finding、repair output。
- graphify adapter 只做可选适配/可视化/查询增强，不替代 agent semantic production。
- 测试证明 Python substring/mapping 补图已经不可用。

## 当前仓库核验摘要

已读取重点文件：

- `docs/superpowers/specs/2026-06-19-storygraph-skill-design.md`
- `docs/superpowers/plans/2026-06-19-storygraph-skill-implementation-plan.md`
- `docs/superpowers/plans/2026-06-20-storygraph-stage2-extraction-implementation-plan.md`
- `skill-src/storygraph/config/storygraph.default.json`
- `skill-src/storygraph/scripts/storygraph_lib/*.py`
- `tests/*.py`

关键现状：

- `stage1.py` 直接导入并调用 `extract_template_aware_supplements`。
- `template_aware.py` 读取小说全文，用 `_find_evidence()` 做 substring 匹配，并直接生成 nodes、edges、events、evidence_index、template-readiness。
- `templates.py` 调用 `parse_template_requirements()`，并通过 `template_graph_mappings/default_mapping` 或 `template_parse_result` 生成 graph mappings。
- `storygraph.default.json` 仍包含 `template_parser_rules`、`template_graph_mappings.default_mapping`、`supplemental_graph_policy`、`evidence_matching_strategy.mode = substring`。
- `agent_ledger.py` 当前用 `make_stage_agent_records()` 伪造阶段级 agent records：`模板需求分析`、`图抽取`、`覆盖审查`、`质量审查`，但没有真实 lane output/task packet/review finding 级追踪。
- `tests/test_template_aware.py`、`tests/test_template_rules.py`、`tests/test_stage1.py::test_stage1_build_merges_real_template_aware_supplements` 明确保护旧 Python 语义路径，需要删除或重写。

核验命令：

```powershell
$env:PYTHONIOENCODING = "utf-8"; [Console]::OutputEncoding = [Text.Encoding]::UTF8; $OutputEncoding = [Text.Encoding]::UTF8; chcp 65001 > $null
$matches = rg -n "template_aware|template_rules|template_graph_mappings|default_mapping|evidence_matching|substring|extract_template_aware_supplements|merge_template_supplements" skill-src tests
if ($LASTEXITCODE -eq 0) { $matches }
elseif ($LASTEXITCODE -eq 1) { "PASS: no legacy semantic path strings found." }
else { throw "rg failed with unexpected exit code $LASTEXITCODE" }
```

预期：改造前能命中旧路径；改造完成后不应再命中 Stage 1 语义生产路径，允许 `merge_template_supplements` 被重命名或替换为 reviewed agent output merge。

---

## 现状判定与处置矩阵

| 模块/文件 | 当前职责 | 处置 | 新边界 |
| --- | --- | --- | --- |
| `storygraph_lib/stage1.py` | 串联模板发现、Python 模板矩阵、chunk、substring supplement、graphify merge、coverage | 改造 | Stage 1 orchestrator 只做 prepare/ingest/merge 的确定性编排；不得调用 Python semantic extractor |
| `storygraph_lib/template_aware.py` | Python 根据模板需求和 substring 生成节点/边/事件/证据/readiness | 删除 | 删除模块；相关 graph/evidence/readiness 只能来自 agent lane outputs 或 reviewed bundles |
| `storygraph_lib/template_rules.py` | Python 解析模板 Markdown，推断字段/表格/卡片/证据/gap rules | 删除 | 删除模块；如需校验 agent-produced template requirements，应新建 schema validator 模块，不复用旧模板解析规则 |
| `storygraph_lib/templates.py` | 模板发现 + Python 构建需求矩阵 + mapping resolution | 改造 | 保留 template discovery；移除 `build_requirement_matrix` 的语义解析/默认 mapping，新增 `validate_template_requirements_payload` 或移到新模块 |
| `storygraph_lib/coverage.py` | chunk ledger、coverage outputs | 保留并改造 | 保留分块；chunk ledger 增加 required lanes、lane statuses、structured failures；不保存语义结论 |
| `storygraph_lib/agent_ledger.py` | 阶段级 agent ledger 和 single-writer 校验 | 改造 | ledger 记录真实 task packet、lane output、review、repair、attempt、repair_of；禁止伪造 completed agent run |
| `storygraph_lib/graph_schema.py` | canonical graph schema、merge supplement、validate graph | 保留并改造 | 保留 schema 校验；merge 输入改为 reviewed agent outputs/chunk bundles；移除 “template supplement” 语义暗示 |
| `storygraph_lib/graphify_adapter.py` | 调用 graphify CLI/local repo | 保留并改造 | 只接受 canonical graph 或作为 post-process adapter；不得从小说 source 替代 agent 建语义图 |
| `storygraph_lib/output_writer.py` | managed output 和路径安全 | 保留 | 继续作为 single-writer 写盘底座 |
| `storygraph_lib/config.py` | 配置合并 | 保留 | 增加 Stage 1 agent-driven 配置键，拒绝旧 semantic extraction 配置键或迁移警告 |
| `storygraph_lib/paths.py` | 小说路径、hash、graph dir | 保留 | 只负责路径/文件 hash，不参与语义 |
| `storygraph_lib/manifest.py` | manifest 写入 | 保留并小改 | manifest 记录 stage1 mode、agent-driven schema version、canonical writer version |
| `storygraph_lib/state.py` | 幂等和重用判断 | 保留并改造 | input hash 包含 config、template files、task packet schema、reviewed output manifest，不包含 graphify semantic result |
| `storygraph_lib/validation.py` | validate skill/graph/template 等 | 保留并加强 | 校验 agent-run-ledger、review-findings、task packets、lane outputs、canonical 来源 |
| `tests/test_template_aware.py` | 保护 Python substring semantic supplements | 测试重写 | 拆出 chunk/output_writer 测试；删除 semantic supplement 测试 |
| `tests/test_template_rules.py` | 保护 Python 模板解析规则 | 删除或重写 | 改成 agent template requirements schema RED 测试 |
| `tests/test_templates.py` | 保护 mapping/default_mapping/template_parse_result | 重写 | 保留 discovery；移除 default_mapping 成功路径；验证 agent-produced matrix |
| `tests/test_stage1.py` | 混合 Stage 1 成功、graphify、coverage、旧 supplement | 重写 | 新增 prepare/ingest/merge/review-before-merge 测试 |
| `tests/test_graph_schema.py` | graph schema validation | 保留并收紧 | 增加 canonical graph provenance 必须指向 reviewed agent output |
| `tests/test_agent_ledger.py` | ledger/writer 基础 | 保留并扩展 | 增加 task packet、lane output、review、repair attempt 契约 |

---

## 删除清单

必须删除的旧 Python 语义抽取对象：

1. `skill-src/storygraph/scripts/storygraph_lib/template_aware.py`
   - 删除 `extract_template_aware_supplements()`
   - 删除 `_find_evidence()`
   - 删除 `_template_requirements()`
   - 删除 `_first_mapping()`
   - 删除 Python 直接生成 `nodes`、`edges`、`events`、`evidence_index`、`template-readiness` 的逻辑
   - 删除 `"evidence_matching_strategy": "substring"` metadata

2. `skill-src/storygraph/scripts/storygraph_lib/stage1.py`
   - 删除 `from .template_aware import extract_template_aware_supplements`
   - 删除对 `extract_template_aware_supplements(...)` 的调用
   - 删除“graphify base graph + Python supplement merge = canonical graph”的成功路径
   - 删除 `_complete_pending_chunks()` 把 pending chunk 直接标 completed 的语义假完成路径
   - 删除 `_parse_subagent_payloads()` 从 config 读取 `agent_policy.sub_agent_json_payloads` 的旧 probe 入口，改为读取 agent output files

3. `skill-src/storygraph/scripts/storygraph_lib/template_rules.py`
   - 删除该模块文件
   - 删除 `parse_template_requirements()` 作为 Stage 1 自动模板需求生产者的职责
   - 删除 `field_headings`、`table_markers`、`card_markers`、`case_markers`、`evidence_markers`、`gap_markers` 推断需求矩阵的运行路径
   - 如仍需要 template requirements 校验能力，只能新建 `template_requirements_schema.py` 或类似 validator；不得从旧 `template_rules.py` 迁移模板正文解析/推断逻辑

4. `skill-src/storygraph/scripts/storygraph_lib/templates.py`
   - 删除 `build_requirement_matrix(...)`
   - 删除 `_resolve_mapping(...)` 的 `default_mapping` fallback
   - 删除 `mapping_source == "template_parse_result"` 的自动 graph mapping 生产
   - 保留 `discover_templates(...)`、`TemplateFile`、`TemplateDiscovery`、README missing warning

5. `skill-src/storygraph/config/storygraph.default.json`
   - 删除 `template_parser_rules`
   - 删除 `template_graph_mappings`
   - 删除 `template_graph_mappings.default_mapping`
   - 删除 `supplemental_graph_policy`
   - 删除 `evidence_matching_strategy`
   - 删除 `stages.build_template_aware_graph`；如需新 stage 开关，使用新的 agent-driven 配置键
   - 替换 `agent_policy` 为 `agent_orchestration`、`element_lanes`、`review_policy`、`retry_repair_policy`、`canonical_graph_writer`

6. 旧测试删除/重写对象
   - 删除 `tests/test_template_aware.py::test_extract_template_aware_supplements_creates_graph_items_readiness_and_evidence_links`
   - 删除旧的固定模板数量 readiness 断言；历史测试名 `tests/test_template_aware.py::test_extract_template_aware_supplements_reports_one_readiness_record_per_37_templates` 只反映旧样例数量，不作为新契约
   - 删除或重写 `tests/test_template_rules.py`
   - 重写 `tests/test_stage1.py::test_stage1_build_merges_real_template_aware_supplements`
   - 重写 `tests/test_stage1.py` 中依赖 `evidence_matching_strategy`、`template_graph_mappings` 的 fixture config
   - 重写 `tests/test_templates.py` 中保护 `default_mapping`、`template_parse_result` 的断言

待核验项及命令：

```powershell
$env:PYTHONIOENCODING = "utf-8"; [Console]::OutputEncoding = [Text.Encoding]::UTF8; $OutputEncoding = [Text.Encoding]::UTF8; chcp 65001 > $null
$matches = rg -n "default_mapping|template_parse_result|evidence_matching_strategy|template_parser_rules|supplemental_graph_policy|extract_template_aware_supplements|No substring evidence found" skill-src tests
if ($LASTEXITCODE -eq 0) { $matches; "Reviewer must confirm matches are only legacy rejection tests or migration notes." }
elseif ($LASTEXITCODE -eq 1) { "PASS: no legacy semantic path strings found." }
else { throw "rg failed with unexpected exit code $LASTEXITCODE" }
```

预期：改造完成后 exit code `1` 且无输出为 PASS；如出现在迁移测试中，测试名必须明确是“reject legacy config/legacy path”。

---

## 保留底座清单

| 底座 | 保留职责 | 禁止职责 |
| --- | --- | --- |
| 路径解析 `paths.py` | 解析 source、novel_name、graph_dir、source_hash | 不根据文件名/路径推断实体、事件、模板意义 |
| 配置加载 `config.py` | default/local/CLI 合并、坏 JSON/UTF-8/shape 结构化错误 | 不把旧模板 mapping 或 lane 列表写死在代码中 |
| manifest `manifest.py` | 记录 source/config/schema/canonical writer/agent-driven status | 不记录伪造 agent success |
| chunk ledger `coverage.py` | 分块、source_range、chunk text path、lane statuses | 不把 chunk 标 completed，除非 required lane output 通过校验或 structured_failure 存在 |
| schema 校验 `graph_schema.py` | 校验 canonical graph、evidence、supports_templates、状态枚举 | 不生成语义节点/边/事件 |
| output writer `output_writer.py` | managed outputs、路径安全、single-writer | 不绕过 writer 写正式文档或 graph artifacts |
| agent-run-ledger `agent_ledger.py` | 记录真实 task packet、agent output、review、repair attempt | 不自动生成 completed semantic agent run |
| canonical graph writer/merge | 归一化、去重、稳定 ID、冲突标记、merge queue | 不从模板字段或 substring 制造 graph facts |
| graphify adapter | 可选可视化/查询增强、adapter 失败 ledger | 不作为 Stage 1 semantic producer |
| validation `validation.py` | 验证 artifacts 完整性和边界错误 | 不修复或补造缺失语义 |

---

## 新 Agent-Driven Stage 1 流程

### 产物目录

```text
<novel>.storygraph/
  manifest.json
  requirements/
    template-requirements.json
  coverage/
    chunk-ledger.json
    evidence-index.json
    template-readiness.json
    agent-run-ledger.json
    review-findings.json
    gap-report.md
  intermediate/
    chunks/
      chunk-0001.txt
      chunk-0001/
        chunk-extraction-bundle.json
    task-packets/
      template-requirements/
        batch-0001.json
        batch-0002.json
      chunk-0001/entities_resources.json
      chunk-0001/event_causality.json
    template-requirements-parts/
      batch-0001.json
      batch-0002.json
    lane-outputs/
      chunk-0001/entities_resources/run-001.json
    review-findings/
      finding-001.json
    merge-queue.json
  graphify-out/
    graph.json
    GRAPH_REPORT.md
    graph.html
```

### 流程

1. 主 agent 读取配置和 workflow，确认 Stage 1 agent-driven 模式。
2. Python `prepare-stage1`：
   - 解析 source/template dir/graph dir。
   - 写 manifest。
   - 扫描模板文件，仅生成 template file inventory。
   - 分块并写 chunk text files。
   - 根据配置 `element_lanes` 生成 task packets。
   - 初始化 chunk-ledger 和 agent-run-ledger pending records。
3. 模板需求分析 agents：
   - 读取 `intermediate/task-packets/template-requirements/batch-*.json`。
   - 每个分片 agent 负责 1-5 个模板，读取对应模板 Markdown。
   - 输出 `intermediate/template-requirements-parts/batch-*.json`。
   - `ingest-stage1` 校验所有分片并汇总写出 `requirements/template-requirements.json`；最终汇总文件不绑定固定 producer。
4. chunk-lane extraction agents：
   - 每个 agent 只读取自己的 task packet 和 chunk text。
   - 输出 lane JSON 到 `intermediate/lane-outputs/<chunk_id>/<lane_id>/<run_id>.json`。
   - lane output 包含 extracted_nodes、extracted_edges、extracted_events、extracted_evidence、supports_templates、uncertainties、structured_failures。
5. reviewer agents：
   - chunk-lane reviewer：检查 lane schema、证据范围、lane contract。
   - chunk coverage reviewer：检查 required lanes 是否齐全或 structured failure 是否合格。
   - global merge reviewer：检查跨 chunk 合并、同名异物、别名、长程因果。
   - template readiness reviewer：检查所有模板 requirement_statuses。
   - quality reviewer：检查 manifest、ledger、writer policy、canonical provenance。
6. repair agent：
   - reviewer 发现必修问题时，主 agent 必须启动新的 repair agent。
   - review finding 必须记录 probe/input/actual/expected。
   - repair output 必须设置 `repair_of` 并产生新的 `run_id`。
7. Python `ingest-stage1`：
   - 读取 template requirements、lane outputs、review findings。
   - 校验 JSON/schema/source ranges/状态枚举/路径安全。
   - 生成 chunk extraction bundle。
   - 未 review passed 的 bundle 不进入 merge queue。
8. Python `merge-stage1`：
   - 只读取 reviewed bundle / reviewed repair output。
   - 归一化、去重、稳定 ID、冲突保留。
   - 写 canonical `graphify-out/graph.json`。
   - 写 evidence-index、template-readiness、merge-queue、review-findings、agent-run-ledger。
9. graphify adapter：
   - 只在 canonical graph 已生成后运行。
   - 默认 failure policy 应为 degraded visualization/query，不得导致 Python 退回 source substring semantic extraction。
   - 如果配置为 blocking，阻塞 adapter 产物，但不伪造 semantic success。

---

## 配置化改造目标

新增或替换配置键：

```json
{
  "stage1_mode": "agent-driven",
  "stage1_artifacts": {
    "task_packet_dir": "intermediate/task-packets",
    "template_requirements_part_dir": "intermediate/template-requirements-parts",
    "chunk_text_dir": "intermediate/chunks",
    "lane_output_dir": "intermediate/lane-outputs",
    "review_finding_dir": "intermediate/review-findings",
    "merge_queue": "intermediate/merge-queue.json"
  },
  "template_requirements_strategy": {
    "mode": "agent-produced",
    "agent_role": "template-requirements-analysis-agent",
    "templates_per_packet": 5,
    "allow_manual_overrides": true,
    "python_validate_only": true
  },
  "element_lanes": [
    {
      "lane_id": "entities_resources",
      "required": true,
      "agent_role": "实体道具资源抽取 agent",
      "schema": "lane-output.schema.json"
    },
    {
      "lane_id": "event_causality",
      "required": true,
      "agent_role": "事件因果抽取 agent",
      "schema": "lane-output.schema.json"
    }
  ],
  "agent_orchestration": {
    "enabled": true,
    "primary_producer": "codex-agents",
    "python_role": "deterministic-tool-layer",
    "max_parallel_agents": 8,
    "max_parallel_lanes_per_chunk": 4,
    "batch_size_chunks": 8,
    "write_conflict_policy": "single-writer",
    "require_real_agent_runs": true
  },
  "review_policy": {
    "enabled": true,
    "reviewers": [
      "chunk-lane-reviewer",
      "chunk-coverage-reviewer",
      "global-merge-reviewer",
      "template-readiness-reviewer",
      "quality-reviewer"
    ],
    "require_review_before_canonical_merge": true,
    "require_new_repair_agent": true
  },
  "retry_repair_policy": {
    "max_attempts_per_lane": 2,
    "max_repair_attempts_per_finding": 2,
    "record_probe_in_review_findings": true,
    "block_on_required_lane_failure": true
  },
  "canonical_graph_writer": {
    "implementation": "python-deterministic-writer",
    "allowed_inputs": ["reviewed_lane_outputs", "reviewed_chunk_extraction_bundles"],
    "semantic_generation": "disabled",
    "fail_stage_if_canonical_merge_fails": true
  },
  "graphify_adapter": {
    "enabled": true,
    "input_strategy": "canonical-graph-or-graph-dir-only",
    "allowed_input_strategies": ["canonical-graph-or-graph-dir-only"],
    "failure_policy": "degrade-visualization-and-query",
    "allowed_failure_policies": ["degrade-visualization-and-query", "blocking"]
  },
  "status_enums": {
    "lane_output_statuses": ["pending", "completed", "blocked", "failed", "needs_repair"],
    "reviewer_statuses": ["pending", "passed", "failed", "blocked"],
    "finding_statuses": ["open", "closed", "waived"],
    "finding_severities": ["must_fix", "should_fix", "note"],
    "structured_failure_statuses": ["blocking", "rebuild_required", "degraded", "not_applicable"]
  }
}
```

必须移除旧配置键：

```json
[
  "template_parser_rules",
  "template_graph_mappings",
  "supplemental_graph_policy",
  "evidence_matching_strategy"
]
```

配置化检查：

- lane 列表、required 标记、agent_role、schema 来自 `element_lanes`。
- 状态枚举来自 `status_enums`。
- review 角色来自 `review_policy.reviewers`。
- retry/repair 策略来自 `retry_repair_policy`。
- artifact 路径来自 `stage1_artifacts` 和 `writer_policy.managed_outputs`。
- 模板数量来自模板发现结果和 `template_count_policy`，不写死固定数量；当前 CultivationWorld 样例/默认集成检查值可配置为 37。
- graphify adapter 的 `failure_policy`、allowed failure policies、adapter 输入策略必须来自 `graphify_adapter`，且 adapter 只能接受 canonical graph path 或 graph dir。
- lane output statuses、reviewer statuses、finding statuses/severities、structured failure statuses 必须来自 `status_enums`，实现逻辑不得在函数体内另写一套枚举。
- 上方 `element_lanes` 是最小默认/测试默认示例；正式默认配置应以配置项为准，允许项目规则定义完整 spec lane 列表。

---

## 测试处置矩阵

| 测试文件 | 处置 | 新测试方向 |
| --- | --- | --- |
| `tests/test_template_aware.py` | 拆分/删除 | chunk ledger 和 coverage writer 测试迁移到 `tests/test_stage1_task_packets.py` 或 `tests/test_coverage.py`；删除 semantic supplement 测试 |
| `tests/test_template_rules.py` | 删除或重写 | 改为 `tests/test_template_requirements_contract.py`，验证 agent-produced requirements schema |
| `tests/test_templates.py` | 重写 | 保留 template discovery；删除 default_mapping 成功路径；新增 legacy mapping config rejected |
| `tests/test_stage1.py` | 大幅重写 | prepare packets、ingest lane outputs、review-before-merge、repair loop、canonical provenance、graphify degraded/blocking |
| `tests/test_stage1_idempotency.py` | 保留并改造 | hash 包含 task packet schema、requirements hash、reviewed output manifest |
| `tests/test_agent_ledger.py` | 保留并扩展 | lane run record、review record、repair_of、attempt、新 repair agent 校验 |
| `tests/test_graph_schema.py` | 保留并收紧 | canonical graph 必须有 provenance 到 reviewed agent output |
| `tests/test_validation_cli.py` | 保留并扩展 | validate graph 检查 task packets、lane outputs、review findings、agent-run-ledger |
| `tests/test_graphify_adapter.py` | 保留并改造 | graphify 不可替代 semantic producer；adapter failure policy 可配置 |
| `tests/test_config.py` | 保留并扩展 | legacy semantic config keys rejected 或 migration warning |

---

## 共享测试 Fixture/Helper 约定

Task 9-11 的 RED tests 必须先创建或扩展 `tests/conftest.py`，避免测试片段引用未定义对象。执行者可按需拆到测试文件本地 helper，但如果拆分，函数名和行为必须保持一致。

下面的 `tests/fixtures/mini_novel.txt` 只能作为 smoke/contract fixture 或中间诊断，不得替代最终验收。最终验收必须另跑完整原文 `E:\AI_Projects\CultivationWorld\docs\世界观参考\凡人修仙传\凡人修仙传.txt` + 全部模板目录 `E:\AI_Projects\CultivationWorld\docs\世界观参考\模板` 的流程。

```python
import json
import shutil
from pathlib import Path

import pytest


def _write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


@pytest.fixture
def novel(tmp_path):
    source = Path("tests/fixtures/mini_novel.txt")
    target = tmp_path / "mini_novel.txt"
    shutil.copyfile(source, target)
    return target


@pytest.fixture
def template_dir(tmp_path):
    path = tmp_path / "templates"
    path.mkdir()
    (path / "法宝分析模板.md").write_text(
        "# 法宝分析模板\n\n## 必填字段\n- 法宝\n- 原文位置\n",
        encoding="utf-8",
    )
    return path


@pytest.fixture
def graph_dir(tmp_path):
    path = tmp_path / "mini_novel.storygraph"
    path.mkdir()
    return path


@pytest.fixture
def config(tmp_path):
    return {
        "stage1_mode": "agent-driven",
        "stage1_artifacts": {
            "task_packet_dir": "intermediate/task-packets",
            "chunk_text_dir": "intermediate/chunks",
            "lane_output_dir": "intermediate/lane-outputs",
            "review_finding_dir": "intermediate/review-findings",
            "reviewed_bundle_dir": "intermediate/reviewed-bundles",
            "merge_queue": "intermediate/merge-queue.json",
        },
        "template_requirements_strategy": {
            "mode": "agent-produced",
            "agent_role": "template-requirements-analysis-agent",
            "templates_per_packet": 5,
            "python_validate_only": True,
            "allow_manual_overrides": True,
        },
        "element_lanes": [
            {
                "lane_id": "entities_resources",
                "required": True,
                "agent_role": "实体道具资源抽取 agent",
                "schema": "lane-output.schema.json",
            }
        ],
        "review_policy": {
            "enabled": True,
            "reviewers": ["chunk-lane-reviewer", "chunk-coverage-reviewer"],
            "require_review_before_canonical_merge": True,
            "require_new_repair_agent": True,
        },
        "retry_repair_policy": {
            "max_attempts_per_lane": 2,
            "max_repair_attempts_per_finding": 2,
            "record_probe_in_review_findings": True,
            "block_on_required_lane_failure": True,
        },
        "canonical_graph_writer": {
            "implementation": "python-deterministic-writer",
            "allowed_inputs": ["reviewed_chunk_extraction_bundles"],
            "semantic_generation": "disabled",
            "fail_stage_if_canonical_merge_fails": True,
        },
        "graphify_adapter": {
            "enabled": False,
            "input_strategy": "canonical-graph-or-graph-dir-only",
            "allowed_input_strategies": ["canonical-graph-or-graph-dir-only"],
            "failure_policy": "degrade-visualization-and-query",
            "allowed_failure_policies": ["degrade-visualization-and-query", "blocking"],
        },
        "status_enums": {
            "lane_output_statuses": ["pending", "completed", "blocked", "failed", "needs_repair"],
            "reviewer_statuses": ["pending", "passed", "failed", "blocked"],
            "finding_statuses": ["open", "closed", "waived"],
            "finding_severities": ["must_fix", "should_fix", "note"],
            "structured_failure_statuses": ["blocking", "rebuild_required", "degraded", "not_applicable"],
        },
        "writer_policy": {
            "managed_outputs": [
                "coverage/agent-run-ledger.json",
                "coverage/review-findings.json",
                "requirements/template-requirements.json",
                "intermediate/merge-queue.json",
                "graphify-out/graph.json",
            ]
        },
    }


@pytest.fixture
def config_with_graphify_success(config):
    config["graphify_adapter"]["enabled"] = True
    config["graphify_adapter"]["failure_policy"] = "degrade-visualization-and-query"
    return config


def _write_agent_template_requirements(graph_dir: Path) -> Path:
    path = graph_dir / "requirements" / "template-requirements.json"
    _write_json(
        path,
        {
            "templates": [
                {
                    "template_name": "法宝分析",
                    "template_file": "法宝分析模板.md",
                    "required_fields": ["法宝", "原文位置"],
                    "required_tables": [],
                    "required_cards": [],
                    "required_case_patterns": [],
                    "required_evidence_fields": ["原文位置"],
                    "graph_node_mapping": ["artifact"],
                    "graph_event_mapping": ["artifact_event"],
                    "graph_relation_mapping": ["artifact_relation"],
                    "coverage_rules": {
                        "requirement_statuses": ["covered", "needs_review", "not_found_in_source"]
                    },
                }
            ],
        },
    )
    return path


def _write_lane_output(graph_dir: Path, chunk_id: str, lane_id: str, status: str = "completed") -> Path:
    path = graph_dir / "intermediate" / "lane-outputs" / chunk_id / lane_id / "run-001.json"
    _write_json(
        path,
        {
            "run_id": "run-001",
            "task_packet_id": f"stage1:{chunk_id}:{lane_id}",
            "chunk_id": chunk_id,
            "lane_id": lane_id,
            "agent_role": "实体道具资源抽取 agent",
            "model_or_agent_identity": "codex-subagent",
            "extracted_nodes": [
                {
                    "id": "node:artifact:xiaoping",
                    "label": "小瓶",
                    "node_type": "artifact",
                    "evidence_ids": ["evidence:1"],
                    "source_locator": "tests/fixtures/mini_novel.txt#char=0-12",
                }
            ],
            "extracted_edges": [],
            "extracted_events": [],
            "extracted_evidence": [
                {
                    "evidence_id": "evidence:1",
                    "source_range": [0, 12],
                    "source_locator": "tests/fixtures/mini_novel.txt#char=0-12",
                    "chunk_id": chunk_id,
                    "fact_summary": "韩立获得小瓶",
                }
            ],
            "supports_templates": [
                {"template_name": "法宝分析", "requirement_id": "r1", "status": "covered"}
            ],
            "uncertainties": [],
            "rejected_candidates": [],
            "structured_failures": [],
            "output_status": status,
            "produced_at": "2026-06-20T00:00:00Z",
        },
    )
    return path


def _write_review_finding(graph_dir: Path, status: str = "passed") -> Path:
    path = graph_dir / "intermediate" / "review-findings" / "finding-001.json"
    payload_status = "closed" if status == "passed" else "open"
    _write_json(
        path,
        {
            "finding_id": "finding-001",
            "reviewer_role": "chunk-lane-reviewer",
            "stage": "stage1",
            "chunk_id": "chunk-0001",
            "lane_id": "entities_resources",
            "probe_or_sample": "pytest tests/test_stage1.py::test_stage1_merge_success_uses_reviewed_agent_outputs -v",
            "actual_output": status,
            "expected_output": "passed",
            "severity": "note" if status == "passed" else "must_fix",
            "status": payload_status,
            "repair_required": status != "passed",
            "repair_agent_run_id": None,
        },
    )
    return path


def _write_reviewed_chunk_bundle(graph_dir: Path) -> Path:
    path = graph_dir / "intermediate" / "reviewed-bundles" / "chunk-0001.json"
    _write_json(
        path,
        {
            "chunk_id": "chunk-0001",
            "ready_for_merge": True,
            "reviewer_status": "passed",
            "lane_output_paths": ["intermediate/lane-outputs/chunk-0001/entities_resources/run-001.json"],
            "normalized_nodes": [
                {
                    "id": "node:artifact:xiaoping",
                    "label": "小瓶",
                    "node_type": "artifact",
                    "evidence_ids": ["evidence:1"],
                    "source_locator": "tests/fixtures/mini_novel.txt#char=0-12",
                    "provenance": {
                        "lane_output_paths": ["intermediate/lane-outputs/chunk-0001/entities_resources/run-001.json"]
                    },
                }
            ],
            "normalized_edges": [],
            "normalized_events": [],
            "normalized_evidence": [
                {
                    "evidence_id": "evidence:1",
                    "source_range": [0, 12],
                    "source_locator": "tests/fixtures/mini_novel.txt#char=0-12",
                    "chunk_id": "chunk-0001",
                    "fact_summary": "韩立获得小瓶",
                }
            ],
        },
    )
    return path


def _write_graph(graph_dir: Path, graph: dict) -> Path:
    path = graph_dir / "graphify-out" / "graph.json"
    _write_json(path, graph)
    return path


def make_minimal_graph_dir_without_agent_outputs(tmp_path) -> Path:
    path = tmp_path / "legacy_missing_agents.storygraph"
    path.mkdir()
    _write_json(path / "manifest.json", {"stage1_mode": "agent-driven"})
    _write_graph(
        path,
        {
            "nodes": [],
            "edges": [],
            "hyperedges": [],
            "events": [],
            "evidence_index": [],
            "metadata": {"semantic_generation": "unknown"},
        },
    )
    return path


@pytest.fixture(name="make_minimal_graph_dir_without_agent_outputs")
def make_minimal_graph_dir_without_agent_outputs_public():
    return make_minimal_graph_dir_without_agent_outputs


@pytest.fixture
def graph_dir_without_agent_outputs(tmp_path):
    return make_minimal_graph_dir_without_agent_outputs(tmp_path)


@pytest.fixture
def write_agent_template_requirements():
    return _write_agent_template_requirements


@pytest.fixture
def write_lane_output():
    return _write_lane_output


@pytest.fixture
def write_review_finding():
    return _write_review_finding


@pytest.fixture
def write_reviewed_chunk_bundle():
    return _write_reviewed_chunk_bundle


@pytest.fixture
def write_graph():
    return _write_graph


@pytest.fixture
def graph_dir_with_reviewed_outputs(graph_dir):
    _write_agent_template_requirements(graph_dir)
    _write_lane_output(graph_dir, chunk_id="chunk-0001", lane_id="entities_resources", status="completed")
    _write_review_finding(graph_dir, status="passed")
    _write_reviewed_chunk_bundle(graph_dir)
    return graph_dir
```

---

## Bite-Sized Tasks

### Task 1: Legacy Semantic Path Guard

**Files:**

- Modify: `tests/test_stage1.py`
- Modify: `tests/test_config.py`
- Modify: `tests/test_templates.py`
- Delete or rewrite: `tests/test_template_aware.py`
- Delete or rewrite: `tests/test_template_rules.py`

**RED tests:**

新增测试：

```python
def test_stage1_does_not_import_template_aware_semantic_extractor():
    import inspect
    import storygraph_lib.stage1 as stage1

    source = inspect.getsource(stage1)
    assert "extract_template_aware_supplements" not in source
    assert "template_aware" not in source
```

```python
def test_default_config_rejects_legacy_python_semantic_extraction_keys(default_config):
    legacy_keys = {
        "template_parser_rules",
        "template_graph_mappings",
        "supplemental_graph_policy",
        "evidence_matching_strategy",
    }
    assert legacy_keys.isdisjoint(default_config.keys())
```

```python
def test_legacy_mapping_config_is_structured_failure(tmp_path):
    from storygraph_lib.config import validate_config_contract

    config = {"template_graph_mappings": {"default_mapping": {"graph_node_mapping": ["x"]}}}
    result = validate_config_contract(config)

    assert result.ok is False
    assert "legacy_semantic_config:template_graph_mappings" in result.errors
```

**实现步骤:**

- [ ] 删除旧测试中保护 `extract_template_aware_supplements` 的断言。
- [ ] 新增 legacy guard tests。
- [ ] 若当前没有 `validate_config_contract`，先写 RED 测试，后续任务实现。

**验证命令:**

```powershell
$env:PYTHONIOENCODING = "utf-8"; [Console]::OutputEncoding = [Text.Encoding]::UTF8; $OutputEncoding = [Text.Encoding]::UTF8; chcp 65001 > $null
pytest tests/test_stage1.py::test_stage1_does_not_import_template_aware_semantic_extractor tests/test_config.py::test_default_config_rejects_legacy_python_semantic_extraction_keys tests/test_templates.py::test_legacy_mapping_config_is_structured_failure -v
```

预期：改造前 FAIL，原因是 `stage1.py` 导入 `template_aware`，默认配置仍含旧键，`validate_config_contract` 不存在或未拒绝旧键。

---

### Task 2: Config Contract Rewrite

**Files:**

- Modify: `skill-src/storygraph/config/storygraph.default.json`
- Modify: `skill-src/storygraph/scripts/storygraph_lib/config.py`
- Test: `tests/test_config.py`

**RED tests:**

```python
def test_stage1_agent_driven_config_contains_lanes_review_and_writer_policy(default_config):
    assert default_config["stage1_mode"] == "agent-driven"
    assert default_config["template_requirements_strategy"]["python_validate_only"] is True
    assert default_config["canonical_graph_writer"]["semantic_generation"] == "disabled"
    assert default_config["element_lanes"]
    assert all("lane_id" in lane and "agent_role" in lane for lane in default_config["element_lanes"])
    assert default_config["review_policy"]["require_review_before_canonical_merge"] is True
```

```python
def test_writer_policy_manages_agent_driven_stage1_outputs(default_config):
    managed = set(default_config["writer_policy"]["managed_outputs"])
    assert "coverage/review-findings.json" in managed
    assert "intermediate/merge-queue.json" in managed
    assert "requirements/template-requirements.json" in managed
```

```python
def test_stage1_config_covers_graphify_adapter_and_status_enums(default_config):
    adapter = default_config["graphify_adapter"]
    assert adapter["input_strategy"] == "canonical-graph-or-graph-dir-only"
    assert adapter["failure_policy"] in adapter["allowed_failure_policies"]
    assert set(adapter["allowed_failure_policies"]) == {"degrade-visualization-and-query", "blocking"}

    enums = default_config["status_enums"]
    assert {"pending", "completed", "blocked", "failed", "needs_repair"}.issubset(enums["lane_output_statuses"])
    assert {"pending", "passed", "failed", "blocked"}.issubset(enums["reviewer_statuses"])
    assert {"open", "closed", "waived"}.issubset(enums["finding_statuses"])
    assert {"must_fix", "should_fix", "note"}.issubset(enums["finding_severities"])
    assert {"blocking", "rebuild_required", "degraded", "not_applicable"}.issubset(enums["structured_failure_statuses"])
```

**实现步骤:**

- [ ] 从默认配置删除旧键。
- [ ] 增加 `stage1_mode`、`stage1_artifacts`、`element_lanes`、`agent_orchestration`、`review_policy`、`retry_repair_policy`、`canonical_graph_writer`。
- [ ] 增加 `graphify_adapter.failure_policy`、`graphify_adapter.allowed_failure_policies`、`graphify_adapter.input_strategy`、`graphify_adapter.allowed_input_strategies`。
- [ ] 增加 `status_enums.lane_output_statuses`、`status_enums.reviewer_statuses`、`status_enums.finding_statuses`、`status_enums.finding_severities`、`status_enums.structured_failure_statuses`。
- [ ] `config.py` 增加 `validate_config_contract(config)`，拒绝 legacy semantic keys。
- [ ] 所有默认数据、状态枚举、lane、reviewer、策略参数、adapter 输入/失败策略配置化；实现逻辑只读取配置，不在函数体内重复硬编码枚举。

**验证命令:**

```powershell
$env:PYTHONIOENCODING = "utf-8"; [Console]::OutputEncoding = [Text.Encoding]::UTF8; $OutputEncoding = [Text.Encoding]::UTF8; chcp 65001 > $null
pytest tests/test_config.py -v
```

预期：PASS；legacy config 返回结构化错误而不是静默接受。

---

### Task 3: Template Discovery Only, Requirements Agent Contract

**Files:**

- Modify: `skill-src/storygraph/scripts/storygraph_lib/templates.py`
- Delete: `skill-src/storygraph/scripts/storygraph_lib/template_rules.py`
- Create: `skill-src/storygraph/scripts/storygraph_lib/template_requirements.py`
- Test: `tests/test_templates.py`
- Test: `tests/test_template_requirements_contract.py`

**RED tests:**

```python
def test_discover_templates_remains_file_inventory_only(tmp_path):
    from storygraph_lib.templates import discover_templates

    template_dir = tmp_path / "templates"
    template_dir.mkdir()
    (template_dir / "法宝分析模板.md").write_text("# 法宝分析模板\n## 字段\n- 法宝", encoding="utf-8")

    discovery = discover_templates(template_dir)

    assert discovery.templates[0].name == "法宝分析"
    assert discovery.templates[0].text.startswith("# 法宝分析模板")
```

```python
def test_template_requirements_must_come_from_agent_payload():
    from storygraph_lib.template_requirements import validate_template_requirements_payload

    payload = {
        "templates": [
            {
                "template_name": "法宝分析",
                "template_file": "法宝分析模板.md",
                "required_fields": ["法宝"],
                "required_tables": [],
                "required_cards": [],
                "required_case_patterns": [],
                "required_evidence_fields": ["原文位置"],
                "graph_node_mapping": ["artifact"],
                "graph_event_mapping": ["artifact_event"],
                "graph_relation_mapping": ["artifact_relation"],
                "coverage_rules": {"requirement_statuses": ["covered", "needs_review", "not_found_in_source"]},
            }
        ],
    }

    result = validate_template_requirements_payload(payload, expected_template_names=["法宝分析"])

    assert result.ok is True
    assert result.errors == []
```

```python
def test_template_requirements_reject_default_mapping_source():
    from storygraph_lib.template_requirements import validate_template_requirements_payload

    payload = {
        "producer": "python-template-parser",
        "templates": [{"template_name": "法宝分析", "mapping_source": "default_mapping"}],
    }

    result = validate_template_requirements_payload(payload, expected_template_names=["法宝分析"])

    assert result.ok is False
    assert "template_requirements_not_agent_produced" in result.errors
    assert "legacy_mapping_source:法宝分析:default_mapping" in result.errors
```

**实现步骤:**

- [ ] 保留 `TemplateFile`、`TemplateDiscovery`、`discover_templates()`。
- [ ] 删除 `build_requirement_matrix()` 或让其抛出结构化 legacy 错误。
- [ ] 新增 `template_requirements.py`，只做 agent payload schema validate。
- [ ] 删除 `template_rules.py`，并删除所有运行代码导入；如果某个测试仍需覆盖 legacy 行为，只能在测试内构造 payload，不得保留模块。
- [ ] 验证 `template_rules` 无运行代码引用：运行下方 `rg` 命令，预期 `$LASTEXITCODE -eq 1` 且无输出为 PASS。

**验证命令:**

```powershell
$env:PYTHONIOENCODING = "utf-8"; [Console]::OutputEncoding = [Text.Encoding]::UTF8; $OutputEncoding = [Text.Encoding]::UTF8; chcp 65001 > $null
pytest tests/test_templates.py tests/test_template_requirements_contract.py -v
$matches = rg -n "template_rules|parse_template_requirements" skill-src tests
if ($LASTEXITCODE -eq 0) { $matches; throw "legacy template_rules reference still exists" }
if ($LASTEXITCODE -ne 1) { throw "rg failed with unexpected exit code $LASTEXITCODE" }
```

预期：pytest PASS；`rg` 无输出且 exit code `1` 视为 PASS。任何 default mapping / python parser producer 都被拒绝。

---

### Task 4: Task Packet And Chunk Text Writer

**Files:**

- Create: `skill-src/storygraph/scripts/storygraph_lib/stage1_packets.py`
- Modify: `skill-src/storygraph/scripts/storygraph_lib/coverage.py`
- Modify: `skill-src/storygraph/scripts/storygraph_lib/output_writer.py`
- Test: `tests/test_stage1_task_packets.py`

**RED tests:**

```python
def test_prepare_task_packets_writes_one_packet_per_required_lane(tmp_path):
    from storygraph_lib.stage1_packets import build_task_packets

    chunks = [
        {
            "chunk_id": "chunk-0001",
            "source_range": [0, 10],
            "chapter_hint": "第一章",
            "chunk_text_path": "intermediate/chunks/chunk-0001.txt",
        }
    ]
    lanes = [
        {"lane_id": "entities_resources", "required": True, "agent_role": "实体道具资源抽取 agent", "schema": "lane-output.schema.json"},
        {"lane_id": "event_causality", "required": True, "agent_role": "事件因果抽取 agent", "schema": "lane-output.schema.json"},
    ]

    packets = build_task_packets(
        source_path="book.txt",
        chunks=chunks,
        lanes=lanes,
        template_requirements_path="requirements/template-requirements.json",
    )

    assert len(packets) == 2
    assert packets[0]["stage"] == "stage1"
    assert packets[0]["chunk_id"] == "chunk-0001"
    assert packets[0]["lane_id"] == "entities_resources"
    assert packets[0]["agent_role"] == "实体道具资源抽取 agent"
    assert packets[0]["allowed_output_schema"] == "lane-output.schema.json"
```

```python
def test_chunk_ledger_records_lane_statuses_without_semantic_completion(tmp_path):
    from storygraph_lib.coverage import make_chunk_ledger

    source = tmp_path / "novel.txt"
    source.write_text("第一章\n韩立获得小瓶。", encoding="utf-8")

    chunks = make_chunk_ledger(
        source,
        {"mode": "chapter-aware", "max_chars": 100, "overlap_chars": 0, "chapter_heading_patterns": ["^第.+章"]},
        processor="storygraph-stage1",
        target_lane_ids=["entities_resources", "event_causality"],
        required_lane_ids=["entities_resources", "event_causality"],
    )

    assert chunks[0]["extraction_status"] == "pending_agent_outputs"
    assert chunks[0]["target_lane_ids"] == ["entities_resources", "event_causality"]
    assert chunks[0]["required_lane_ids"] == ["entities_resources", "event_causality"]
    assert chunks[0]["lane_statuses"] == {}
```

```python
def test_output_writer_accepts_configured_stage1_managed_paths(tmp_path):
    from storygraph_lib.output_writer import validate_managed_output_path

    managed_outputs = [
        "intermediate/task-packets/chunk-0001/entities_resources.json",
        "intermediate/lane-outputs/chunk-0001/entities_resources/run-001.json",
        "intermediate/reviewed-bundles/chunk-0001.json",
    ]

    for rel_path in managed_outputs:
        result = validate_managed_output_path(
            graph_dir=tmp_path / "mini_novel.storygraph",
            relative_path=rel_path,
            managed_outputs=managed_outputs,
        )
        assert result.ok is True
```

**实现步骤:**

- [ ] `make_chunk_ledger()` 增加 `target_lane_ids`、`required_lane_ids` 参数。
- [ ] chunk ledger 不再把 semantic 状态写成 completed。
- [ ] 新增 `build_task_packets()`。
- [ ] task packet 路径、schema、lane role 全部来自配置。
- [ ] `output_writer.py` 必须支持从 `writer_policy.managed_outputs` 和 stage1 artifact glob/前缀配置校验动态 task packet、lane output、reviewed bundle 路径；不得把 `chunk-0001` 或 lane id 写死。

**验证命令:**

```powershell
$env:PYTHONIOENCODING = "utf-8"; [Console]::OutputEncoding = [Text.Encoding]::UTF8; $OutputEncoding = [Text.Encoding]::UTF8; chcp 65001 > $null
pytest tests/test_stage1_task_packets.py -v
```

预期：PASS；task packets 不包含 Python 生成的 nodes/edges/events/evidence。

---

### Task 5: Agent Ledger Rewrite

**Files:**

- Modify: `skill-src/storygraph/scripts/storygraph_lib/agent_ledger.py`
- Test: `tests/test_agent_ledger.py`

**RED tests:**

```python
def test_make_lane_agent_record_requires_task_packet_and_output_path():
    from storygraph_lib.agent_ledger import make_lane_agent_record

    record = make_lane_agent_record(
        run_id="run-001",
        chunk_id="chunk-0001",
        lane_id="entities_resources",
        agent_role="实体道具资源抽取 agent",
        task_packet_path="intermediate/task-packets/chunk-0001/entities_resources.json",
        output_path="intermediate/lane-outputs/chunk-0001/entities_resources/run-001.json",
        attempt=1,
    )

    assert record["stage"] == "stage1"
    assert record["chunk_id"] == "chunk-0001"
    assert record["lane_id"] == "entities_resources"
    assert record["prompt_or_input_packet"].endswith("entities_resources.json")
    assert record["status"] == "pending"
    assert record["attempt"] == 1
```

```python
def test_repair_agent_must_be_new_run_for_finding():
    from storygraph_lib.agent_ledger import validate_repair_attempts

    finding = {"finding_id": "finding-001", "repair_required": True, "status": "open"}
    bad_records = [
        {"run_id": "run-001", "lane_id": "entities_resources", "repair_of": None},
        {"run_id": "run-001", "lane_id": "entities_resources", "repair_of": "finding-001"},
    ]

    result = validate_repair_attempts([finding], bad_records)

    assert result.ok is False
    assert "repair_agent_not_fresh:finding-001" in result.errors
```

**实现步骤:**

- [ ] 保留 `validate_single_writer()`。
- [ ] 新增 lane/template/review/repair record factory。
- [ ] `make_stage_agent_records()` 删除或仅用于 migration tests，不得用于 Stage 1 success。
- [ ] ledger records 必须包含 `run_id`、`chunk_id`、`lane_id`、`agent_role`、`prompt_or_input_packet`、`input_paths`、`output_paths`、`write_scope`、`status`、`errors`、`reviewer_status`、`repair_of`、`attempt`、`started_at`、`ended_at`。

**验证命令:**

```powershell
$env:PYTHONIOENCODING = "utf-8"; [Console]::OutputEncoding = [Text.Encoding]::UTF8; $OutputEncoding = [Text.Encoding]::UTF8; chcp 65001 > $null
pytest tests/test_agent_ledger.py -v
```

预期：PASS；旧阶段级伪记录不再被 Stage 1 成功路径使用。

---

### Task 6: Lane Output Schema And Ingestion

**Files:**

- Create: `skill-src/storygraph/scripts/storygraph_lib/lane_outputs.py`
- Test: `tests/test_lane_outputs.py`

**RED tests:**

```python
def test_validate_lane_output_accepts_agent_produced_json():
    from storygraph_lib.lane_outputs import validate_lane_output

    output = {
        "run_id": "run-001",
        "task_packet_id": "stage1:chunk-0001:entities_resources",
        "chunk_id": "chunk-0001",
        "lane_id": "entities_resources",
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
        "output_status": "completed",
        "produced_at": "2026-06-20T00:00:00Z",
    }

    result = validate_lane_output(output, allowed_lane_ids=["entities_resources"])

    assert result.ok is True
    assert result.errors == []
```

```python
def test_validate_lane_output_rejects_python_producer_and_bad_lane():
    from storygraph_lib.lane_outputs import validate_lane_output

    output = {
        "run_id": "run-001",
        "chunk_id": "chunk-0001",
        "lane_id": "python_template_aware",
        "agent_role": "python",
        "model_or_agent_identity": "python-template-aware",
        "output_status": "completed",
    }

    result = validate_lane_output(output, allowed_lane_ids=["entities_resources"])

    assert result.ok is False
    assert "lane_not_configured:python_template_aware" in result.errors
    assert "semantic_output_not_agent_produced" in result.errors
```

**实现步骤:**

- [ ] 实现 lane output schema validator。
- [ ] 校验证据 source_range 必须落在 chunk source_range 内。
- [ ] 校验 status 枚举来自配置。
- [ ] structured failure 允许替代 required lane success，但必须包含 code、message、attempt。

**验证命令:**

```powershell
$env:PYTHONIOENCODING = "utf-8"; [Console]::OutputEncoding = [Text.Encoding]::UTF8; $OutputEncoding = [Text.Encoding]::UTF8; chcp 65001 > $null
pytest tests/test_lane_outputs.py -v
```

预期：PASS；Python semantic producer 被拒绝。

---

### Task 7: Review Findings And Review-Before-Merge

**Files:**

- Create: `skill-src/storygraph/scripts/storygraph_lib/review_findings.py`
- Create or modify: `skill-src/storygraph/scripts/storygraph_lib/chunk_bundles.py`
- Test: `tests/test_review_findings.py`
- Test: `tests/test_chunk_bundles.py`

**RED tests:**

```python
def test_open_required_review_finding_blocks_chunk_bundle_merge():
    from storygraph_lib.chunk_bundles import make_chunk_bundle, validate_bundle_ready_for_merge

    bundle = make_chunk_bundle(
        chunk_id="chunk-0001",
        source_range=[0, 20],
        lane_outputs=[{"chunk_id": "chunk-0001", "lane_id": "entities_resources", "output_status": "completed"}],
        review_findings=[{"finding_id": "finding-001", "severity": "must_fix", "status": "open"}],
    )

    result = validate_bundle_ready_for_merge(bundle, require_review_before_merge=True)

    assert result.ok is False
    assert "open_must_fix_finding:finding-001" in result.errors
```

```python
def test_closed_finding_with_fresh_repair_allows_bundle_merge():
    from storygraph_lib.chunk_bundles import make_chunk_bundle, validate_bundle_ready_for_merge

    bundle = make_chunk_bundle(
        chunk_id="chunk-0001",
        source_range=[0, 20],
        lane_outputs=[{"chunk_id": "chunk-0001", "lane_id": "entities_resources", "output_status": "completed"}],
        review_findings=[
            {
                "finding_id": "finding-001",
                "severity": "must_fix",
                "status": "closed",
                "repair_agent_run_id": "run-002",
                "repair_of": "run-001",
            }
        ],
    )

    result = validate_bundle_ready_for_merge(bundle, require_review_before_merge=True)

    assert result.ok is True
```

**实现步骤:**

- [ ] review finding schema 包含 reviewer_role、stage、chunk_id、lane_id、probe_or_sample、actual_output、expected_output、severity、status、repair_required、repair_agent_run_id。
- [ ] chunk bundle 只能包含同 chunk 的 lane outputs。
- [ ] required lane 缺失时，必须有 structured failure 或 open finding，不能默默通过。
- [ ] review-before-merge 策略读取 `review_policy.require_review_before_canonical_merge`。

**验证命令:**

```powershell
$env:PYTHONIOENCODING = "utf-8"; [Console]::OutputEncoding = [Text.Encoding]::UTF8; $OutputEncoding = [Text.Encoding]::UTF8; chcp 65001 > $null
pytest tests/test_review_findings.py tests/test_chunk_bundles.py -v
```

预期：PASS。

---

### Task 8: Canonical Graph Writer From Reviewed Agent Outputs

**Files:**

- Modify: `skill-src/storygraph/scripts/storygraph_lib/graph_schema.py`
- Create: `skill-src/storygraph/scripts/storygraph_lib/canonical_writer.py`
- Test: `tests/test_canonical_writer.py`
- Modify: `tests/test_graph_schema.py`

**RED tests:**

```python
def test_canonical_writer_rejects_unreviewed_lane_outputs():
    from storygraph_lib.canonical_writer import build_canonical_graph_from_bundles

    bundle = {
        "chunk_id": "chunk-0001",
        "ready_for_merge": False,
        "reviewer_status": "pending",
        "normalized_nodes": [],
        "normalized_edges": [],
        "normalized_events": [],
        "normalized_evidence": [],
    }

    result = build_canonical_graph_from_bundles([bundle], novel_name="book", status_enums={})

    assert result.ok is False
    assert "bundle_not_reviewed:chunk-0001" in result.errors
```

```python
def test_canonical_writer_preserves_agent_output_provenance():
    from storygraph_lib.canonical_writer import build_canonical_graph_from_bundles

    bundle = {
        "chunk_id": "chunk-0001",
        "ready_for_merge": True,
        "reviewer_status": "passed",
        "lane_output_paths": ["intermediate/lane-outputs/chunk-0001/entities_resources/run-001.json"],
        "normalized_nodes": [
            {
                "id": "node:artifact:x",
                "label": "小瓶",
                "node_type": "artifact",
                "evidence_ids": ["evidence:1"],
                "source_locator": "tests/fixtures/mini_novel.txt#char=3-5",
                "supports_templates": [{"template_name": "法宝分析", "requirement_id": "r1", "status": "covered"}],
                "confidence": "EXTRACTED",
                "verification_status": "verified",
            }
        ],
        "normalized_edges": [],
        "normalized_events": [],
        "normalized_evidence": [
            {
                "evidence_id": "evidence:1",
                "source_range": [3, 5],
                "source_locator": "tests/fixtures/mini_novel.txt#char=3-5",
                "chunk_id": "chunk-0001",
                "fact_summary": "韩立获得小瓶",
                "supports_templates": [{"template_name": "法宝分析", "requirement_id": "r1", "status": "covered"}],
                "confidence": "EXTRACTED",
                "verification_status": "verified",
            }
        ],
    }

    result = build_canonical_graph_from_bundles([bundle], novel_name="book", status_enums={})

    assert result.ok is True
    assert result.graph["nodes"][0]["provenance"]["lane_output_paths"]
    assert result.graph["metadata"]["semantic_generation"] == "agent-produced"
```

**实现步骤:**

- [ ] 新增 canonical writer，只接受 reviewed bundles。
- [ ] 合并时做稳定 ID/去重/冲突保留，但不得从 template requirement 自动生成语义 item。
- [ ] 删除 `merge_template_supplements`；用新的 reviewed bundle canonical writer 取代旧 supplement 合并入口。
- [ ] graph metadata 记录 `semantic_generation: agent-produced`、`canonical_writer_version`、`source_bundle_paths`。

**验证命令:**

```powershell
$env:PYTHONIOENCODING = "utf-8"; [Console]::OutputEncoding = [Text.Encoding]::UTF8; $OutputEncoding = [Text.Encoding]::UTF8; chcp 65001 > $null
pytest tests/test_canonical_writer.py tests/test_graph_schema.py -v
```

预期：PASS。

---

### Task 9: Stage 1 Prepare/Ingest/Merge Orchestrator

**Files:**

- Modify: `skill-src/storygraph/scripts/storygraph_lib/stage1.py`
- Modify: `skill-src/storygraph/scripts/storygraph_lib/cli.py`
- Modify: `skill-src/storygraph/scripts/storygraph_lib/state.py`
- Create or modify: `tests/conftest.py`
- Test: `tests/test_stage1.py`
- Test: `tests/test_stage1_idempotency.py`

**Task 9A RED tests: `prepare_stage1()` 只写 task packets、chunk ledger、pending ledger，不写 canonical graph**

```python
def test_prepare_stage1_writes_task_packets_but_no_canonical_graph(novel, template_dir, graph_dir, config):
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
```

**Task 9A 实现步骤:**

- [ ] `prepare_stage1(source_path, template_dir, graph_dir, config)` 解析路径、写 manifest、扫描模板 inventory、写 chunk text。
- [ ] 根据 `config["element_lanes"]` 写 task packets。
- [ ] 写 chunk ledger 和 pending agent-run-ledger；pending ledger 不得伪造 completed agent run。
- [ ] 不调用 canonical writer，不调用 graphify adapter，不写 `graphify-out/graph.json`。

**Task 9B RED tests: `ingest_stage1()` 读取 agent/template/lane/review artifacts，生成 reviewed chunk bundles**

```python
def test_ingest_stage1_requires_agent_template_requirements_before_lane_merge(graph_dir, config):
    from storygraph_lib.stage1 import ingest_stage1

    result = ingest_stage1(graph_dir=graph_dir, config=config)

    assert result["status"] == "failed"
    assert result["error"]["code"] == "template_requirements_missing"
```

```python
def test_ingest_stage1_writes_reviewed_chunk_bundle_from_reviewed_agent_artifacts(
    graph_dir,
    config,
    write_agent_template_requirements,
    write_lane_output,
    write_review_finding,
):
    from storygraph_lib.stage1 import ingest_stage1

    write_agent_template_requirements(graph_dir)
    write_lane_output(graph_dir, chunk_id="chunk-0001", lane_id="entities_resources", status="completed")
    write_review_finding(graph_dir, status="passed")

    result = ingest_stage1(graph_dir=graph_dir, config=config)

    assert result["status"] == "ingested"
    assert (graph_dir / "intermediate" / "reviewed-bundles" / "chunk-0001.json").exists()
    assert (graph_dir / "intermediate" / "merge-queue.json").exists()
```

**Task 9B 实现步骤:**

- [ ] `ingest_stage1(graph_dir, config)` 读取 `requirements/template-requirements.json`、lane outputs、review findings。
- [ ] 校验 agent 产物来源、lane id、状态枚举、source range、source locator、review finding 状态；template requirements 最终汇总文件不校验固定 producer。
- [ ] 只有 review passed/closed 且 required lane 已满足或有合格 structured failure 的 chunk 才生成 reviewed bundle。
- [ ] 写 reviewed chunk bundles 和 merge queue；不写 canonical graph。

**Task 9C RED tests: `merge_stage1()` 只读 reviewed bundles，调用 canonical writer**

```python
def test_merge_stage1_fails_when_required_lane_output_missing(graph_dir, config):
    from storygraph_lib.stage1 import merge_stage1

    result = merge_stage1(graph_dir=graph_dir, config=config)

    assert result["status"] == "failed"
    assert "required_lane_missing" in result["validation_errors"]
```

```python
def test_stage1_merge_success_uses_reviewed_agent_outputs(
    novel,
    template_dir,
    graph_dir,
    config,
    write_agent_template_requirements,
    write_lane_output,
    write_review_finding,
):
    import json

    from storygraph_lib.stage1 import prepare_stage1, ingest_stage1, merge_stage1

    prepare_stage1(source_path=novel, template_dir=template_dir, graph_dir=graph_dir, config=config)
    write_agent_template_requirements(graph_dir)
    write_lane_output(graph_dir, chunk_id="chunk-0001", lane_id="entities_resources", status="completed")
    write_review_finding(graph_dir, status="passed")

    ingest = ingest_stage1(graph_dir=graph_dir, config=config)
    merge = merge_stage1(graph_dir=graph_dir, config=config)

    assert ingest["status"] == "ingested"
    assert merge["status"] == "success"
    graph = json.loads((graph_dir / "graphify-out" / "graph.json").read_text(encoding="utf-8"))
    assert graph["metadata"]["semantic_generation"] == "agent-produced"
```

**Task 9C 实现步骤:**

- [ ] 删除 `extract_template_aware_supplements()` 调用。
- [ ] `merge_stage1(graph_dir, config)` 只读取 reviewed bundles/merge queue。
- [ ] `merge_stage1()` 调用 canonical writer；缺少 reviewed bundle 时返回 `missing_reviewed_agent_outputs` 或 `required_lane_missing`，不得尝试 source substring 或 graphify base graph。
- [ ] canonical graph metadata 写 `semantic_generation: agent-produced` 和 `source_bundle_paths`。
- [ ] 现有 graphify 错误处理改为 adapter phase，不影响 semantic provenance。

**Task 9D RED tests: idempotency / CLI compatibility**

```python
def test_build_stage1_cli_returns_pending_when_agent_outputs_missing(capsys, novel, template_dir, graph_dir):
    import json

    from storygraph_lib.cli import main

    code = main([
        "build-stage1",
        "--source",
        str(novel),
        "--template-dir",
        str(template_dir),
        "--graph-dir",
        str(graph_dir),
    ])

    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["status"] in {"prepared", "pending_agent_outputs"}
    assert payload["next_action"] == "run_agent_task_packets"
    assert not (graph_dir / "graphify-out" / "graph.json").exists()
```

```python
def test_stage1_idempotency_hash_includes_reviewed_output_manifest():
    from storygraph_lib.state import compute_stage1_input_hash

    base = compute_stage1_input_hash(
        source_hash="source-a",
        config_hash="config-a",
        template_inventory_hash="templates-a",
        task_packet_schema_hash="packet-schema-a",
        requirements_hash="requirements-a",
        reviewed_output_manifest_hash="reviewed-a",
    )
    changed = compute_stage1_input_hash(
        source_hash="source-a",
        config_hash="config-a",
        template_inventory_hash="templates-a",
        task_packet_schema_hash="packet-schema-a",
        requirements_hash="requirements-a",
        reviewed_output_manifest_hash="reviewed-b",
    )

    assert base != changed
```

**Task 9D 实现步骤:**

- [ ] 拆分 `build_stage1_graph()` 内部流程为 `prepare_stage1()`、`ingest_stage1()`、`merge_stage1()`；CLI 可保留 `build-stage1`，但缺少 agent outputs 时只能返回 prepared/pending，不得返回 success。
- [ ] `prepare-stage1`、`ingest-stage1`、`merge-stage1` CLI 均返回结构化 JSON。
- [ ] 幂等 hash 包含 source hash、config hash、template inventory、task packet schema、requirements hash、reviewed output manifest。

**验证命令:**

```powershell
$env:PYTHONIOENCODING = "utf-8"; [Console]::OutputEncoding = [Text.Encoding]::UTF8; $OutputEncoding = [Text.Encoding]::UTF8; chcp 65001 > $null
pytest tests/test_stage1.py tests/test_stage1_idempotency.py -v
```

预期：PASS。

---

### Task 10: Validation And CLI Boundary Inventory

**Files:**

- Modify: `skill-src/storygraph/scripts/storygraph_lib/validation.py`
- Modify: `skill-src/storygraph/scripts/storygraph_lib/cli.py`
- Test: `tests/test_validation_cli.py`

**Task 10A: Boundary Inventory 可执行清单**

所有入口先标注为 `needs_fix`；当对应 RED test 变绿后，执行者在实现 PR 描述中标注为 `covered`。只有受控内部写入后立即读取、且没有用户/旧缓存/外部进程可注入路径的入口可标 `not_applicable`，并必须写明理由。

| 边界入口 | 覆盖状态 | 读取/解析模块 | 必测坏输入 | 期望结构化错误码或行为 | 对应测试文件和测试名 |
| --- | --- | --- | --- | --- | --- |
| 配置 JSON | needs_fix -> covered | `config.py::load_config_file`、`config.py::validate_config_contract` | `bad_json`、`bad_utf8`、`json_shape_not_object`、`deep_json_recursion_or_too_deep`、`missing_required_field`、`field_type_error` | `config_json_invalid`、`config_utf8_decode_error`、`config_shape_not_object`、`config_too_deep`、`config_missing_required_field`、`config_field_type_error`；CLI 返回 JSON failure | `tests/test_config.py::test_config_boundary_bad_inputs_are_structured_failures` |
| local override | needs_fix -> covered | `config.py::load_local_override`、`config.py::merge_config` | `bad_json`、`bad_utf8`、`json_shape_not_object`、`field_type_error`、legacy key | `local_override_invalid`、`local_override_utf8_decode_error`、`local_override_shape_not_object`、`local_override_field_type_error`、`legacy_semantic_config:<key>` | `tests/test_config.py::test_local_override_boundary_errors_do_not_leak_parser_exceptions` |
| 小说源文件 | needs_fix -> covered | `paths.py`、`coverage.py::make_chunk_ledger` | `bad_utf8`、超大/空文件、Windows 路径语义、embedded NUL、绝对路径越权、`..` 越界 | `source_utf8_decode_error`、`source_empty`、`path_embedded_nul`、`path_absolute_rejected`、`path_parent_traversal_rejected`；CLI blocking failure | `tests/test_validation_cli.py::test_source_file_boundary_errors_are_structured` |
| 模板文件 | needs_fix -> covered | `templates.py::discover_templates`、`template_requirements.py` | `bad_utf8`、README missing、嵌入 NUL 文件名、`..` 越界、模板需求缺字段/类型错 | `template_utf8_decode_error`、`template_readme_missing_warning`、`path_embedded_nul`、`path_parent_traversal_rejected`、`template_requirements_missing_required_field`、`template_requirements_field_type_error` | `tests/test_templates.py::test_template_file_boundary_errors_are_structured` |
| README | needs_fix -> covered | `templates.py::discover_templates`、`validation.py` | missing README、bad UTF-8、json_shape_not_object 不适用 | README missing 只 degraded warning：`template_readme_missing_warning`；bad UTF-8 为 `readme_utf8_decode_error` | `tests/test_templates.py::test_readme_boundary_warning_and_decode_error` |
| graphify artifacts | needs_fix -> covered | `graphify_adapter.py`、`validation.py` | `bad_json`、`bad_utf8`、`json_shape_not_object`、missing graph fields、corrupt artifact | `graphify_artifact_invalid_json`、`graphify_artifact_utf8_decode_error`、`graphify_artifact_shape_not_object`、`graphify_artifact_missing_required_field`；按 failure policy blocking/degraded | `tests/test_graphify_adapter.py::test_graphify_artifact_boundary_errors_follow_failure_policy` |
| 旧 manifest | needs_fix -> covered | `manifest.py`、`state.py`、`validation.py` | `bad_json`、`bad_utf8`、`json_shape_not_object`、missing schema version、legacy semantic metadata、corrupt legacy cache | `manifest_invalid_json`、`manifest_utf8_decode_error`、`manifest_shape_not_object`、`manifest_missing_required_field`、`legacy_manifest_requires_rebuild`、`corrupt_legacy_cache_rebuild_required` | `tests/test_validation_cli.py::test_corrupt_legacy_manifest_returns_rebuild_or_structured_failure` |
| 旧 agent ledger | needs_fix -> covered | `agent_ledger.py`、`validation.py` | `bad_json`、`bad_utf8`、`json_shape_not_object`、旧 stage-level fake completed records、缺 run_id/路径 | `agent_ledger_invalid_json`、`agent_ledger_utf8_decode_error`、`agent_ledger_shape_not_object`、`legacy_agent_ledger_requires_rebuild`、`agent_ledger_missing_required_field` | `tests/test_agent_ledger.py::test_legacy_agent_ledger_boundary_errors_return_rebuild` |
| coverage/readiness JSON | needs_fix -> covered | `coverage.py`、`validation.py` | `bad_json`、`bad_utf8`、`json_shape_not_object`、missing required field、field type error、corrupt legacy cache | `coverage_invalid_json`、`coverage_utf8_decode_error`、`coverage_shape_not_object`、`coverage_missing_required_field`、`coverage_field_type_error`、`corrupt_legacy_cache_rebuild_required` | `tests/test_validation_cli.py::test_coverage_and_readiness_boundary_errors_are_structured` |
| sub-agent JSON payload | needs_fix -> covered | `lane_outputs.py`、`template_requirements.py`、`review_findings.py` | `bad_json`、`bad_utf8`、`json_shape_not_object`、missing required field、field type error、deep JSON | `subagent_payload_invalid_json`、`subagent_payload_utf8_decode_error`、`subagent_payload_shape_not_object`、`subagent_payload_missing_required_field`、`subagent_payload_field_type_error`、`subagent_payload_too_deep` | `tests/test_lane_outputs.py::test_subagent_payload_boundary_errors_are_structured` |
| subprocess stdout/stderr | needs_fix -> covered | `graphify_adapter.py::run_graphify_adapter` | subprocess output decode error、non-JSON stdout、oversized stderr | `subprocess_output_decode_error`、`subprocess_stdout_not_json`、`subprocess_stderr_too_large`；按 adapter policy blocking/degraded | `tests/test_graphify_adapter.py::test_subprocess_output_decode_error_is_structured` |
| 路径字符串 | needs_fix -> covered | `paths.py`、`output_writer.py`、`cli.py` | Windows 路径语义、embedded NUL、absolute path rejected where needed、parent traversal rejected | `path_windows_semantics_normalized`、`path_embedded_nul`、`path_absolute_rejected`、`path_parent_traversal_rejected` | `tests/test_validation_cli.py::test_path_string_boundary_errors_are_structured` |
| output writer | needs_fix -> covered | `output_writer.py` | unmanaged path、absolute path、`..` 越界、embedded NUL、Windows drive path | `writer_unmanaged_output`、`writer_absolute_path_rejected`、`writer_parent_traversal_rejected`、`writer_embedded_nul`、`writer_windows_drive_rejected` | `tests/test_validation_cli.py::test_output_writer_boundary_errors_are_structured` |

**RED tests:**

`tests/test_validation_cli.py` 文件顶部需要：

```python
import json

import pytest
```

```python
def test_validate_graph_dir_requires_agent_driven_artifacts(tmp_path, make_minimal_graph_dir_without_agent_outputs):
    from storygraph_lib.validation import validate_graph_dir

    graph_dir = make_minimal_graph_dir_without_agent_outputs(tmp_path)

    result = validate_graph_dir(graph_dir)

    assert result.ok is False
    assert "missing_agent_run_ledger" in result.errors or "missing_lane_outputs" in result.errors
    assert "canonical_graph_without_agent_provenance" in result.errors
```

```python
def test_validate_graph_dir_rejects_legacy_python_semantic_metadata(graph_dir, write_graph):
    from storygraph_lib.validation import validate_graph_dir

    graph = {
        "nodes": [],
        "edges": [],
        "hyperedges": [],
        "events": [],
        "evidence_index": [],
        "metadata": {"evidence_matching_strategy": "substring"},
    }
    write_graph(graph_dir, graph)

    result = validate_graph_dir(graph_dir)

    assert result.ok is False
    assert "legacy_semantic_metadata:substring" in result.errors
```

```python
def test_cli_prepare_stage1_outputs_json_and_pending_agent_tasks(capsys, tmp_path):
    from storygraph_lib.cli import main

    code = main(["prepare-stage1", "--source", str(novel), "--template-dir", str(template_dir)])

    payload = json.loads(capsys.readouterr().out)
    assert code == 0
    assert payload["status"] == "prepared"
    assert payload["next_action"] == "run_agent_task_packets"
```

```python
@pytest.mark.parametrize(
    ("scenario", "raw_bytes", "expected_code"),
    [
        ("bad_json", b"{not-json", "external_json_invalid"),
        ("bad_utf8", b"\xff\xfe\x00", "external_json_utf8_decode_error"),
        ("json_shape_not_object", b"[1, 2, 3]", "external_json_shape_not_object"),
        ("missing_required_field", b"{}", "external_json_missing_required_field:version"),
        ("field_type_error", b"{\"version\": 1}", "external_json_field_type_error:version"),
    ],
)
def test_external_json_boundary_bad_inputs_are_structured_failures(tmp_path, scenario, raw_bytes, expected_code):
    from storygraph_lib.validation import validate_external_json_artifact

    path = tmp_path / f"{scenario}.json"
    path.write_bytes(raw_bytes)

    result = validate_external_json_artifact(
        path,
        artifact_name="config",
        required_fields={"version": str},
        max_depth=32,
    )

    assert result.ok is False
    assert expected_code in result.errors
```

```python
def test_deep_json_recursion_or_too_deep_is_structured_failure(tmp_path):
    from storygraph_lib.validation import validate_external_json_artifact

    payload = current = {}
    for index in range(80):
        current["child"] = {}
        current = current["child"]
    path = tmp_path / "deep.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    result = validate_external_json_artifact(path, artifact_name="subagent_payload", max_depth=32)

    assert result.ok is False
    assert "subagent_payload_too_deep" in result.errors
```

```python
@pytest.mark.parametrize(
    ("scenario", "raw_path", "expected_code"),
    [
        ("windows_path_semantics", r"C:\tmp\outside.json", "path_absolute_rejected"),
        ("embedded_nul", "chunk-0001\x00.json", "path_embedded_nul"),
        ("absolute_path_rejected_where_needed", "/tmp/outside.json", "path_absolute_rejected"),
        ("parent_traversal_rejected", "../outside.json", "path_parent_traversal_rejected"),
    ],
)
def test_path_string_boundary_errors_are_structured(tmp_path, scenario, raw_path, expected_code):
    from storygraph_lib.paths import validate_relative_artifact_path

    result = validate_relative_artifact_path(raw_path, base_dir=tmp_path / "mini_novel.storygraph")

    assert result.ok is False
    assert expected_code in result.errors
```

```python
def test_subprocess_output_decode_error_is_structured():
    from storygraph_lib.graphify_adapter import decode_graphify_output

    result = decode_graphify_output(stdout=b"\xff\xfe", stderr=b"", failure_policy="degrade-visualization-and-query")

    assert result.ok is False
    assert "subprocess_output_decode_error" in result.errors
    assert result.status == "degraded"
```

```python
def test_corrupt_legacy_cache_returns_rebuild_or_structured_failure(tmp_path):
    from storygraph_lib.validation import validate_graph_dir

    graph_dir = tmp_path / "mini_novel.storygraph"
    (graph_dir / "coverage").mkdir(parents=True)
    (graph_dir / "coverage" / "template-readiness.json").write_bytes(b"{bad-json")

    result = validate_graph_dir(graph_dir)

    assert result.ok is False
    assert (
        "corrupt_legacy_cache_rebuild_required" in result.errors
        or "coverage_invalid_json" in result.errors
    )
```

**实现步骤:**

- [ ] `validate_graph_dir()` 增加 task packet、lane output、review findings、agent provenance 校验。
- [ ] CLI 增加或调整 `prepare-stage1`、`ingest-stage1`、`merge-stage1`。
- [ ] 旧 `build-stage1` 如保留，应变成 orchestration helper：缺少 agent outputs 时返回 prepared/pending，不返回 success。
- [ ] 所有 CLI 错误返回结构化 JSON。
- [ ] 新增通用外部 JSON 读取 helper，捕获 bad JSON、bad UTF-8、非 object shape、过深 JSON、缺字段、类型错误；不得向 CLI 泄漏原始 `JSONDecodeError`、`UnicodeDecodeError`、`RecursionError`。
- [ ] 新增路径边界 helper，统一处理 Windows drive/UNC 语义、embedded NUL、absolute path、parent traversal。
- [ ] graphify subprocess stdout/stderr 解码必须走结构化结果；adapter policy 为 `degrade-visualization-and-query` 时返回 degraded warning，为 `blocking` 时返回 blocking failure。
- [ ] 旧 manifest、旧 agent ledger、coverage/readiness cache 解析失败时返回 rebuild 判定或结构化 failure，不允许未捕获解析异常中断 CLI。

**验证命令:**

```powershell
$env:PYTHONIOENCODING = "utf-8"; [Console]::OutputEncoding = [Text.Encoding]::UTF8; $OutputEncoding = [Text.Encoding]::UTF8; chcp 65001 > $null
pytest tests/test_validation_cli.py -v
```

预期：PASS。

---

### Task 11: Graphify Adapter Decoupling

**Files:**

- Modify: `skill-src/storygraph/scripts/storygraph_lib/graphify_adapter.py`
- Modify: `skill-src/storygraph/scripts/storygraph_lib/stage1.py`
- Test: `tests/test_graphify_adapter.py`
- Test: `tests/test_stage1.py`

**RED tests:**

```python
def test_graphify_adapter_does_not_produce_semantic_success_without_agent_outputs(
    graph_dir_without_agent_outputs,
    config_with_graphify_success,
):
    from storygraph_lib.stage1 import merge_stage1

    result = merge_stage1(graph_dir=graph_dir_without_agent_outputs, config=config_with_graphify_success)

    assert result["status"] == "failed"
    assert "missing_reviewed_agent_outputs" in result["validation_errors"]
```

```python
def test_graphify_failure_degrades_visualization_when_policy_allows(graph_dir_with_reviewed_outputs, config):
    from storygraph_lib.stage1 import merge_stage1

    config["graphify_adapter"]["failure_policy"] = "degrade-visualization-and-query"
    result = merge_stage1(graph_dir=graph_dir_with_reviewed_outputs, config=config)

    assert result["status"] in {"success", "warning"}
    assert "graphify_degraded" in result["warnings"]
```

```python
def test_config_rejects_legacy_canonical_graph_policy_merge_template_aware_supplements():
    from storygraph_lib.config import validate_config_contract

    result = validate_config_contract(
        {"canonical_graph_policy": "merge-template-aware-supplements"}
    )

    assert result.ok is False
    assert "legacy_semantic_config:canonical_graph_policy:merge-template-aware-supplements" in result.errors
```

```python
def test_graphify_adapter_rejects_source_as_semantic_input(novel, config):
    from storygraph_lib.graphify_adapter import build_graphify_command

    config["graphify_adapter"]["input_strategy"] = "canonical-graph-or-graph-dir-only"

    result = build_graphify_command(source_path=novel, canonical_graph_path=None, graph_dir=None, config=config)

    assert result.ok is False
    assert "graphify_source_input_rejected" in result.errors
```

```python
def test_stage1_success_path_ignores_source_as_graphify_semantic_base(
    novel,
    template_dir,
    graph_dir_with_reviewed_outputs,
    config_with_graphify_success,
):
    import json

    from storygraph_lib.stage1 import merge_stage1

    merge = merge_stage1(graph_dir=graph_dir_with_reviewed_outputs, config=config_with_graphify_success)

    assert merge["status"] in {"success", "warning"}
    graph = json.loads(
        (graph_dir_with_reviewed_outputs / "graphify-out" / "graph.json").read_text(encoding="utf-8")
    )
    assert graph["metadata"]["semantic_generation"] == "agent-produced"
    assert graph["metadata"]["graphify_input_strategy"] == "canonical-graph-or-graph-dir-only"
    assert "source_semantic_base_graph" not in graph["metadata"]
```

**实现步骤:**

- [ ] graphify adapter 输入改为 canonical graph path 或 graph dir，不再从 source 生成 semantic base graph。
- [ ] adapter failure policy 从配置读取：`degrade-visualization-and-query` 或 `blocking`。
- [ ] `validate_config_contract()` 拒绝旧 `canonical_graph_policy: merge-template-aware-supplements`。
- [ ] `build_graphify_command()` 或等价 adapter 入口拒绝只有 `source_path`、没有 canonical graph/graph dir 的语义输入。
- [ ] blocking 只阻塞 adapter 阶段，不允许 fallback 到 Python semantic extraction。
- [ ] ledger 记录 graphify adapter run，但 agent semantic provenance 仍指向 lane outputs。

**验证命令:**

```powershell
$env:PYTHONIOENCODING = "utf-8"; [Console]::OutputEncoding = [Text.Encoding]::UTF8; $OutputEncoding = [Text.Encoding]::UTF8; chcp 65001 > $null
pytest tests/test_graphify_adapter.py tests/test_config.py::test_config_rejects_legacy_canonical_graph_policy_merge_template_aware_supplements tests/test_stage1.py::test_graphify_adapter_does_not_produce_semantic_success_without_agent_outputs tests/test_stage1.py::test_graphify_failure_degrades_visualization_when_policy_allows tests/test_stage1.py::test_stage1_success_path_ignores_source_as_graphify_semantic_base -v
```

预期：PASS；旧 `merge-template-aware-supplements` 被拒绝，adapter 只能读取 canonical graph 或 graph dir，不再把 `{source}` 当 semantic base graph。

---

### Task 12: Documentation And Skill Workflow Update

**Files:**

- Modify: `skill-src/storygraph/SKILL.md`
- Modify: `skill-src/storygraph/references/workflow.md`
- Modify: `skill-src/storygraph/references/graph-schema.md`
- Modify: `docs/storygraph-cli.md`
- Test: `tests/test_skill_structure.py`

**RED tests:**

```python
def test_stage1_docs_describe_agent_driven_not_python_semantic_extraction():
    text = Path("skill-src/storygraph/references/workflow.md").read_text(encoding="utf-8")
    assert "Codex 主 agent" in text
    assert "Python 只做 deterministic tool layer" in text
    assert "substring" not in text
    assert "template_aware" not in text
```

```python
def test_cli_docs_include_prepare_ingest_merge_commands():
    text = Path("docs/storygraph-cli.md").read_text(encoding="utf-8")
    assert "prepare-stage1" in text
    assert "ingest-stage1" in text
    assert "merge-stage1" in text
```

**实现步骤:**

- [ ] 更新 workflow，明确 Stage 1 semantic producer 是 Codex agents。
- [ ] 更新 graph schema，新增 provenance 要求。
- [ ] CLI 文档写清 prepare/agent run/ingest/review/merge。
- [ ] 删除文档中的 Python 模板感知抽取、substring evidence matching、default mapping 描述。

**验证命令:**

```powershell
$env:PYTHONIOENCODING = "utf-8"; [Console]::OutputEncoding = [Text.Encoding]::UTF8; $OutputEncoding = [Text.Encoding]::UTF8; chcp 65001 > $null
pytest tests/test_skill_structure.py -v
$matches = rg -n "substring|template_aware|default_mapping|template_graph_mappings|evidence_matching_strategy" skill-src docs/storygraph-cli.md
if ($LASTEXITCODE -eq 0) { $matches; "Reviewer must confirm matches are only legacy rejection tests or migration notes." }
elseif ($LASTEXITCODE -eq 1) { "PASS: no legacy semantic path strings found in runtime docs." }
else { throw "rg failed with unexpected exit code $LASTEXITCODE" }
```

预期：pytest PASS；`rg` exit code `1` 且无输出为 PASS。若命中 legacy rejection 测试说明，需人工确认上下文是拒绝旧配置。

---

## Plan Review Gate

主 Agent 保存本计划后，应交给至少两个 reviewer agent 审查。

### Contract Reviewer

审查范围：

- 规范覆盖：是否覆盖用户要求的删除清单、保留底座、新 agent-driven Stage 1、测试处置、final review gate。
- 数据契约：task packet、lane output、review finding、repair、agent-run-ledger、chunk bundle、merge queue、canonical graph。
- 行为契约：无 reviewed agent outputs 时不得生成成功 canonical graph。
- 边界入口：配置 JSON、local override、小说源文件、模板文件、README、graphify artifacts、旧 manifest、旧 agent ledger、coverage/readiness JSON、sub-agent JSON payload、subprocess stdout/stderr、路径字符串、output writer。
- 边界入口硬性验收：reviewer 不只检查是否枚举入口；必须逐项确认每个入口在 Task 10A 表格中有读取/解析模块、坏输入测试、结构化错误码或 blocking/rebuild/degraded 行为、对应测试文件和测试名。若某入口被标为 `not_applicable`，reviewer 必须确认它是受控内部写入后立即读取，且无用户输入、旧缓存或外部进程输出可注入。

Reviewer 必须运行或要求执行的 probe：

```powershell
$env:PYTHONIOENCODING = "utf-8"; [Console]::OutputEncoding = [Text.Encoding]::UTF8; $OutputEncoding = [Text.Encoding]::UTF8; chcp 65001 > $null
$matches = rg -n "template_aware|template_rules|template_graph_mappings|default_mapping|evidence_matching_strategy|substring|extract_template_aware_supplements" skill-src tests
if ($LASTEXITCODE -eq 0) { $matches; "Reviewer must confirm every match is a legacy rejection test or migration note, not a Stage 1 success path." }
elseif ($LASTEXITCODE -eq 1) { "PASS: no legacy semantic path strings found." }
else { throw "rg failed with unexpected exit code $LASTEXITCODE" }
```

期望：exit code `1` 且无输出为 PASS；若 exit code `0`，只允许出现在 legacy rejection tests 或迁移说明中，且 reviewer 必须逐条确认不得出现在 Stage 1 success path。

### Code Quality Reviewer

审查范围：

- 结构：模块职责是否清晰，是否把读取/校验/写盘/merge 混成一个大函数。
- 架构质量：Orchestrator、Fan-out/Fan-in、Adapter、Strategy、Single-writer、Review/Repair Loop 是否落实。
- 通用架构：是否避免为当前测试小说或当前动态发现到的模板集合写一次性硬编码。
- 设计模式适配：是否只在有实际边界收益处新增模块，没有无意义过度抽象。
- 配置化覆盖范围：lane、reviewer、状态枚举、artifact path、failure policy、retry policy、writer policy 是否配置化。
- 删除质量：旧代码删除是否连带清理导入、测试 fixture、文档描述。

Reviewer 若发现问题，必须给 repair agent 完整 packet：

```json
{
  "probe_command": "pytest tests/test_stage1.py::test_name -v",
  "input_sample": {
    "config": "最小复现 config",
    "agent_output": "触发失败的 lane output/review finding",
    "graph_dir_files": ["manifest.json", "coverage/agent-run-ledger.json"]
  },
  "actual_output": "完整 stdout/stderr 或断言失败",
  "expected_output": "期望 exit code、JSON field、错误 code 或文件内容",
  "reviewer_diagnosis": "违反的契约边界或架构规则"
}
```

---

## Final Review Gate

实施完成前必须运行：

下面的 `mini_novel` final-review fixture 只用于快速 smoke/contract 检查：验证 prepare pending、缺 agent outputs 时结构化失败、写入 reviewed agent fixture 后能成功 merge。它不能作为最终验收，不能替代完整《凡人修仙传》原文和全部模板的全量验收。

```powershell
$env:PYTHONIOENCODING = "utf-8"; [Console]::OutputEncoding = [Text.Encoding]::UTF8; $OutputEncoding = [Text.Encoding]::UTF8; chcp 65001 > $null
pytest -v
```

预期：全部 PASS。

```powershell
$env:PYTHONIOENCODING = "utf-8"; [Console]::OutputEncoding = [Text.Encoding]::UTF8; $OutputEncoding = [Text.Encoding]::UTF8; chcp 65001 > $null
python skill-src/storygraph/scripts/storygraph.py validate-skill --skill-root skill-src/storygraph
```

预期：exit code `0`，无缺失 skill 文件。

```powershell
$env:PYTHONIOENCODING = "utf-8"; [Console]::OutputEncoding = [Text.Encoding]::UTF8; $OutputEncoding = [Text.Encoding]::UTF8; chcp 65001 > $null
$matches = rg -n "extract_template_aware_supplements|evidence_matching_strategy|template_graph_mappings|default_mapping|No substring evidence found|mapping_source.*template_parse_result" skill-src tests
if ($LASTEXITCODE -eq 0) { $matches; "Reviewer must confirm every match is a legacy rejection test or migration note, not a Stage 1 success path." }
elseif ($LASTEXITCODE -eq 1) { "PASS: no legacy semantic path strings found." }
else { throw "rg failed with unexpected exit code $LASTEXITCODE" }
```

预期：exit code `1` 且无输出为 PASS；如命中，只能是 legacy rejection test，并由 reviewer 确认。

```powershell
$env:PYTHONIOENCODING = "utf-8"; [Console]::OutputEncoding = [Text.Encoding]::UTF8; $OutputEncoding = [Text.Encoding]::UTF8; chcp 65001 > $null
$fixtureRoot = "tests/tmp/stage1-final-review-fixture"
$templateDir = Join-Path $fixtureRoot "templates"
$graphDir = Join-Path $fixtureRoot "mini_novel.storygraph"
New-Item -ItemType Directory -Force -Path $templateDir | Out-Null
Set-Content -LiteralPath (Join-Path $templateDir "法宝分析模板.md") -Encoding UTF8 -Value "# 法宝分析模板`n`n## 必填字段`n- 法宝`n- 原文位置"
python skill-src/storygraph/scripts/storygraph.py prepare-stage1 --source "tests/fixtures/mini_novel.txt" --template-dir $templateDir --graph-dir $graphDir
```

预期：返回 `"status": "prepared"`，写 task packets、chunk-ledger、pending agent-run-ledger，不写成功 canonical graph。

```powershell
$env:PYTHONIOENCODING = "utf-8"; [Console]::OutputEncoding = [Text.Encoding]::UTF8; $OutputEncoding = [Text.Encoding]::UTF8; chcp 65001 > $null
$graphDir = "tests/tmp/stage1-final-review-fixture/mini_novel.storygraph"
python skill-src/storygraph/scripts/storygraph.py merge-stage1 --graph-dir $graphDir
```

在缺少 reviewed agent outputs 时预期：返回 structured failure，包含 `missing_reviewed_agent_outputs` 或 `required_lane_missing`。

写入 reviewed agent outputs 的 fixture 步骤：

```powershell
$env:PYTHONIOENCODING = "utf-8"; [Console]::OutputEncoding = [Text.Encoding]::UTF8; $OutputEncoding = [Text.Encoding]::UTF8; chcp 65001 > $null
$graphDir = "tests/tmp/stage1-final-review-fixture/mini_novel.storygraph"
New-Item -ItemType Directory -Force -Path (Join-Path $graphDir "requirements") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $graphDir "intermediate/lane-outputs/chunk-0001/entities_resources") | Out-Null
New-Item -ItemType Directory -Force -Path (Join-Path $graphDir "intermediate/review-findings") | Out-Null

$requirements = @'
{
  "templates": [
    {
      "template_name": "法宝分析",
      "template_file": "法宝分析模板.md",
      "required_fields": ["法宝", "原文位置"],
      "required_tables": [],
      "required_cards": [],
      "required_case_patterns": [],
      "required_evidence_fields": ["原文位置"],
      "graph_node_mapping": ["artifact"],
      "graph_event_mapping": ["artifact_event"],
      "graph_relation_mapping": ["artifact_relation"],
      "coverage_rules": {"requirement_statuses": ["covered", "needs_review", "not_found_in_source"]}
    }
  ]
}
'@
Set-Content -LiteralPath (Join-Path $graphDir "requirements/template-requirements.json") -Encoding UTF8 -Value $requirements

$laneOutput = @'
{
  "run_id": "run-001",
  "task_packet_id": "stage1:chunk-0001:entities_resources",
  "chunk_id": "chunk-0001",
  "lane_id": "entities_resources",
  "agent_role": "实体道具资源抽取 agent",
  "model_or_agent_identity": "codex-subagent",
  "extracted_nodes": [
    {
      "id": "node:artifact:xiaoping",
      "label": "小瓶",
      "node_type": "artifact",
      "evidence_ids": ["evidence:1"],
      "source_locator": "tests/fixtures/mini_novel.txt#char=0-12"
    }
  ],
  "extracted_edges": [],
  "extracted_events": [],
  "extracted_evidence": [
    {
      "evidence_id": "evidence:1",
      "source_range": [0, 12],
      "source_locator": "tests/fixtures/mini_novel.txt#char=0-12",
      "chunk_id": "chunk-0001",
      "fact_summary": "韩立获得小瓶"
    }
  ],
  "supports_templates": [{"template_name": "法宝分析", "requirement_id": "r1", "status": "covered"}],
  "uncertainties": [],
  "rejected_candidates": [],
  "structured_failures": [],
  "output_status": "completed",
  "produced_at": "2026-06-20T00:00:00Z"
}
'@
Set-Content -LiteralPath (Join-Path $graphDir "intermediate/lane-outputs/chunk-0001/entities_resources/run-001.json") -Encoding UTF8 -Value $laneOutput

$review = @'
{
  "finding_id": "finding-001",
  "reviewer_role": "chunk-lane-reviewer",
  "stage": "stage1",
  "chunk_id": "chunk-0001",
  "lane_id": "entities_resources",
  "probe_or_sample": "pytest tests/test_stage1.py::test_stage1_merge_success_uses_reviewed_agent_outputs -v",
  "actual_output": "passed",
  "expected_output": "passed",
  "severity": "note",
  "status": "closed",
  "repair_required": false,
  "repair_agent_run_id": null
}
'@
Set-Content -LiteralPath (Join-Path $graphDir "intermediate/review-findings/finding-001.json") -Encoding UTF8 -Value $review

python skill-src/storygraph/scripts/storygraph.py ingest-stage1 --graph-dir $graphDir
python skill-src/storygraph/scripts/storygraph.py merge-stage1 --graph-dir $graphDir
```

在测试 fixture 写入 reviewed agent outputs 后预期：`ingest-stage1` 返回 `"status": "ingested"`；`merge-stage1` 返回 `"status": "success"`，`graphify-out/graph.json` metadata 包含：

```json
{
  "semantic_generation": "agent-produced"
}
```

全量最终验收必须另跑完整原文和全部模板流程，命令模板如下：

```powershell
$env:PYTHONIOENCODING = "utf-8"; [Console]::OutputEncoding = [Text.Encoding]::UTF8; $OutputEncoding = [Text.Encoding]::UTF8; chcp 65001 > $null
$source = "E:\AI_Projects\CultivationWorld\docs\世界观参考\凡人修仙传\凡人修仙传.txt"
$templateDir = "E:\AI_Projects\CultivationWorld\docs\世界观参考\模板"
$graphDir = ".storygraph\stage1-final-review-fanren-full.storygraph"

python skill-src/storygraph/scripts/storygraph.py prepare-stage1 --source $source --template-dir $templateDir --graph-dir $graphDir

# 按 agent-driven 流程执行所有 template-requirements agent、chunk lane agents、reviewer agents 和必要 repair agents。
# 允许中间用单模板、单章段、单 chunk 调试，但最终写入 $graphDir 的 agent artifacts 必须覆盖完整原文和全部模板。

python skill-src/storygraph/scripts/storygraph.py ingest-stage1 --graph-dir $graphDir
python skill-src/storygraph/scripts/storygraph.py merge-stage1 --graph-dir $graphDir
python skill-src/storygraph/scripts/storygraph.py validate-graph --graph-dir $graphDir
```

全量验收预期：

- `prepare-stage1` 必须读取完整 `E:\AI_Projects\CultivationWorld\docs\世界观参考\凡人修仙传\凡人修仙传.txt`，并扫描完整 `E:\AI_Projects\CultivationWorld\docs\世界观参考\模板`。
- template requirements、lane outputs、review findings、repair outputs、agent-run-ledger 必须来自真实 agent-driven 流程。
- `ingest-stage1` 和 `merge-stage1` 的最终结果必须覆盖全文 chunk，并包含全部模板的 coverage/readiness 结果。
- reviewer 必须确认没有用 `tests/fixtures/mini_novel.txt`、局部章节、单模板或单 chunk 结果冒充最终完成。
- 若全量流程因缺 agent artifact、缺 review、缺 repair 或模板覆盖不完整而失败，结论必须是未完成，不能降级成成功。

最终报告必须包含：

```markdown
Verification:
- `pytest -v`: PASS
- `validate-skill`: PASS
- legacy semantic path scan: PASS
- prepare-stage1 pending flow: PASS
- merge-stage1 without reviewed outputs fails structurally: PASS
- merge-stage1 with reviewed agent fixture succeeds: PASS
- full corpus + all templates final acceptance: PASS

Architecture checks:
- 通用架构: PASS
- 设计模式适配: PASS
- 配置化覆盖范围: PASS
- Python semantic extraction removed: PASS
```

执行者可选：实施完成并通过 review 后，再由主 Agent 决定是否提交。
