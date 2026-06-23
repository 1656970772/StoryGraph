# StoryGraph CLI

StoryGraph CLI 位于 `skill-src/storygraph/scripts/storygraph.py`。CLI 负责 deterministic tool layer：配置、路径、模板发现、Stage 1 准备、agent 产物摄入、已审查 bundle 合并、canonical graph 写盘、graphify adapter 和验证。Stage 1 的语义内容由 Codex agents 产生，不由 CLI 自动生成。

## CLI 工具层命令

这些命令主要供 Codex agent orchestrator 在 Stage 1 工作流内部调用，或用于调试确定性契约。面向使用者的入口是把 `source`、`template-dir` 和 `graph-dir` 交给 Codex，由 Codex 主 agent 调度 template requirements agent 和默认单次综合 lane extraction agents；reviewer 和 repair agents 默认只在用户发现遗漏后作为后置增量流程调用。

CLI 本身不是直接完成 Stage 1 的主入口；它只负责确定性的准备、摄入、合并和验证。

## 用户模式

StoryGraph skill 对用户只暴露三种模式：`full`、`stage2_incremental`、`full_incremental`。

- `full` 是默认全量模式：完成 Stage 1 并通过 `validate-graph` 后再进入 Stage 2。
- `stage2_incremental` 只做阶段 2 增量：先验证既有 Stage 1，不重写 Stage 1，再用 `prepare-stage2 --selection changed-or-missing` 派发变更、缺失或未渲染模板。
- `full_incremental` 用于模板内容变更：重做 template requirements 分片和三轮整理，再按受影响模板相关支撑做 Stage 1 增量，最后按 Stage 2 增量策略处理模板文档。

```powershell
python skill-src/storygraph/scripts/storygraph.py --version
python skill-src/storygraph/scripts/storygraph.py validate-skill --skill-root skill-src/storygraph
python skill-src/storygraph/scripts/storygraph.py config-check --config skill-src/storygraph/config/storygraph.default.json --local-override path/to/storygraph.local.json
python skill-src/storygraph/scripts/storygraph.py inspect-templates --template-dir path/to/templates --config skill-src/storygraph/config/storygraph.default.json --local-override path/to/storygraph.local.json
python skill-src/storygraph/scripts/storygraph.py prepare-stage1 --source path/to/novel.txt --template-dir path/to/templates --graph-dir path/to/novel.storygraph
python skill-src/storygraph/scripts/storygraph.py inspect-dispatch --graph-dir path/to/novel.storygraph
python skill-src/storygraph/scripts/storygraph.py next-agent-batches --graph-dir path/to/novel.storygraph --phase template_requirements --limit 6
python skill-src/storygraph/scripts/storygraph.py ingest-template-requirements --graph-dir path/to/novel.storygraph
python skill-src/storygraph/scripts/storygraph.py claim-agent-batches --graph-dir path/to/novel.storygraph --phase template_requirements_refinement --limit 3
python skill-src/storygraph/scripts/storygraph.py ingest-template-requirements --graph-dir path/to/novel.storygraph
python skill-src/storygraph/scripts/storygraph.py claim-agent-batches --graph-dir path/to/novel.storygraph --phase lane_extraction --limit 6
python skill-src/storygraph/scripts/storygraph.py claim-agent-batches --graph-dir path/to/novel.storygraph --phase lane_extraction --limit 1
python skill-src/storygraph/scripts/storygraph.py ingest-stage1 --graph-dir path/to/novel.storygraph
python skill-src/storygraph/scripts/storygraph.py merge-stage1 --graph-dir path/to/novel.storygraph
python skill-src/storygraph/scripts/storygraph.py validate-graph --graph-dir path/to/novel.storygraph
```

`--local-override` 是可选参数；如果显式传入但文件不存在，CLI 返回 exit code `2` 并输出结构化 JSON 错误。

## Stage 1 退出与 JSON 契约

