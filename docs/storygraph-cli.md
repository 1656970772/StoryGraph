# StoryGraph CLI

StoryGraph CLI 位于 `skill-src/storygraph/scripts/storygraph.py`。CLI 负责 deterministic tool layer：配置、路径、模板发现、Stage 1 准备、agent 产物摄入、已审查 bundle 合并、canonical graph 写盘、graphify adapter 和验证。Stage 1 的语义内容由 Codex agents 产生，不由 CLI 自动生成。

## CLI 工具层命令

这些命令主要供 Codex agent orchestrator 在 Stage 1 工作流内部调用，或用于调试确定性契约。面向使用者的入口是把 `source`、`template-dir` 和 `graph-dir` 交给 Codex，由 Codex 主 agent 调度 template requirements agent 和默认单次综合 lane extraction agents；reviewer 和 repair agents 默认只在用户发现遗漏后作为后置增量流程调用。

CLI 本身不是直接完成 Stage 1 的主入口；它只负责确定性的准备、摄入、合并和验证。

```powershell
python skill-src/storygraph/scripts/storygraph.py --version
python skill-src/storygraph/scripts/storygraph.py validate-skill --skill-root skill-src/storygraph
python skill-src/storygraph/scripts/storygraph.py config-check --config skill-src/storygraph/config/storygraph.default.json --local-override path/to/storygraph.local.json
python skill-src/storygraph/scripts/storygraph.py inspect-templates --template-dir path/to/templates --config skill-src/storygraph/config/storygraph.default.json --local-override path/to/storygraph.local.json
python skill-src/storygraph/scripts/storygraph.py prepare-stage1 --source path/to/novel.txt --template-dir path/to/templates --graph-dir path/to/novel.storygraph
python skill-src/storygraph/scripts/storygraph.py inspect-dispatch --graph-dir path/to/novel.storygraph
python skill-src/storygraph/scripts/storygraph.py next-agent-batches --graph-dir path/to/novel.storygraph --phase template_requirements --limit 6
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

1. Codex 主 agent 调用 `prepare-stage1` 读取 source、template dir 和配置，创建 graph dir，写入 manifest、`intermediate/stage1-input-cache.json`、chunk ledger、chunk text、agent task packets、`intermediate/agent-dispatch-plan.json` 和 pending ledger/状态。dispatch plan 包含 `execution_batches`；该命令成功时返回 `status: prepared`，并在 `cache.template_requirements`、`cache.source_flow` 中报告 `reused`、`refreshed` 或 `partial_refreshed`。
2. 如果 `cache.template_requirements` 不是 `reused`，Codex 主 agent 循环调用 `next-agent-batches --phase template_requirements`，按 `agent_policy.max_parallel` 并行调度多个 template requirements agents；默认 role 是 `template-requirements-analysis-agent`，每个 agent 负责 1-5 个发生变化或新增的模板，在 `ingest-stage1` 前输出到 `intermediate/template-requirements-parts/batch-*.json`。如果模板只发生删除，`prepare-stage1` 会返回 `next_action: ingest_template_requirements`，无需派发 template requirements agent。
3. Codex 主 agent 等待所有 template requirements 分片产物后调用 `ingest-template-requirements`，只校验并汇总分片为 `requirements/template-requirements.json`，不要求 lane outputs 或 review findings 已存在。增量模式按模板文件 key 替换或追加条目，并移除已删除模板；如果既有总 JSON 缺失、损坏或包含重复模板 key，本轮只覆盖部分模板时会 fail closed。
4. Codex 主 agent 先调用 `claim-agent-batches --phase lane_extraction --limit <max_parallel_agents>` 派满首轮，再在每完成一个 batch 的全部 `expected_output_paths` 后调用 `claim-agent-batches --phase lane_extraction --limit 1` 补位。`intermediate/agent-dispatch-state.json` 记录 batch 的 `running` / `completed` 状态；claim 返回 `status`、`phase`、`claimed_count`、`in_flight_count`、`available_slots`、`pending_count`、`completed_count` 和 `batches`。当 `pending_count == 0` 且 `in_flight_count == 0` 时，主 agent 才进入 `ingest-stage1`。默认规模是 `chunks * 1`，例如 2452 chunks 只对应 2452 个 lane output JSON；多 lane 仅在 local config 显式开启时使用。
5. Codex 主 agent 调用 `ingest-stage1` 读取 graph dir 中的 template requirements 和 lane outputs。默认 `post_merge_incremental` 模式不要求 `coverage/review-findings.json`，但缺少真实 completed lane output、坏 JSON、伪造 producer 或越界路径会 fail closed。
6. Codex 主 agent 调用 `merge-stage1` 只读取通过 merge gate 的 bundles，生成 canonical `graphify-out/graph.json`、evidence index、template readiness、manifest 和 ledger。未复查但可用的结果写入 `review_status: unreviewed_usable`，不得伪装成 reviewer `passed`。可选 graphify adapter 只消费 canonical graph path 或 graph dir，用于可视化和查询增强。
7. 如果用户发现遗漏，Codex 主 agent 可按 chunk、模板、实体或时间段发起增量 review/repair。repair agent 必须先复现 reviewer probe，记录 actual 输出，再把 probe 固化成 RED 测试，完成最小修复后运行目标测试和相关回归测试。增量 lane output 使用新的 attempt，例如 `run-002.json`。
8. Codex 主 agent 调用 `validate-graph` 检查必需 Stage 1 产物、失败 ledger、graph schema、template readiness、chunk coverage、evidence references、manifest stage status、review status 和 single-writer scopes。

`build-stage1` 仍保留为兼容入口，不作为推荐入口。缺少真实 agent outputs 或 template requirements 时，不得把它的返回结果描述为 Stage 1 已成功完成；默认后置增量模式下缺少 review findings 只表示 `review_status: unreviewed_usable`。

如果当前环境没有可用 subagent runner，Codex 主 agent 必须以 `stage1_runner_unavailable` 停止，不能继续调用 ingest/merge 并宣称完成。

## 失败与复用

常见结构化失败码示例包括 `source_unreadable`、`template_requirements_missing`、`graphify_unavailable`、`graphify_failed` 和 `graphify_artifact_missing`。未在实现和测试中固定的错误类别不作为稳定失败码承诺；调用方应以当前 JSON payload 中的 `error`、`errors` 或 `status` 字段为准。

`prepare-stage1` 的输入缓存清单位于 `intermediate/stage1-input-cache.json`，记录 source path/hash/size、模板 inventory（模板名、相对模板文件、MD5、SHA-256）、chunk strategy hash 和 lane/task packet 相关配置 hash。

模板 requirements 是模板文件级增量：全部模板 MD5 未变时跳过 template requirements phase 并复用 `requirements/template-requirements.json`；部分模板变更或新增时只生成对应模板 task packet；模板删除时从总 JSON 中移除对应条目。

原文流程是整体级重建：source hash、chunk strategy 或 lane/task packet 配置未变且 chunk ledger、chunk text、lane task packets 完整时复用这些产物；source hash 变化时完整重建 chunk ledger、chunk text、lane task packets 和 lane dispatch batches，并隔离旧 lane outputs、reviewed bundles、merge queue 与 canonical graph，避免新一轮 ingest/merge 误用旧结果。

## Stage 2 Scaffold

Stage 2 当前只暴露 schema 和输出策略辅助能力，不渲染完整模板文档。抽取记录使用配置中的 `stage2_categories`，Stage 1 覆盖范围来自 `coverage/chunk-ledger.json`，未来运行产物写入 `coverage/template-run-ledger.json`、`coverage/template-evidence-usage.json` 和 `coverage/template-gap-report.md`。

默认输出策略是 draft-first：`draft` 解析到 `<graph_dir>/<stage2_output_policy.default_dir>/<template_name>.md`，不会覆盖小说目录中同名正式 Markdown。正式文档目标只能由 `backup-and-overwrite` 或经过独立 contract 的 `merge` 选择。
