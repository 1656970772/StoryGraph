# StoryGraph 工作流

StoryGraph Stage 1 是 agent-driven 流程。Codex 主 agent 负责读取 skill 文档、配置和任务包，调度分块 lane 抽取 agent、reviewer，以及 reviewer 指定范围内的新 repair/extraction agent。Python 只做 deterministic tool layer：配置加载、路径解析、模板发现、原文分块、任务包生成、schema 校验、ledger、review gate、已审查 bundle 合并、canonical writer、graphify adapter 和写盘。

Stage 1 不由 Python 从小说源文本或模板规则自动产出语义节点、边、事件或证据。语义内容必须来自 Codex agents 的结构化 lane outputs，并经过配置化 reviewer 状态门禁后才能进入 canonical graph。

使用 StoryGraph 时，提供小说源文件、模板目录和目标 graph 目录即可；Codex 主 agent 按 agent-driven workflow 负责调度 template requirements agent、lane extraction agents、reviewer agents 和必要的新 repair agents。

CLI 只是主 agent 内部调用的确定性工具层，不是直接完成 Stage 1 的主入口。

## Codex orchestrator 内部顺序

1. Codex 主 agent 调用 `scripts/storygraph.py validate-skill --skill-root skill-src/storygraph`，确认 skill 源结构完整。
2. Codex 主 agent 通过工具层加载 `config/storygraph.default.json`、可选 `storygraph.local.json`，再叠加显式参数；本机路径、graphify 仓库和策略覆盖应来自 local override 或命令参数。
3. Codex 主 agent 调用 `scripts/storygraph.py inspect-templates --template-dir <template-dir>`，确认模板发现可用。实际存在的模板文件定义集成范围；README 中提到但缺失的模板按配置记警告或失败。
4. Codex 主 agent 调用 `prepare-stage1`。该步骤创建 `<novel-stem>.storygraph/`，写入 manifest、chunk ledger、chunk text、agent task packets 和待执行 ledger/状态；此时不写 canonical graph，也不宣称语义抽取完成。
5. `template-requirements-analysis-agent` 在 `ingest-stage1` 前产出 `requirements/template-requirements.json`；缺少该文件时，`ingest-stage1` 必须返回 `status: failed`、`error.code: template_requirements_missing` 和对应 `validation_errors`。
6. Codex 主 agent 读取 `intermediate/task-packets/<chunk>/<lane>.json`，按配置中的 lane、agent role、证据策略和并发策略调度抽取 agent。agent 输出写入 `intermediate/lane-outputs/<chunk>/<lane>/...json`。
7. reviewer agent 审查 lane output、chunk 覆盖、全局合并风险、模板 readiness 和质量门禁。review findings 必须记录 probe 或样本、实际输出、期望输出、严重级别、修复要求和 repair agent run；必修问题必须开启新的 repair/extraction agent。repair agent 必须先复现 reviewer probe，记录 actual 输出，再把 probe 固化成 RED 测试，完成最小修复后运行目标测试和相关回归测试。
8. Codex 主 agent 调用 `ingest-stage1`。Python 校验 lane outputs、template requirements、review findings、配置枚举、路径边界和 reviewer 状态，只把通过 review gate 的内容整理成 `intermediate/reviewed-bundles/*.json`；未审查或审查未通过的 lane 不进入 merge queue。
9. Codex 主 agent 调用 `merge-stage1`。canonical writer 只读取已审查 bundle，进行确定性归一化、去重、稳定 ID、provenance 合并、evidence index 和 template readiness 汇总，写入 `graphify-out/graph.json` 及相关 manifest/ledger。
10. 可选 graphify adapter 只消费 canonical graph path 或 graph dir，用于可视化和查询增强。graphify 不可用时按 `graphify_adapter.failure_policy` 记录 degraded 或 blocking，不得伪装成 Stage 1 agent extraction 已完成。
11. Codex 主 agent 调用 `validate-graph --graph-dir <graph-dir>`，确认必需产物、schema、review gate、coverage、manifest 状态、single-writer 范围和 graphify adapter ledger 一致。

## 写入与复用规则

- 所有 Stage 1 产物必须经过配置化 single-writer output registry，未管理路径、越界路径和重复写入应失败。
- source hash、stage input hash、task packet schema hash、reviewed output manifest hash、manifest 状态、必需文件、deep graph validation 和 graphify adapter ledger 都必须参与复用判定。
- Stage 2 是 draft-first。默认输出写入 graph draft 目录，不覆盖小说目录中的正式 Markdown；只有显式 `backup-and-overwrite` 策略才能覆盖，`merge` 需要独立 merge contract。