`prepare-stage1`、`claim-agent-batches`、`ingest-template-requirements`、`ingest-stage1`、`merge-stage1` 和 `validate-graph` 都遵循同一类 CLI 退出规则：成功返回 exit code `0`，结构化失败返回 exit code `2`，并输出结构化 JSON。JSON payload 分两类：Stage 1 动作命令（`prepare-stage1`、`claim-agent-batches`、`ingest-template-requirements`、`ingest-stage1`、`merge-stage1`）使用 `status`、`error`、`validation_errors`、`warnings`、`next_action` 等字段表达状态和下一步动作，不承诺 `ok` 字段；`validate-graph` 使用 `ok`、`errors`、`warnings` 和 `review_status` 表达验证与复查状态。

## Stage 1 agent-driven 内部流程

1. Codex 主 agent 调用 `prepare-stage1` 读取 source、template dir 和配置，创建 graph dir，写入 manifest、`intermediate/stage1-input-cache.json`、chunk ledger、chunk text、agent task packets、`intermediate/agent-dispatch-plan.json` 和 pending ledger/状态。lane extraction task packet 会携带 `extraction_quality_rules.path/content`；dispatch plan 包含 `execution_batches`；该命令成功时返回 `status: prepared`，并在 `cache.template_requirements`、`cache.source_flow` 中报告 `reused`、`refreshed` 或 `partial_refreshed`。
2. 如果 `cache.template_requirements` 不是 `reused`，Codex 主 agent 循环调用 `next-agent-batches --phase template_requirements`，按选中 agent adapter 的 `max_parallel_tasks` 并行调度多个 template requirements agents。默认 role 是 `template-requirements-analysis-agent`，每个 agent 负责 1-5 个发生变化或新增的模板，在 `ingest-stage1` 前输出到 `intermediate/template-requirements-parts/batch-*.json`。如果模板只发生删除，`prepare-stage1` 会返回 `next_action: ingest_template_requirements`，无需派发 template requirements agent。
3. Codex 主 agent 等待所有 template requirements 分片产物后调用 `ingest-template-requirements`，CLI 先校验并汇总完整模板详单到 `intermediate/template-requirements-raw.json`，不要求 lane outputs 或 review findings 已存在。启用 refinement 时，该命令在三轮优化尚未完成前返回 `status: requirements_refinement_pending` 和 `next_action: dispatch_template_requirements_refinement_agents`，不会提前写最终 `requirements/template-requirements.json`。分片未齐时的 `template_requirements_part_missing` 是等待信号；单个分片完成后应先运行分片 contract/schema validator，全部分片齐全后才运行全局 ingest。
4. Codex 主 agent 顺序执行 `template_requirements_refinement` phase。该 phase 固定三轮，`claim-agent-batches --phase template_requirements_refinement --limit <N>` 每次最多只领取当前最早可执行的一轮：`pass-1.json`、`pass-2.json`、`pass-3.json`。上一轮缺失、仍在 running 或 summary schema 校验失败时，下一轮不会暴露。每轮 agent 都必须读取 raw 全集和上一轮结果；pass 1 的上一轮输入就是 raw 全集。三轮完成后再次调用 `ingest-template-requirements`，CLI 校验 pass 1/2/3 的 summary payload 和模板覆盖，并把 pass 3 写为最终小文件 `requirements/template-requirements.json`。
5. Codex 主 agent 先按选中 agent adapter 的 `max_parallel_tasks` 调用 `claim-agent-batches --phase lane_extraction --limit <agent_max_parallel_tasks>` 派满首轮，再在每完成一个 batch 的全部 `expected_output_paths` 后调用 `claim-agent-batches --phase lane_extraction --limit 1` 补位。调度每个 lane extraction agent 时，必须把对应 task packet 内的 `extraction_quality_rules.content` 原样作为附加质量规则交给 agent，并提供 graph dir、task packet、expected output 的绝对路径。`intermediate/agent-dispatch-state.json` 记录 batch 的 `running` / `completed` 状态；claim 返回 `status`、`phase`、`claimed_count`、`in_flight_count`、`available_slots`、`pending_count`、`completed_count` 和 `batches`。当 `pending_count == 0` 且 `in_flight_count == 0`，并且全部 expected output 文件存在、UTF-8 without BOM、lane output contract 校验通过时，主 agent 才进入 `ingest-stage1`。默认规模是 `chunks * 1`，例如 2452 chunks 只对应 2452 个 lane output JSON；多 lane 仅在 local config 显式开启时使用。
6. Codex 主 agent 调用 `ingest-stage1` 读取 graph dir 中的最终 template requirements summary 和 lane outputs。默认 `post_merge_incremental` 模式不要求 `coverage/review-findings.json`，但缺少真实 completed lane output、坏 JSON、伪造 producer 或越界路径会 fail closed。
7. Codex 主 agent 调用 `merge-stage1` 只读取通过 merge gate 的 bundles，生成 canonical `graphify-out/graph.json`、evidence index、template readiness、manifest 和 ledger。未复查但可用的结果写入 `review_status: unreviewed_usable`，不得伪装成 reviewer `passed`。如果返回 canonical validation errors，应修复 reviewed bundle 或 lane output 的 source locator、stable id、evidence refs、status enum、supports_templates、node/edge/event 引用闭合等根因，再重跑 merge。可选 graphify adapter 只消费 canonical graph path 或 graph dir，用于可视化和查询增强；`validation_errors: []` 但带 `graphify_degraded` / `graphify_failed` 时，表示 canonical graph 已写出但 adapter 降级，仍必须继续执行 `validate-graph`。
8. 如果用户发现遗漏，Codex 主 agent 可按 chunk、模板、实体或时间段发起增量 review/repair。repair agent 必须先复现 reviewer probe，记录 actual 输出，再把 probe 固化成 RED 测试，完成最小修复后运行目标测试和相关回归测试。增量 lane output 使用新的 attempt，例如 `run-002.json`。
9. Codex 主 agent 调用 `validate-graph` 检查必需 Stage 1 产物、失败 ledger、graph schema、template readiness、chunk coverage、evidence references、manifest stage status、review status 和 single-writer scopes。最终交付前必须看到 `ok: true`、`errors: []`，并额外检查 graph dir 下所有 Stage 1 JSON 没有 UTF-8 BOM。`manifest.json` 的 `stage1: success`、`graphify-out/graph.json` 存在或 `merge-stage1` 写出了文件，都不是最终完成声明的替代。

