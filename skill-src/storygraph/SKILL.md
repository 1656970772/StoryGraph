---
name: storygraph
description: 使用 Codex agent-driven Stage 1 构建、校验和复用小说 StoryGraph 图谱。
---

# StoryGraph

当用户提供小说源文件，并要求构建、校验、复用 StoryGraph 图谱，或基于图谱进入后续资料抽取时使用本 skill。

## 读取顺序

1. `references/workflow.md`
2. `references/graph-schema.md`
3. `references/extraction-workflow.md`

## Stage 1 职责边界

Stage 1 的语义生产者是 Codex agents。Codex 主 agent 读取配置和任务包，调度分块 lane 抽取 agent、reviewer 和必要的新 repair/extraction agent；Python 工具只负责确定性的配置加载、路径解析、分块、任务包、schema 校验、ledger、review gate、已审查 bundle 合并、canonical writer、graphify adapter 和写盘。

用户入口是提供小说源文件、模板目录和目标 graph 目录，由 Codex 主 agent 调度 agent-driven Stage 1。内部调用顺序是 `prepare-stage1` -> 读取 `intermediate/agent-dispatch-plan.json` 的 `execution_batches` -> 通过 `next-agent-batches` 按 `agent_policy.max_parallel` 并行调度 template requirements agents -> 等待分片产物并运行 `ingest-template-requirements` -> 通过 `next-agent-batches` 并行调度 lane agents -> 完成 review/repair -> `ingest-stage1` -> `merge-stage1` -> `validate-graph`。`build-stage1` 仅作为兼容入口保留，不作为推荐入口；缺少 reviewed agent outputs 时不得宣称 Stage 1 成功。

template requirements 由多个分片 agents 按配置批量分析模板，分片产物写入 `intermediate/template-requirements-parts/`，再由 `ingest-template-requirements` 校验并汇总成 `requirements/template-requirements.json`；最终文件不绑定某个固定 producer。

graphify 只作为可选的可视化和查询适配层，输入必须是 StoryGraph canonical graph path 或 graph dir；不得把 graphify 或 Python 规则当作 Stage 1 语义抽取来源。

## Stage 2 边界

Stage 2 当前仍是 schema scaffold 和输出策略层。使用配置中的 `stage2_categories`、`stage2_output_policy` 和 `overwrite_policy`；默认 `draft` 策略写入 graph draft 目录，不得覆盖已有正式 Markdown 文档。

汇报 skill source ready 前必须运行 `scripts/storygraph.py validate-skill`。
