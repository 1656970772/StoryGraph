---
name: storygraph
description: 使用 Codex agent-driven Stage 1 构建、校验和复用小说 StoryGraph 图谱。
---

# StoryGraph

当用户提供小说源文件，并要求构建、校验、复用 StoryGraph 图谱，或基于图谱进入后续资料抽取时使用本 skill。

## 用户模式

本 skill 只使用三种用户模式：

- `full`：默认全量模式。执行 Stage 1 全流程，直到 `validate-graph` 通过，再进入 Stage 2。
- `stage2_incremental`：阶段 2 增量模式。先验证既有 Stage 1，不改 Stage 1，只按 `stage2_incremental_policy.selection` 处理变更、缺失或未渲染的 Stage 2 模板。
- `full_incremental`：全量增量模式。适合模板内容变更；重新生成 template requirements 分片和三轮整理，再按 `stage1_delta_policy.scope` 只重做受影响模板相关支撑，随后 Stage 2 只处理受影响或缺失模板。

## 读取顺序

1. `references/workflow.md`
2. `references/graph-schema.md`
3. `references/extraction-workflow.md`

## Stage 1 职责边界

Stage 1 的语义生产者是 Codex agents。默认配置使用单次综合抽取 lane：每个 chunk 只派发一次 `comprehensive_extraction`，产出节点、边、事件、证据、模板支撑、疑点、拒绝候选和结构化失败；多 lane 专业抽取仍可通过 local config 显式开启。Python 工具只负责确定性的配置加载、路径解析、分块、任务包、schema 校验、ledger、merge gate、bundle 合并、canonical writer、graphify adapter 和写盘。

用户入口是提供小说源文件、模板目录和目标 graph 目录，由 Codex 主 agent 按用户模式调度 agent-driven Stage 1/Stage 2。`full` 内部调用顺序是 `prepare-stage1` -> 读取 `intermediate/agent-dispatch-plan.json` 的 `execution_batches` -> 通过 `next-agent-batches` 按 `agent_policy.max_parallel` 并行调度 template requirements agents -> 等待分片产物并运行 `ingest-template-requirements` -> 通过 `claim-agent-batches --phase template_requirements_refinement` 串行领取三轮整理 -> 再次 `ingest-template-requirements` 写出正式 requirements -> 通过 `claim-agent-batches` 滑动窗口调度综合 lane agents，并在 `intermediate/agent-dispatch-state.json` 记录 `running` / `completed` -> `ingest-stage1` -> `merge-stage1` -> `validate-graph`。lane 阶段首次按 `agent_orchestration.max_parallel_agents` claim 派满，之后每完成一个 batch 就 `--limit 1` claim 一个新 batch；调度每个 lane extraction agent 时，必须把对应 task packet 中的 `extraction_quality_rules.content` 原样作为附加质量规则交给 agent。当 `pending_count == 0` 且 `in_flight_count == 0` 时才进入 `ingest-stage1`。默认 `review_policy.mode` 为 `post_merge_incremental`，未复查结果会标记为 `review_status: unreviewed_usable`；如果用户发现遗漏，再按 chunk、模板、实体或时间段发起增量 review/repair。`build-stage1` 仅作为兼容入口保留，不作为推荐入口；缺少真实 agent lane outputs 时不得宣称 Stage 1 成功。

template requirements 由多个分片 agents 按配置批量分析模板，分片产物写入 `intermediate/template-requirements-parts/`。`ingest-template-requirements` 先汇总完整 raw JSON 到 `intermediate/template-requirements-raw.json`；随后三轮 refinement agent 必须严格串行，每轮都读取 raw 全集和上一轮结果，pass-1 完成并校验后才领取 pass-2，pass-2 完成并校验后才领取 pass-3。pass-3 经 summary schema 校验后成为 `requirements/template-requirements.json`；最终文件不绑定某个固定 producer。

graphify 只作为可选的可视化和查询适配层，输入必须是 StoryGraph canonical graph path 或 graph dir；不得把 graphify 或 Python 规则当作 Stage 1 语义抽取来源。

## Stage 2 边界

Stage 2 是 agent-driven 模板文档生成工具链。主 agent 先运行 `prepare-stage2`，按模板文档生成 `intermediate/stage2/task-packets/*.json`；每个 task packet 只对应一个模板、一个 Stage 2 agent、一个 `intermediate/stage2/extraction-records/<模板名>/run-001.json` 和一个输出文档。task packet 会携带该模板覆盖到的 template requirements summary category、相关 requirements、原始模板 Markdown 路径、模板 hash、Stage 1 证据和 `stage2_render_policy`。Python 只负责 schema 校验、证据闭合、ledger、路径策略、审查草稿整理、正文准入过滤、去重归并和 Markdown 渲染；语义内容仍来自 Stage 2 agent 的结构化记录。

默认输出策略仍是 draft-first。`render-stage2` 使用配置中的 `stage2_categories`、`stage2_output_policy`、`overwrite_policy` 和 `stage2_render_policy`，在 `draft` 策略下只写审查型草稿条目：名称、分类、用途/材料、source range、原文摘录、证据、置信度和 review status；草稿不得渲染前置声明、资料来源说明、模板说明或 agent 预写的 `document_sections` 正文。显式 `backup-and-overwrite` 会先备份小说目录中的同名正式 Markdown，再只从 ledger 中的原始模板 Markdown 路径读取并校验模板 hash，然后按模板标题结构，基于草稿条目执行配置化正文准入、去重和保守归并后只输出正式案例；`merge` 需要单独 merge contract 和复核流程。未命名、组合性描述、低置信度、来源不足、用途/材料/成分不闭合或待复核状态的条目不得进入正式正文，只能留在草稿或待复核数据中。

汇报 skill source ready 前必须运行 `scripts/storygraph.py validate-skill`。