`build-stage1` 仍保留为兼容入口，不作为推荐入口。缺少真实 agent outputs 或 template requirements 时，不得把它的返回结果描述为 Stage 1 已成功完成；默认后置增量模式下缺少 review findings 只表示 `review_status: unreviewed_usable`。

如果当前环境没有可用 subagent runner，Codex 主 agent 必须以 `stage1_runner_unavailable` 停止，不能继续调用 ingest/merge 并宣称完成。

## 运行中阻断处理准则

- 子 agent 未落盘或超时：先关闭仍在运行的旧 agent，再按同一 task packet 新开 repair/extraction agent。不要让旧 agent 晚到输出覆盖已修复文件。
- 主 agent 临时补写：只允许作为 fallback，并必须在输出的 `model_or_agent_identity`、`uncertainties` 或最终运行报告中写明来源、chunk 数量、质量影响和后续复核建议。
- bulk fallback：只用于打通 deterministic pipeline 和验证 ingest/merge/validate 链路，不等同于完成高质量语义抽取。fallback chunk 应保持 `review_status: unreviewed_usable` 或更保守状态。
- 修复中间产物：如果修的是 lane output，必须重跑 `ingest-stage1`、`merge-stage1` 和 `validate-graph`；如果修的是 reviewed bundle、coverage ledger、agent ledger 或 task packet，至少重跑 `merge-stage1` 和 `validate-graph`。
- coverage 完成态：`coverage/chunk-ledger.json` 中每个 chunk 必须是 `completed`，`coverage/evidence-index.json` 必须与 canonical graph 的 evidence 同 ID，`coverage/template-readiness.json` 必须覆盖最终 requirements 的全部模板或 summary template list，`coverage/agent-run-ledger.json` 必须满足 single-writer。

## 失败与复用

常见结构化失败码示例包括 `source_unreadable`、`extraction_quality_rules_unreadable`、`template_requirements_missing`、`graphify_unavailable`、`graphify_failed` 和 `graphify_artifact_missing`。未在实现和测试中固定的错误类别不作为稳定失败码承诺；调用方应以当前 JSON payload 中的 `error`、`errors` 或 `status` 字段为准。

