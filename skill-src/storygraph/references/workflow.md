# StoryGraph 工作流

StoryGraph Stage 1 是 agent-driven 流程。Codex 主 agent 负责读取 skill 文档、配置和任务包，调度 template requirements agent 和分块综合抽取 agent；reviewer 与 repair/extraction agent 默认作为后置增量流程使用。Python 只做 deterministic tool layer：配置加载、路径解析、模板发现、原文分块、任务包生成、schema 校验、ledger、merge gate、bundle 合并、canonical writer、graphify adapter 和写盘。

Stage 1 不由 Python 从小说源文本或模板规则自动产出语义节点、边、事件或证据。语义内容必须来自 Codex agents 的结构化 lane outputs；默认 `post_merge_incremental` 模式允许未复查但完整的真实 lane outputs 进入 canonical graph，并在 metadata 中标记 `review_status: unreviewed_usable`。

使用 StoryGraph 时，提供小说源文件、模板目录和目标 graph 目录即可；Codex 主 agent 按 agent-driven workflow 负责调度 template requirements agent 和综合 lane extraction agents。默认完整长篇规模是 `chunks * 1`，例如 2452 个 chunks 只需要 2452 个 lane output JSON；如果 local config 显式开启多 lane，才会按配置扩展调用量。

CLI 只是主 agent 内部调用的确定性工具层，不是直接完成 Stage 1 的主入口。

## 用户模式

- `full`：默认全量模式。执行 Stage 1 的 template requirements、三轮 refinement、lane extraction、ingest、merge 和 `validate-graph`，通过后再执行 Stage 2。
- `stage2_incremental`：阶段 2 增量模式。先运行 `validate-graph` 确认既有 Stage 1 可用，不修改 Stage 1；随后 `prepare-stage2 --selection changed-or-missing` 只派发模板 hash 变化、record 缺失、渲染目标缺失或未完成的 Stage 2 模板。
- `full_incremental`：全量增量模式。模板文件变化时重新生成 template requirements 分片和三轮 refinement；按 `stage1_delta_policy.scope == changed-template-support` 只重做受影响模板相关支撑，不推倒未受影响模板成果；Stage 2 继续使用 `changed-or-missing` 策略。

## Codex orchestrator 内部顺序

