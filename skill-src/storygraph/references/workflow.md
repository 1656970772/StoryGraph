# StoryGraph 工作流

StoryGraph Stage 1 是 agent-driven 流程。Codex 主 agent 负责读取 skill 文档、配置和任务包，调度 template requirements agent 和分块综合抽取 agent；reviewer 与 repair/extraction agent 默认作为后置增量流程使用。Python 只做 deterministic tool layer：配置加载、路径解析、模板发现、原文分块、任务包生成、schema 校验、ledger、merge gate、bundle 合并、canonical writer、graphify adapter 和写盘。

Stage 1 不由 Python 从小说源文本或模板规则自动产出语义节点、边、事件或证据。语义内容必须来自 Codex agents 的结构化 lane outputs；默认 `post_merge_incremental` 模式允许未复查但完整的真实 lane outputs 进入 canonical graph，并在 metadata 中标记 `review_status: unreviewed_usable`。

使用 StoryGraph 时，提供小说源文件、模板目录和目标 graph 目录即可；Codex 主 agent 按 agent-driven workflow 负责调度 template requirements agent 和综合 lane extraction agents。默认完整长篇规模是 `chunks * 1`，例如 2452 个 chunks 只需要 2452 个 lane output JSON；如果 local config 显式开启多 lane，才会按配置扩展调用量。

CLI 只是主 agent 内部调用的确定性工具层，不是直接完成 Stage 1 的主入口。

## Codex orchestrator 内部顺序

1. Codex 主 agent 调用 `scripts/storygraph.py validate-skill --skill-root skill-src/storygraph`，确认 skill 源结构完整。
2. Codex 主 agent 通过工具层加载 `config/storygraph.default.json`、可选 `storygraph.local.json`，再叠加显式参数；本机路径、graphify 仓库和策略覆盖应来自 local override 或命令参数。
3. Codex 主 agent 调用 `scripts/storygraph.py inspect-templates --template-dir <template-dir>`，确认模板发现可用。实际存在的模板文件定义集成范围；README 中提到但缺失的模板按配置记警告或失败。
4. Codex 主 agent 调用 `prepare-stage1`。该步骤创建 `<novel-stem>.storygraph/`，写入 manifest、chunk ledger、chunk text、agent task packets、`intermediate/agent-dispatch-plan.json` 和待执行 ledger/状态；dispatch plan 中必须包含 `execution_batches`，此时不写 canonical graph，也不宣称语义抽取完成。`build-stage1` 兼容入口也只到 prepared 状态，不得立刻调用 ingest 检查缺失 agent 产物。
5. Codex 主 agent 先调用 `next-agent-batches --phase template_requirements`，按 `agent_policy.max_parallel` 并行派发 template requirements agents。每个 agent 消费返回 batch 中的 task packet，默认 role 是 `template-requirements-analysis-agent`，每个 agent 负责 1-5 个模板，并在 `ingest-stage1` 前把分片产物写入 `intermediate/template-requirements-parts/batch-*.json`。
6. Codex 主 agent 等待所有 template requirements 分片产物，再调用 `ingest-template-requirements`。Python 只校验并汇总这些分片，写出不绑定固定 producer 的 `requirements/template-requirements.json`；该入口不要求 lane outputs 或 review findings 已存在。
7. Codex 主 agent 再循环调用 `next-agent-batches --phase lane_extraction`，按默认 `comprehensive_extraction` lane、agent role、证据策略、`agent_orchestration.lane_chunks_per_agent` 和 `agent_policy.max_parallel` 并行调度抽取 agent。一个 lane batch agent 可以读取多个 task packet，但必须为每个 task packet 写回独立的 `intermediate/lane-outputs/<chunk>/comprehensive_extraction/...json`。多 lane 是高级配置，不是完整长篇默认路径。
8. Codex 主 agent 调用 `ingest-stage1`。Python 校验 lane outputs、template requirements、配置枚举和路径边界；默认后置增量模式不要求 `coverage/review-findings.json` 存在，但缺少真实 completed lane output 仍失败关闭。未复查 bundle 必须写 `merge_gate_status: unreviewed_usable`，不得伪装成 reviewer `passed`。
9. Codex 主 agent 调用 `merge-stage1`。canonical writer 只读取通过 merge gate 的 bundle，进行确定性归一化、去重、稳定 ID、provenance 合并、evidence index 和 template readiness 汇总，写入 `graphify-out/graph.json` 及相关 manifest/ledger，并记录 `review_status`。
10. 如果用户后续发现遗漏，Codex 主 agent 可以按 chunk、模板、实体或 source range 发起增量 review/repair。review findings 必须记录 probe 或样本、实际输出、期望输出、严重级别、修复要求和 repair agent run；repair agent 必须先复现 reviewer probe，记录 actual 输出，再把 probe 固化成 RED 测试，完成最小修复后运行目标测试和相关回归测试。增量 lane output 使用新的 attempt，例如 `run-002.json`，不要求重跑全部 chunks。
11. 可选 graphify adapter 只消费 canonical graph path 或 graph dir，用于可视化和查询增强。graphify 不可用时按 `graphify_adapter.failure_policy` 记录 degraded 或 blocking，不得伪装成 Stage 1 agent extraction 已完成。
12. Codex 主 agent 调用 `validate-graph --graph-dir <graph-dir>`，确认必需产物、schema、review status、coverage、manifest 状态、single-writer 范围和 graphify adapter ledger 一致。

## 写入与复用规则

- 所有 Stage 1 产物必须经过配置化 single-writer output registry，未管理路径、越界路径和重复写入应失败。
- 如果当前 Codex 环境没有可用 subagent runner，主 agent 必须以 `stage1_runner_unavailable` 停止，并说明无法消费 `execution_batches`；不得在未派发 agent 时调用 ingest/merge 宣称完成。
- source hash、stage input hash、task packet schema hash、reviewed output manifest hash、manifest 状态、必需文件、deep graph validation 和 graphify adapter ledger 都必须参与复用判定。
- Stage 2 是 draft-first。默认输出写入 graph draft 目录，不覆盖小说目录中的正式 Markdown；只有显式 `backup-and-overwrite` 策略才能覆盖，`merge` 需要独立 merge contract。