`prepare-stage1` 的输入缓存清单位于 `intermediate/stage1-input-cache.json`，记录 source path/hash/size、模板 inventory（模板名、相对模板文件、MD5、SHA-256）、chunk strategy hash、抽取质量规则摘要和 lane/task packet 相关配置 hash。

模板 requirements 是模板文件级增量：全部模板 MD5 未变时跳过 template requirements phase 并复用既有最终 summary；部分模板变更或新增时只生成对应模板 task packet。启用 refinement 后，完整详单保存在 `intermediate/template-requirements-raw.json`，最终 `requirements/template-requirements.json` 是三轮 refinement 后的分类摘要；模板全集发生变化时 raw 和三轮 refinement 需要重新生成，避免摘要与模板覆盖不一致。

原文流程是整体级重建：source hash、chunk strategy 或 lane/task packet 配置未变且 chunk ledger、chunk text、lane task packets 完整时复用这些产物；source hash 变化时完整重建 chunk ledger、chunk text、lane task packets 和 lane dispatch batches，并隔离旧 lane outputs、reviewed bundles、merge queue 与 canonical graph，避免新一轮 ingest/merge 误用旧结果。

## Stage 2 Scaffold

Stage 2 是 agent-driven 模板文档生成工具链。Python CLI 只负责确定性的准备、调度状态、schema/证据闭合校验、ledger、路径策略和 Markdown 渲染；模板正文、归纳判断和章节内容必须来自 Stage 2 agent 写入的 `stage2-extraction-record.v1`，不得由 Python 根据图谱自动编造。

```powershell
python skill-src/storygraph/scripts/storygraph.py prepare-stage2 --graph-dir path/to/novel.storygraph --template-dir path/to/templates --overwrite-policy draft
python skill-src/storygraph/scripts/storygraph.py prepare-stage2 --graph-dir path/to/novel.storygraph --template-dir path/to/templates --overwrite-policy draft --selection changed-or-missing
python skill-src/storygraph/scripts/storygraph.py inspect-stage2-dispatch --graph-dir path/to/novel.storygraph
python skill-src/storygraph/scripts/storygraph.py claim-stage2-batches --graph-dir path/to/novel.storygraph --limit 6
python skill-src/storygraph/scripts/storygraph.py ingest-stage2 --graph-dir path/to/novel.storygraph
python skill-src/storygraph/scripts/storygraph.py render-stage2 --graph-dir path/to/novel.storygraph
python skill-src/storygraph/scripts/storygraph.py validate-stage2 --graph-dir path/to/novel.storygraph
```

`prepare-stage2` 读取 `requirements/template-requirements.json`、`coverage/template-readiness.json`、`coverage/evidence-index.json`、`intermediate/stage1-input-cache.json` 和模板目录，按模板文档生成 `intermediate/stage2/task-packets/*.json` 与 `intermediate/stage2/dispatch-state.json`。每个 task packet 只包含一个模板、该模板关联的 requirement category/requirement/evidence 上下文，以及唯一预期 agent 输出路径 `intermediate/stage2/extraction-records/<模板名>/run-001.json`。

`claim-stage2-batches` 维护模板级 `pending` / `running` / `completed` 滑动窗口；当 running batch 的唯一预期 extraction record 已落盘且通过校验时才标记完成，并按 `--limit` 补领新的模板 batch。`ingest-stage2` 校验每个 extraction record 的 `document_sections`、`facts`、分类标签、overwrite policy 和 evidence id 是否闭合到 Stage 1 evidence index，并更新 `coverage/template-run-ledger.json`、`coverage/template-evidence-usage.json` 和 `coverage/template-gap-report.md`。

默认输出策略是 draft-first：`render-stage2` 在 `draft` 策略下写入 `<graph_dir>/<stage2_output_policy.default_dir>/<template_name>.md`，不会覆盖小说目录中同名正式 Markdown。显式 `backup-and-overwrite` 会先把已存在的正式文档复制到 `.bak`，再用单模板 agent 产出的 Markdown 整篇覆盖正式文档；`merge` 仍需要独立 merge contract，本轮工具链会失败关闭而不会伪合并。