1. Codex 主 agent 调用 `scripts/storygraph.py validate-skill --skill-root skill-src/storygraph`，确认 skill 源结构完整。
2. Codex 主 agent 通过工具层加载 `config/storygraph.default.json`、可选 `storygraph.local.json`，再叠加显式参数；本机路径、graphify 仓库和策略覆盖应来自 local override 或命令参数。
3. Codex 主 agent 调用 `scripts/storygraph.py inspect-templates --template-dir <template-dir>`，确认模板发现可用。实际存在的模板文件定义集成范围；README 中提到但缺失的模板按配置记警告或失败。
4. Codex 主 agent 调用 `prepare-stage1`。该步骤创建 `<novel-stem>.storygraph/`，写入 manifest、`intermediate/stage1-input-cache.json`、chunk ledger、chunk text、agent task packets、`intermediate/agent-dispatch-plan.json` 和待执行 ledger/状态；dispatch plan 中必须包含 `execution_batches`，此时不写 canonical graph，也不宣称语义抽取完成。返回 payload 的 `cache.template_requirements` 和 `cache.source_flow` 表示本轮复用或刷新状态。`build-stage1` 兼容入口也只到 prepared 状态，不得立刻调用 ingest 检查缺失 agent 产物。
5. 如果 `cache.template_requirements` 不是 `reused`，Codex 主 agent 调用 `next-agent-batches --phase template_requirements`，按选中 agent adapter 的 `max_parallel_tasks` 并行派发 template requirements agents。每个 agent 消费返回 batch 中的 task packet，默认 role 是 `template-requirements-analysis-agent`，每个 agent 负责 1-5 个发生变化或新增的模板，并在 `ingest-stage1` 前把分片产物写入 `intermediate/template-requirements-parts/batch-*.json`。如果模板只发生删除，主 agent 直接进入 `ingest-template-requirements`。
6. Codex 主 agent 等待所有 template requirements 分片产物，再调用 `ingest-template-requirements`。Python 只校验并汇总这些分片，写出 `intermediate/template-requirements-raw.json`；该入口不要求 lane outputs 或 review findings 已存在。增量模式按模板文件 key 替换、追加或删除条目；既有总 JSON 缺失、损坏或存在重复模板 key 时 fail closed。单个分片完成时，主 agent 只运行该分片的 contract/schema 校验；在分片未齐时，`ingest-template-requirements` 返回 `template_requirements_part_missing` 属于等待信号，不应当作该分片内容失败。
7. 如果 `ingest-template-requirements` 返回 `requirements_refinement_pending`，Codex 主 agent 通过 `claim-agent-batches --phase template_requirements_refinement --limit <N>` 串行领取三轮整理。pass-1 必须完成并通过 summary schema 校验后才会暴露 pass-2；pass-2 同理；pass-3 完成后再次运行 `ingest-template-requirements`，把 pass-3 写为正式 `requirements/template-requirements.json`。每轮 agent 都读取 raw 全集和上一轮结果；pass-1 的上一轮输入等于 raw 全集。
8. Codex 主 agent 再调用 `claim-agent-batches` 维护 lane extraction 滑动窗口：首次用选中 agent adapter 的 `max_parallel_tasks` 作为 `--limit` 派满；之后每个 batch 的全部 `expected_output_paths` 写齐后，用 `--limit 1` 补领一个新的 pending batch。claim 会先把已写齐输出的 running batch 标记为 `completed`，再把新领取 batch 写入 `intermediate/agent-dispatch-state.json` 的 `running` 状态。一个 lane batch agent 可以读取多个 task packet，但必须为每个 task packet 写回独立的 `intermediate/lane-outputs/<chunk>/comprehensive_extraction/...json`。分派 agent 时必须给出 graph dir、task packet、expected output 的绝对路径；JSON 产物内仍使用相对 artifact path。若 agent 超时或未落盘，主 agent 应关闭旧 agent 后按同一 task packet 重派新 agent，避免晚到输出覆盖。当 claim 返回 `pending_count == 0` 且 `in_flight_count == 0`，且全部 expected outputs 均存在、UTF-8 without BOM、lane output contract 校验通过时，主 agent 才进入 `ingest-stage1`。多 lane 是高级配置，不是完整长篇默认路径。
9. Codex 主 agent 调用 `ingest-stage1`。Python 校验 lane outputs、template requirements、配置枚举和路径边界；默认后置增量模式不要求 `coverage/review-findings.json` 存在，但缺少真实 completed lane output 仍失败关闭。未复查 bundle 必须写 `merge_gate_status: unreviewed_usable`，不得伪装成 reviewer `passed`。
10. Codex 主 agent 调用 `merge-stage1`。canonical writer 只读取通过 merge gate 的 bundle，进行确定性归一化、去重、稳定 ID、provenance 合并、evidence index 和 template readiness 汇总，写入 `graphify-out/graph.json` 及相关 manifest/ledger，并记录 `review_status`。如果 `merge-stage1` 报 canonical graph validation error，优先修复 reviewed bundles 或 lane outputs 中的 schema/引用根因，再重跑 `merge-stage1`；不要修改 validator 放宽约束。`validation_errors: []` 但有 `graphify_degraded` 或 `graphify_failed` 表示 canonical graph 已生成但 graphify adapter 降级，仍需进入 `validate-graph` 做最终判定。
11. 如果用户后续发现遗漏，Codex 主 agent 可以按 chunk、模板、实体或 source range 发起增量 review/repair。review findings 必须记录 probe 或样本、实际输出、期望输出、严重级别、修复要求和 repair agent run；repair agent 必须先复现 reviewer probe，记录 actual 输出，再把 probe 固化成 RED 测试，完成最小修复后运行目标测试和相关回归测试。增量 lane output 使用新的 attempt，例如 `run-002.json`，不要求重跑全部 chunks。
12. 可选 graphify adapter 只消费 canonical graph path 或 graph dir，用于可视化和查询增强。graphify 不可用时按 `graphify_adapter.failure_policy` 记录 degraded 或 blocking，不得伪装成 Stage 1 agent extraction 已完成。
13. Codex 主 agent 调用 `validate-graph --graph-dir <graph-dir>`，确认必需产物、schema、review status、coverage、manifest 状态、single-writer 范围和 graphify adapter ledger 一致。最终完成声明必须同时满足：`validate-graph` 返回 `ok: true`、`errors: []`，所有 Stage 1 JSON artifact 的 BOM 计数为 0，manifest、coverage ledger、agent-run-ledger 与 graph 规模互相一致。只看到 `manifest.stage_status.stage1 == success` 或 `graphify-out/graph.json` 存在，不足以宣称 Stage 1 完成。

