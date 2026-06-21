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
python skill-src/storygraph/scripts/storygraph.py next-agent-batches --graph-dir path/to/novel.storygraph --phase lane_extraction --limit 6
python skill-src/storygraph/scripts/storygraph.py ingest-stage1 --graph-dir path/to/novel.storygraph
python skill-src/storygraph/scripts/storygraph.py merge-stage1 --graph-dir path/to/novel.storygraph
python skill-src/storygraph/scripts/storygraph.py validate-graph --graph-dir path/to/novel.storygraph
```

`--local-override` 是可选参数；如果显式传入但文件不存在，CLI 返回 exit code `2` 并输出结构化 JSON 错误。

## Stage 1 退出与 JSON 契约

`prepare-stage1`、`ingest-template-requirements`、`ingest-stage1`、`merge-stage1` 和 `validate-graph` 都遵循同一类 CLI 退出规则：成功返回 exit code `0`，结构化失败返回 exit code `2`，并输出结构化 JSON。JSON payload 分两类：Stage 1 动作命令（`prepare-stage1`、`ingest-template-requirements`、`ingest-stage1`、`merge-stage1`）使用 `status`、`error`、`validation_errors`、`warnings`、`next_action` 等字段表达状态和下一步动作，不承诺 `ok` 字段；`validate-graph` 使用 `ok`、`errors`、`warnings` 和 `review_status` 表达验证与复查状态。

## Stage 1 agent-driven 内部流程

1. Codex 主 agent 调用 `prepare-stage1` 读取 source、template dir 和配置，创建 graph dir，写入 manifest、chunk ledger、chunk text、agent task packets、`intermediate/agent-dispatch-plan.json` 和 pending ledger/状态。dispatch plan 包含 `execution_batches`；该命令成功时返回 `status: prepared`，下一步动作是 `dispatch_template_requirements_agents`。
2. Codex 主 agent 循环调用 `next-agent-batches --phase template_requirements`，按 `agent_policy.max_parallel` 并行调度多个 template requirements agents；默认 role 是 `template-requirements-analysis-agent`，每个 agent 负责 1-5 个模板，在 `ingest-stage1` 前输出到 `intermediate/template-requirements-parts/batch-*.json`。
3. Codex 主 agent 等待所有 template requirements 分片产物后调用 `ingest-template-requirements`，只校验并汇总分片为 `requirements/template-requirements.json`，不要求 lane outputs 或 review findings 已存在。
4. Codex 主 agent 循环调用 `next-agent-batches --phase lane_extraction`，按默认 `comprehensive_extraction` lane 和 `agent_orchestration.lane_chunks_per_agent` 聚合的 batch 并行调度 extraction agents。默认规模是 `chunks * 1`，例如 2452 chunks 只对应 2452 个 lane output JSON；多 lane 仅在 local config 显式开启时使用。
5. Codex 主 agent 调用 `ingest-stage1` 读取 graph dir 中的 template requirements 和 lane outputs。默认 `post_merge_incremental` 模式不要求 `coverage/review-findings.json`，但缺少真实 completed lane output、坏 JSON、伪造 producer 或越界路径会 fail closed。
6. Codex 主 agent 调用 `merge-stage1` 只读取通过 merge gate 的 bundles，生成 canonical `graphify-out/graph.json`、evidence index、template readiness、manifest 和 ledger。未复查但可用的结果写入 `review_status: unreviewed_usable`，不得伪装成 reviewer `passed`。可选 graphify adapter 只消费 canonical graph path 或 graph dir，用于可视化和查询增强。
7. 如果用户发现遗漏，Codex 主 agent 可按 chunk、模板、实体或时间段发起增量 review/repair。repair agent 必须先复现 reviewer probe，记录 actual 输出，再把 probe 固化成 RED 测试，完成最小修复后运行目标测试和相关回归测试。增量 lane output 使用新的 attempt，例如 `run-002.json`。
8. Codex 主 agent 调用 `validate-graph` 检查必需 Stage 1 产物、失败 ledger、graph schema、template readiness、chunk coverage、evidence references、manifest stage status、review status 和 single-writer scopes。

`build-stage1` 仍保留为兼容入口，不作为推荐入口。缺少真实 agent outputs 或 template requirements 时，不得把它的返回结果描述为 Stage 1 已成功完成；默认后置增量模式下缺少 review findings 只表示 `review_status: unreviewed_usable`。

如果当前环境没有可用 subagent runner，Codex 主 agent 必须以 `stage1_runner_unavailable` 停止，不能继续调用 ingest/merge 并宣称完成。

## 失败与复用

常见结构化失败码示例包括 `source_unreadable`、`template_requirements_missing`、`graphify_unavailable`、`graphify_failed` 和 `graphify_artifact_missing`。未在实现和测试中固定的错误类别不作为稳定失败码承诺；调用方应以当前 JSON payload 中的 `error`、`errors` 或 `status` 字段为准。

Stage 1 只有在 source hash、stage input hash、task packet schema hash、reviewed output manifest hash、manifest status、必需文件、deep graph validation 和 graphify adapter ledger 都匹配时才复用既有输出。source、template、config、graphify source、graphify command、chunk strategy 或 agent 输出变化会触发重建或重新合并。

## Stage 2 Scaffold

Stage 2 当前只暴露 schema 和输出策略辅助能力，不渲染完整模板文档。抽取记录使用配置中的 `stage2_categories`，Stage 1 覆盖范围来自 `coverage/chunk-ledger.json`，未来运行产物写入 `coverage/template-run-ledger.json`、`coverage/template-evidence-usage.json` 和 `coverage/template-gap-report.md`。

默认输出策略是 draft-first：`draft` 解析到 `<graph_dir>/<stage2_output_policy.default_dir>/<template_name>.md`，不会覆盖小说目录中同名正式 Markdown。正式文档目标只能由 `backup-and-overwrite` 或经过独立 contract 的 `merge` 选择。
