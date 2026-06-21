# StoryGraph 图谱 Schema

`graphify-out/graph.json` 是 Stage 1 的 canonical graph。它保留 graphify-native 顶层结构，并增加 StoryGraph 面向模板需求、证据链、review gate 和 agent provenance 的字段。

## 必需顶层字段

- `schema_version`
- `graphify_schema_version`
- `storygraph_schema_version`
- `nodes`
- `edges`
- `hyperedges`
- `events`
- `evidence_index`
- `metadata`

`metadata` 必须能说明 canonical graph 的来源：

- `semantic_generation`: 必须为 `agent-produced`，表示语义内容来自 Codex agent outputs。
- `canonical_writer_version`: 当前 canonical writer 版本。
- `source_bundle_paths`: 参与合并的 reviewed bundle 路径列表；列表项必须是非空字符串。
- `graphify_input_strategy`: graphify adapter 使用的输入策略，当前只允许 canonical graph path 或 graph dir。

## StoryGraph 条目字段

StoryGraph 创建或修改的 nodes、edges、events 和 evidence records 必须包含：

- 稳定 `id` 或 `evidence_id`。
- `source_location` 或 `source_range`，用于回到小说源文本。
- `evidence_ids`，适用于依赖证据的节点、边和事件。
- `supports_templates`，记录支撑的模板需求项和配置化 requirement status。
- `confidence`，取值来自配置化 confidence 枚举。
- `verification_status`，取值来自配置化 verification 枚举。
- `provenance`，记录该条目来自哪些已审查 agent outputs。

`provenance` 是必需对象，至少包含：

- `semantic_generation`: `agent-produced`。
- `chunk_ids`: 贡献该条目的 chunk id 列表。
- `lane_output_paths`: 贡献该条目的 lane output 路径列表。
- `conflicts`: 可选；当 canonical writer 保留同 ID 冲突时，记录冲突 chunk、lane output 和原因。

lane output 本身必须携带 `task_packet_id`、`chunk_id`、`lane_id`、`agent_role`、`model_or_agent_identity`、抽取结果和输出状态。review findings 必须携带 `reviewer_role`、`reviewer_status` 或 finding status、probe/sample、实际输出、期望输出和 repair 关联信息。只有 reviewer 状态通过配置化 review gate 后，对应内容才能进入 reviewed bundle 和 canonical merge。

## 校验规则

Graphify-native nodes、edges 和 events 在 canonical merge 前可以保留 graphify 原字段；凡是 StoryGraph 创建或修改的条目，都必须通过完整 StoryGraph validation contract。

Deep validation 要求 StoryGraph 条目使用稳定 ID 前缀、引用已知 node/evidence、非空 `supports_templates`、配置化 requirement status、配置化 confidence、配置化 verification status，并带有 source locator。缺少 source locator 会报告为 `<item>_without_source_location:<id>`。

`provenance` 校验必须失败关闭：非对象、非字符串路径、非字符串 chunk id、非法冲突结构和 metadata 来源不一致都应进入结构化错误，不得让原始解析异常泄漏到 CLI。