## 阻断处理与降级标注

- 主 agent 不得把主观补写或 bulk fallback 混同为高质量 agent 精抽。若为了打通工具链临时生成粗粒度 lane output，必须在 `model_or_agent_identity`、`uncertainties` 或最终报告中标明 fallback 来源、chunk 数量、质量影响和后续复核建议。
- bulk fallback 只能用于恢复 deterministic pipeline、验证 ingest/merge/validate 链路，不能替代正常分块语义抽取。任何 fallback chunk 的 `review_status` 应保持 `unreviewed_usable` 或更保守状态。
- 修复 reviewed bundles、coverage ledger、agent-run-ledger、task packets 或 graphify artifact 后，必须重新执行对应下游步骤：至少重跑 `merge-stage1` 与 `validate-graph`。如果修复发生在 lane output 层，还必须重新执行 `ingest-stage1`。
- coverage 账本不得只依赖旧 prepared 状态。Stage 1 完成态必须保证 `coverage/chunk-ledger.json` 中每个 chunk 的 `extraction_status` 为 `completed`，`coverage/evidence-index.json` 与 canonical graph 的 `evidence_index` 同 ID，`coverage/template-readiness.json` 覆盖最终 requirements 的全部模板或 summary 覆盖列表，`coverage/agent-run-ledger.json` 满足 single-writer。

## 写入与复用规则

- 所有 Stage 1 产物必须经过配置化 single-writer output registry，未管理路径、越界路径和重复写入应失败。
- 如果当前 Codex 环境没有可用 subagent runner，主 agent 必须以 `stage1_runner_unavailable` 停止，并说明无法消费 `execution_batches`；不得在未派发 agent 时调用 ingest/merge 宣称完成。
- `intermediate/stage1-input-cache.json` 记录 source path/hash/size、模板 inventory（模板名、相对模板文件、MD5、SHA-256）、chunk strategy hash 和 lane/task packet 相关配置 hash。模板 requirements 按模板文件级增量复用：MD5 全部未变时跳过 template requirements phase；部分变更或新增时只派发对应模板；删除模板时从总 requirements JSON 移除对应条目。
- 原文流程按 source 整体级复用或重建：source hash、chunk strategy 和 lane/task packet 配置未变且 chunk ledger、chunk text、lane task packets 完整时复用；source hash 变化时完整重建 chunk ledger、chunk text、lane task packets 和 lane dispatch batches，并隔离旧 lane outputs、reviewed bundles、merge queue 与 canonical graph，避免新 ingest/merge 误用旧结果。
- Stage 2 是 agent-driven 文档生成。Python 按模板文档生成 task packet、维护 dispatch state、校验 agent extraction record、更新 ledger 并渲染 Markdown；语义内容必须由 Stage 2 agent 产生。每个模板文档只派发一个 Stage 2 agent，并只写一个 `stage2-extraction-record.v1`。task packet 携带 `stage2_render_policy`，正式渲染只信任 ledger 中由模板发现阶段写入的模板路径和 hash，不读取 agent record 中的模板路径。默认 `draft` 输出写入 graph draft 目录，只保留审查型结构化条目和证据信息，不渲染前置声明、资料来源清单、模板说明或 agent 预写正文。显式 `backup-and-overwrite` 会先备份再覆盖正式 Markdown；正式正文必须读取原始模板 Markdown 的标题结构，并基于草稿条目按配置化准入、去重和保守归并规则输出案例。`merge` 需要独立 merge contract。
