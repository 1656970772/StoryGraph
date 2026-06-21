# StoryGraph CLI

StoryGraph CLI 位于 `skill-src/storygraph/scripts/storygraph.py`。CLI 负责 deterministic tool layer：配置、路径、模板发现、Stage 1 准备、agent 产物摄入、已审查 bundle 合并、canonical graph 写盘、graphify adapter 和验证。Stage 1 的语义内容由 Codex agents 产生，不由 CLI 自动生成。

## CLI 工具层命令

这些命令主要供 Codex agent orchestrator 在 Stage 1 工作流内部调用，或用于调试确定性契约。面向使用者的入口是把 `source`、`template-dir` 和 `graph-dir` 交给 Codex，由 Codex 主 agent 调度 template requirements agent、lane extraction agents、reviewer agents 和必要的新 repair agents。

CLI 本身不是直接完成 Stage 1 的主入口；它只负责确定性的准备、摄入、合并和验证。

```powershell
python skill-src/storygraph/scripts/storygraph.py --version
python skill-src/storygraph/scripts/storygraph.py validate-skill --skill-root skill-src/storygraph
python skill-src/storygraph/scripts/storygraph.py config-check --config skill-src/storygraph/config/storygraph.default.json --local-override path/to/storygraph.local.json
python skill-src/storygraph/scripts/storygraph.py inspect-templates --template-dir path/to/templates --config skill-src/storygraph/config/storygraph.default.json --local-override path/to/storygraph.local.json
python skill-src/storygraph/scripts/storygraph.py prepare-stage1 --source path/to/novel.txt --template-dir path/to/templates --graph-dir path/to/novel.storygraph
python skill-src/storygraph/scripts/storygraph.py ingest-stage1 --graph-dir path/to/novel.storygraph
python skill-src/storygraph/scripts/storygraph.py merge-stage1 --graph-dir path/to/novel.storygraph
python skill-src/storygraph/scripts/storygraph.py validate-graph --graph-dir path/to/novel.storygraph
```

`--local-override` 是可选参数；如果显式传入但文件不存在，CLI 返回 exit code `2` 并输出结构化 JSON 错误。

## Stage 1 退出与 JSON 契约

`prepare-stage1`、`ingest-stage1`、`merge-stage1` 和 `validate-graph` 都遵循同一类 CLI 退出规则：成功返回 exit code `0`，结构化失败返回 exit code `2`，并输出结构化 JSON。JSON payload 分两类：Stage 1 动作命令（`prepare-stage1`、`ingest-stage1`、`merge-stage1`）使用 `status`、`error`、`validation_errors`、`warnings`、`next_action` 等字段表达状态和下一步动作，不承诺 `ok` 字段；`validate-graph` 使用 `ok` 和 `errors` 表达验证是否通过。

## Stage 1 agent-driven 内部流程

1. Codex 主 agent 调用 `prepare-stage1` 读取 source、template dir 和配置，创建 graph dir，写入 manifest、chunk ledger、chunk text、agent task packets 和 pending ledger/状态。该命令成功时返回 `status: prepared`，下一步动作是调度 agent task packets。
2. `template-requirements-analysis-agent` 在 `ingest-stage1` 前产出 `requirements/template-requirements.json`。缺少该文件时，`ingest-stage1` 会 fail closed，并返回 `status: failed`、`error.code: template_requirements_missing` 和对应 `validation_errors`。
3. Codex 主 agent 读取 `intermediate/task-packets/<chunk>/<lane>.json`，调度 lane extraction agents。agent 输出写入 `intermediate/lane-outputs/<chunk>/<lane>/...json`。
4. reviewer agents 审查 lane output、chunk 覆盖、全局合并、模板 readiness 和质量门禁，并把 findings 写入 `coverage/review-findings.json`。必修 finding 需要新的 repair/extraction agent 产出修复结果；repair agent 必须先复现 reviewer probe，记录 actual 输出，再把 probe 固化成 RED 测试，完成最小修复后运行目标测试和相关回归测试。
5. Codex 主 agent 调用 `ingest-stage1` 读取 graph dir 中的 lane outputs、template requirements 和 review findings，校验 agent-produced 产物、路径边界、配置枚举和 reviewer gate，只把通过审查的内容写成 `intermediate/reviewed-bundles/*.json`。成功时返回 `status: ingested`。
6. Codex 主 agent 调用 `merge-stage1` 只读取 reviewed bundles，生成 canonical `graphify-out/graph.json`、evidence index、template readiness、manifest 和 ledger。可选 graphify adapter 只消费 canonical graph path 或 graph dir，用于可视化和查询增强。成功时返回 `status: success`。
7. Codex 主 agent 调用 `validate-graph` 检查必需 Stage 1 产物、失败 ledger、graph schema、template readiness、chunk coverage、evidence references、manifest stage status、review gate 和 single-writer scopes。

`build-stage1` 仍保留为兼容入口，不作为推荐入口。缺少 reviewed agent outputs、template requirements 或 review findings 时，不得把它的返回结果描述为 Stage 1 已成功完成。

## 失败与复用

常见结构化失败码示例包括 `source_unreadable`、`template_requirements_missing`、`graphify_unavailable`、`graphify_failed` 和 `graphify_artifact_missing`。未在实现和测试中固定的错误类别不作为稳定失败码承诺；调用方应以当前 JSON payload 中的 `error`、`errors` 或 `status` 字段为准。

Stage 1 只有在 source hash、stage input hash、task packet schema hash、reviewed output manifest hash、manifest status、必需文件、deep graph validation 和 graphify adapter ledger 都匹配时才复用既有输出。source、template、config、graphify source、graphify command、chunk strategy 或 agent 输出变化会触发重建或重新合并。

## Stage 2 Scaffold

Stage 2 当前只暴露 schema 和输出策略辅助能力，不渲染完整模板文档。抽取记录使用配置中的 `stage2_categories`，Stage 1 覆盖范围来自 `coverage/chunk-ledger.json`，未来运行产物写入 `coverage/template-run-ledger.json`、`coverage/template-evidence-usage.json` 和 `coverage/template-gap-report.md`。

默认输出策略是 draft-first：`draft` 解析到 `<graph_dir>/<stage2_output_policy.default_dir>/<template_name>.md`，不会覆盖小说目录中同名正式 Markdown。正式文档目标只能由 `backup-and-overwrite` 或经过独立 contract 的 `merge` 选择。
