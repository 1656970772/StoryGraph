
## StoryGraph 项目规则

### Stage 1 / agent JSON 编码规则

- Stage 1 及 subagent 写给 Python ingest/validator 读取的 JSON 产物必须使用 UTF-8 without BOM。
- 在 PowerShell 5.1 中不要用 `Set-Content -Encoding UTF8` 写这类 JSON；该写法会写入 UTF-8 BOM，导致 Python `json.loads(path.read_text(encoding="utf-8"))` 报 `Unexpected UTF-8 BOM`。
- 如需在 PowerShell 5.1 写 JSON，优先使用 `.NET` 无 BOM 编码写入，例如 `New-Object System.Text.UTF8Encoding($false)`，或使用项目提供的写盘脚本/工具统一输出。

### Stage 1 / agent 调度与路径规则

- 分派 Stage 1 子 agent 时，必须同时提供 graph dir、task packet、预期输出路径的绝对路径；不要只给相对路径。相对路径只用于写入 JSON 内部 provenance 和 artifact 字段。
- 主 agent 必须在所有 template requirements 分片齐全后才运行 `ingest-template-requirements`；单个分片完成时只运行分片级 contract/schema 校验，不要用全局 ingest 的 `template_requirements_part_missing` 作为失败结论。
- lane extraction 必须通过 `claim-agent-batches` 维护 dispatch state。只有当 `pending_count == 0` 且 `in_flight_count == 0`，并且全部 `expected_output_paths` 实际存在且校验通过后，才能进入 `ingest-stage1`。
- 发现子 agent 超时或未落盘时，先关闭仍在运行的旧 agent，避免晚到输出覆盖；再按相同 task packet 重派新的 repair/extraction agent。若主 agent 临时补写，必须在结果中标注为 fallback，并保留低质量/待复核说明。
- bulk fallback 只能作为打通工具链的降级手段，不得当作高质量语义抽取完成。最终汇报必须说明 fallback 数量、影响范围和 `review_status`。

### Stage 1 / schema 与验证闭环规则

- lane output 进入 `ingest-stage1` 前，必须检查 node/edge/event/evidence 的 `supports_templates`、`confidence`、`verification_status`、`source_range`、`source_location`、`evidence_ids` 和 node/event/edge 引用闭合性；不要等到 `merge-stage1` 才第一次发现 canonical graph deep validation 错误。
- `supports_templates.requirement_id` 必须来自最终 `requirements/template-requirements.json` 中真实存在的 requirements 或 summary category；如果最终 requirements 是 summary 结构，应使用 summary category id，不要留空或临时编造字段名。
- `merge-stage1` 返回 `validation_errors: []` 但带 `graphify_degraded` / `graphify_failed` 时，视为 canonical graph 已生成但可视化/adapter 降级；仍必须继续运行 `validate-graph` 判定最终 Stage 1 是否可交付。
- `validate-graph` 是最终完成声明的唯一准入门槛：必须返回 `ok: true`、`errors: []`，并额外检查 Stage 1 JSON 产物 BOM 计数为 0。
- 修复 reviewed bundles、coverage ledger、agent-run-ledger 或 task packets 后，必须重新运行 `merge-stage1` 和 `validate-graph`；不得只根据文件存在或 manifest 的 `stage1: success` 宣称完成。
