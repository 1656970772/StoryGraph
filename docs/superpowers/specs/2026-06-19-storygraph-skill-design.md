# StoryGraph 小说图谱 Skill 设计

> 日期：2026-06-19
> 状态：已与用户确认总体设计，待规格审阅
> 目标位置：`E:\AI_Projects\StoryGraph`
> 安装位置：`C:\Users\Administrator\.codex\skills\storygraph`
> 参考项目：`E:\Github_Projects\graphify`

## 1. 目标

StoryGraph 的第一版目标是创建一个可安装的 Codex skill：`storygraph`。它接收小说原文路径，在小说原文所在目录创建独立图目录，为整部小说生成“模板感知”的知识图谱。

这个图谱必须服务后续 37 个世界观参考模板的抽取需求。阶段 1 暂不生成 37 份 Markdown 调研文档，但它生成的节点、边、事件、证据索引和覆盖账本，必须能支撑阶段 2 按模板生成尽可能完整的文档。

阶段 2 的目标是基于阶段 1 的全文图谱、原文和模板配置，为每个模板生成对应调研文档。每个模板都必须面向整部小说抽取，不能只处理局部章节、代表案例或主角线。

## 2. 非目标

- 不直接修改 `E:\Github_Projects\graphify` 上游仓库。
- 不在阶段 1 生成最终 37 份模板 Markdown。
- 不把 `凡人修仙传`、模板目录、图目录名、提交信息等写成全局硬编码默认值。
- 不把没有证据的推断伪装成原作事实。
- 不覆盖用户已有调研文档，除非配置明确允许。

## 3. 当前上下文与缺口

已检查：

- `E:\AI_Projects\StoryGraph` 当前为空目录，且不是 Git 仓库。
- 模板目录为 `E:\AI_Projects\CultivationWorld\docs\世界观参考\模板`。
- 该模板目录实际有 37 个 `*模板.md` 文件。
- 模板 README 清单还提到两个不存在的模板文件：
  - `出门游历流程分析模板.md`
  - `时间行动与事件耗时模板.md`
- 阶段 1 的首版范围以实际存在的 37 个模板文件为准；README 中列出但文件不存在的模板记录为 `missing_template_file` 警告，不阻塞建图。后续文件补齐后，模板扫描会自动把它们纳入下一次需求矩阵。
- 测试原文为 `E:\AI_Projects\CultivationWorld\docs\世界观参考\凡人修仙传\凡人修仙传.txt`。
- 测试原文目录已有部分 Markdown 调研文档，但没有独立图目录。

因此第一阶段需要先建立可复用的 skill 源码仓库和安装流程，再实现小说全文图谱生成。

## 4. 总体架构

采用“本地源码仓库 + 可安装个人 skill”的方案。

源码仓库：

```text
E:\AI_Projects\StoryGraph\
  skill-src\
    storygraph\
      SKILL.md
      agents\
        openai.yaml
      references\
        workflow.md
        graph-schema.md
        extraction-workflow.md
      scripts\
        storygraph.py
        sync-skill.ps1
      config\
        storygraph.default.json
  docs\
    superpowers\
      specs\
        2026-06-19-storygraph-skill-design.md
```

安装目录：

```text
C:\Users\Administrator\.codex\skills\storygraph\
```

架构分三层：

1. Skill 指令层：`SKILL.md` 保持简洁，只定义触发场景、入口流程、阶段边界和需要读取的参考文件。
2. 可配置流程层：`storygraph.default.json` 定义图目录、模板目录、graphify 来源、覆盖阈值、写入策略和子 agent 策略。
3. 脚本工具层：`storygraph.py` 负责目录解析、图状态检查、graphify 调用、manifest、coverage ledger 和产物完整性检查。

可安装 skill 的验收：

- `skill-src\storygraph\SKILL.md`、`references\`、`scripts\`、`config\` 齐全。
- `sync-skill.ps1` 可重复执行，把源码 skill 同步到 `C:\Users\Administrator\.codex\skills\storygraph`。
- 安装目录保留同样的必需文件结构。
- Codex 下一轮会话能从技能清单发现 `storygraph`。
- 同步脚本不删除安装目录中不属于本次源码同步的用户临时文件，除非显式传入清理参数。

## 5. 阶段 1：模板感知小说全文建图

阶段 1 输入是一份小说原文路径，例如：

```text
E:\AI_Projects\CultivationWorld\docs\世界观参考\凡人修仙传\凡人修仙传.txt
```

流程：

1. 解析小说目录与小说名。
2. 在小说目录下创建独立图目录，默认：

```text
E:\AI_Projects\CultivationWorld\docs\世界观参考\凡人修仙传\凡人修仙传.storygraph\
```

3. 检查图状态：
   - 图目录不存在：全量建图。
   - 图目录存在但缺关键产物：补建或重建。
   - 图完整且原文哈希未变化：复用。
   - 原文哈希变化：按配置增量更新或重建。
4. 读取 37 个模板文件，生成模板需求配置：

```text
requirements\template-requirements.json
```

5. 生成 37 模板需求矩阵。矩阵必须逐模板记录字段、表格、卡片、案例、证据和缺口判定规则，并把每项需求映射到图节点类型、事件类型、关系类型和证据类型。
6. 基于模板需求矩阵执行模板感知建图。
7. 写入图谱、manifest、evidence index 和 coverage 产物。

阶段 1 产物：

```text
凡人修仙传.storygraph\
  manifest.json
  graphify-out\
    graph.json
    GRAPH_REPORT.md
    graph.html
  requirements\
    template-requirements.json
  coverage\
    agent-run-ledger.json
    chunk-ledger.json
    evidence-index.json
    template-readiness.json
    gap-report.md
```

模板感知图至少包含以下图层：

- 实体层：人物、势力、地点、物品、功法、术法、神通、境界、灵根、体质、血脉、妖兽、职业、建筑、材料、丹药、法宝、武器。
- 事件层：相遇、战斗、交易、突破、任务、夺舍、灾变、情报传播、资源产出、资源消耗、秘境机缘、宗门活动。
- 关系层：人物关系、势力从属、敌对、师承、使用、拥有、产出、消耗、交换、传播、触发、因果、影响。
- 证据层：原文路径、章节或分块位置、短事实摘要、置信度、待核验状态。
- 叙事视角层：视角持有者、已知信息、未知信息、误判、旁观记录、有限视角日志。
- 行为决策层：角色目标、约束、资源、行动选择、行为链、后果，支撑角色 AI 行为参考模板。
- 情绪记忆层：记忆来源、执念对象、情绪触发、长期影响、行动反馈。
- 场景对话层：相遇场景、对话参与者、信息交换、态度变化、后续影响。
- 时间因果层：时间点、耗时、机会窗口、长程因果、前置条件、延迟后果。
- 模板索引层：节点和边标注 `supports_templates`，说明可服务哪些模板。

37 模板需求矩阵规则：

- 每个实际存在的 `*模板.md` 文件必须在矩阵中有独立记录，不能只用大类概括。
- 每条模板记录必须包含该模板的字段、表格、卡片、案例和证据要求。
- `有限视角与叙事日志` 必须映射到叙事视角层和证据层。
- `角色AI行为参考` 必须映射到行为决策层、资源约束和行动后果。
- `记忆情绪与执念` 必须映射到情绪记忆层和长期影响关系。
- `相遇剧情与对话设计` 必须映射到场景对话层、人物态度变化和信息交换。
- `动态事件与机会点` 必须映射到机会窗口、触发条件和后续影响。
- `事件因果链（长程因果图）` 必须映射到时间因果层、前置条件和延迟后果。

阶段 1 验收标准：

- 小说目录下生成独立 `.storygraph` 图目录。
- `graphify-out/graph.json` 可被查询。
- `manifest.json` 能追溯原文路径、哈希、配置版本和 graphify 来源。
- `chunk-ledger.json` 能证明全文被分块扫描。
- `evidence-index.json` 能把图节点、边、事件追溯到原文分块和短事实摘要。
- `template-readiness.json` 覆盖 37 个模板，说明每个模板的数据准备情况。
- 图内容能支撑 37 个模板后续抽取，而不是通用概念图。每个模板需求项必须被标记为 `covered`、`needs_review` 或 `not_found_in_source`，不得缺项。
- 重复执行不会无意义重建。

阶段 1 验证矩阵：

| 检查项 | 通过标准 |
|--------|----------|
| skill 安装结构 | 安装目录存在 `SKILL.md`、`references/`、`scripts/`、`config/` |
| 模板发现 | 实际存在的 `*模板.md` 数量为 37，README 缺失模板只记警告 |
| 原文分块 | `chunk-ledger.json` 覆盖原文全文范围，且无未处理分块 |
| 图 schema | `graphify-out/graph.json` 通过 StoryGraph canonical graph schema 校验 |
| 证据链接 | 每个模板感知节点、边或事件至少能关联 evidence，或标记为 `needs_review` |
| 模板 readiness | 37 个模板都有 `requirement_statuses`，每项状态非空 |
| 幂等执行 | 原文哈希不变时重复运行不重建 canonical graph |
| 原文变化 | 原文哈希变化时 manifest 标记需要增量更新或重建 |
| graphify 失败 | 失败写入 ledger，阶段状态不得标为通过 |

## 6. 阶段 2：模板级全文抽取

阶段 2 输入是阶段 1 生成的 `.storygraph` 图目录，以及模板目录。

流程：

1. 读取图、manifest、模板需求、全文分块账本和阶段 1 证据索引。
2. 为每个模板创建独立抽取任务。
3. 每个模板任务从图中取候选节点、边、事件和证据，再必要时回查原文。
4. 先写结构化抽取结果：

```text
extractions\<模板名>.json
```

5. 再按模板结构生成 Markdown 草稿或正式文档。
6. 对每个模板做缺口复核。
7. 覆盖不足时补抽、合并、再审查。

阶段 2 产物：

```text
凡人修仙传.storygraph\
  extractions\
    法宝分析.json
    ...
  drafts\
    法宝分析.md
    ...
  coverage\
    agent-run-ledger.json
    template-gap-report.md
    template-run-ledger.json
    template-evidence-usage.json
```

阶段 2 验收标准：

- 37 个模板都有抽取任务记录。
- 每份模板文档都以整部小说为抽取范围。
- 每个模板字段、表格、卡片或案例都有响应。
- 有证据的内容写“原作事实”并附证据。
- 推断内容标为“我的判断”。
- 证据不足内容标为“待核验”。
- 原作明显没有的类型写“未见可靠证据”。
- 输出 Markdown 默认使用中文标题、中文正文和中文字段名，除非用户或项目规范另行指定。
- 已有文档不会被意外覆盖。

阶段 2 验证矩阵：

| 检查项 | 通过标准 |
|--------|----------|
| 抽取任务数 | 37 个模板都有 `extractions/<模板名>.json` 或失败记录 |
| 抽取 schema | 每个 extraction JSON 通过 Stage 2 extraction schema 校验 |
| 全文范围 | 每个模板记录引用阶段 1 chunk ledger，并说明覆盖范围 |
| 字段履约 | 字段、表格、卡片、案例都有 `fulfilled`、`needs_review` 或 `not_found_in_source` 状态 |
| 证据引用 | 原作事实必须引用 `evidence_id` 或原文位置 |
| 中文输出 | Markdown 标题、字段和正文默认中文 |
| 不覆盖用户文档 | 默认写入 `drafts/`，正式写入前检查 overwrite policy |
| 缺口报告 | 覆盖不足模板进入 `template-gap-report.md` |

## 7. 动态子 Agent 调度

主 agent 负责总控：任务契约、配置、写入范围、验收、缺口复核和最终汇报。子 agent 可动态参与生产、审查和修复。

阶段 1 可用子 agent：

- 模板需求分析 agent：读取模板并提炼实体、事件、关系、证据字段。
- 图抽取 agent：按小说分块抽取节点、边、事件和证据。
- 合并去重 agent：处理同名、别名、阶段称谓和重复节点。
- 覆盖审查 agent：检查 37 个模板的数据需求是否都有候选支撑。
- 质量审查 agent：检查图产物、manifest 和 coverage ledger 是否完整。

阶段 2 可用子 agent：

- 模板专题 agent：负责一个或一组模板的结构化抽取。
- 证据复核 agent：检查事实、判断和待核验标注。
- 遗漏审查 agent：检查图中高相关候选是否漏进文档。
- 合并修订 agent：把补抽结果合并回 JSON 和 Markdown。
- 最终审查 agent：检查 37 个模板文档整体一致性和覆盖性。

调度规则：

- 可并行：不同章节分块、不同模板、只读审查、互不冲突的结构化抽取。
- 不并行：多个 agent 同时写同一个 manifest、同一个模板文档、同一个合并索引。
- 每个 agent 必须返回处理范围、产物路径、覆盖情况、疑点和失败片段。
- Spec Review 先检查是否满足用户目标和模板要求。
- Quality Review 再检查证据、去重、结构、维护性和风险。
- StoryGraph 执行流程中的 reviewer 发现必修问题后，派 fixer 修复并复审；这条规则不要求只读审查任务自行修改文件。

子 agent 运行记录写入 `coverage/agent-run-ledger.json`，每条记录至少包含：

- run_id
- agent_role
- stage
- assigned_chunk_ids
- assigned_template_names
- input_paths
- output_paths
- write_scope
- status
- errors
- merge_owner
- reviewer_status

## 8. 配置设计

所有可变信息默认走配置。

首版配置文件：

```text
skill-src\storygraph\config\storygraph.default.json
```

核心配置项：

```json
{
  "graph_dir_suffix": ".storygraph",
  "paths": {
    "template_dir": null,
    "graphify_repo": null,
    "project_override_file": "storygraph.local.json"
  },
  "supported_source_exts": [".txt", ".md"],
  "output_language": "zh-CN",
  "template_discovery": {
    "glob": "*模板.md",
    "exclude_files": ["README.md"],
    "readme_index_file": "README.md",
    "readme_missing_policy": "warn",
    "require_all_templates_scope": "existing_template_files"
  },
  "stages": {
    "build_template_aware_graph": true,
    "extract_template_documents": false
  },
  "graphify_adapter": {
    "mode": "local-repo-or-cli",
    "canonical_graph_policy": "merge-template-aware-supplements"
  },
  "supplemental_graph_policy": {
    "write_to_canonical_graph": true,
    "sidecar_dir": "template-graph",
    "fail_stage_if_canonical_merge_fails": true
  },
  "chunk_strategy": {
    "mode": "chapter-aware",
    "max_chars": 20000,
    "overlap_chars": 1200
  },
  "template_requirements_strategy": {
    "mode": "auto-from-templates",
    "allow_manual_overrides": true
  },
  "overwrite_policy": "draft",
  "agent_policy": {
    "enabled": true,
    "max_parallel": 6,
    "write_conflict_policy": "single-writer"
  },
  "coverage_thresholds": {
    "require_all_templates": true,
    "require_all_chunks_scanned": true,
    "readiness_warning_threshold": 0.8,
    "block_on_missing_requirement_mapping": true
  }
}
```

这些值是可移植默认配置，不写入本机绝对路径。本机路径写入不提交的 `storygraph.local.json` 或命令参数，例如模板目录和 graphify 仓库位置。`require_all_templates_scope` 表示“全部模板”以实际存在的模板文件为准；README 索引缺文件按 `readme_missing_policy` 记警告。`readiness_warning_threshold` 只用于提示薄弱模板；阶段 1 的硬性验收是 37 个模板均有需求矩阵、全文分块均被扫描、每个需求项都有覆盖状态。

## 9. 数据契约

`manifest.json` 应记录：

- source_path
- source_hash
- source_size
- novel_name
- graph_dir
- config_hash
- graphify_repo
- graphify_version_or_commit
- created_at
- updated_at
- stage_status

`graphify-out/graph.json` 是阶段 1 的 canonical graph。StoryGraph 允许在 graphify 原字段基础上增加兼容属性，但不得破坏 graphify 查询。

canonical graph 顶层应包含：

- schema_version
- graphify_schema_version
- storygraph_schema_version
- nodes
- edges
- events
- hyperedges
- metadata

节点字段至少包含：

- id
- label
- node_type
- source_file
- source_location
- evidence_ids
- supports_templates
- confidence
- verification_status

边字段至少包含：

- source
- target
- relation
- edge_type
- source_file
- evidence_ids
- supports_templates
- confidence
- confidence_score
- verification_status

事件字段至少包含：

- id
- label
- event_type
- participants
- locations
- source_file
- source_range
- evidence_ids
- causes
- effects
- supports_templates
- confidence
- verification_status

稳定 ID 规则：

- 节点 ID 用小说名、实体规范名和类型生成，避免同名跨类型冲突。
- 事件 ID 用小说名、事件类型、主参与者、原文范围哈希生成。
- evidence ID 用小说名、chunk ID 和原文范围生成。
- 同一原文、同一配置、同一 graphify 版本重复运行时 ID 必须稳定。

`supports_templates` 统一为对象数组：

```json
[
  {
    "template_name": "法宝分析",
    "requirement_id": "法宝分析.required_cards.法宝卡片",
    "status": "covered"
  }
]
```

状态枚举：

- requirement status: `covered`、`needs_review`、`not_found_in_source`
- verification status: `verified`、`needs_review`、`rejected`
- confidence: `EXTRACTED`、`INFERRED`、`AMBIGUOUS`

Graphify 兼容边界：

- graphify 原有 `nodes`、`edges`、`hyperedges` 字段保留。
- StoryGraph 扩展字段作为节点/边属性写入，不改变 graphify 必需字段。
- `events` 可作为顶层扩展，同时关键事件也以事件节点形式进入 `nodes`，保证 graphify 查询可触达。
- sidecar 只保存审计信息；阶段 1 通过前，模板感知节点、边和事件必须合入 canonical graph。

`template-requirements.json` 应记录：

- template_name
- template_file
- template_file_hash
- template_status
- output_language
- required_sections
- required_fields
- required_tables
- required_cards
- required_case_patterns
- required_entity_types
- required_event_types
- required_relation_types
- required_evidence_fields
- graph_node_mapping
- graph_event_mapping
- graph_relation_mapping
- output_sections
- coverage_rules
- gap_rules

`chunk-ledger.json` 应记录：

- chunk_id
- source_range
- chapter_hint
- hash
- scanned_at
- extraction_status
- failed_reason
- retry_count

`evidence-index.json` 应记录：

- evidence_id
- source_path
- chunk_id
- source_range
- chapter_hint
- fact_summary
- linked_node_ids
- linked_edge_ids
- linked_event_ids
- supports_templates
- confidence
- verification_status

`template-readiness.json` 应记录：

- template_name
- readiness_score
- supporting_node_count
- supporting_edge_count
- supporting_event_count
- evidence_count
- missing_requirement_types
- requirement_statuses
- notes

`extractions/<模板名>.json` 应记录：

- template_name
- template_file
- source_graph
- source_novel
- output_language
- coverage_scope
- fulfilled_sections
- fulfilled_fields
- fulfilled_tables
- fulfilled_cards
- fulfilled_cases
- facts
- judgments
- pending_verifications
- not_found_items
- evidence_citations
- gap_items
- render_target
- overwrite_policy

履约记录字段：

- requirement_id
- requirement_kind
- status
- linked_node_ids
- linked_edge_ids
- linked_event_ids
- evidence_ids
- notes

事实与判断字段：

- content
- category: `原作事实`、`我的判断`、`待核验`、`未见可靠证据`
- evidence_ids
- source_locations
- confidence

Markdown 证据引用规则：

- 原作事实必须引用 `evidence_id` 或原文位置。
- 我的判断必须说明依据，不能伪装成原作事实。
- 待核验必须说明缺什么证据。
- 未见可靠证据必须说明检索范围来自全文图或原文分块账本。

`template-evidence-usage.json` 应记录每份 Markdown 使用了哪些 `evidence_id`，用于反查证据遗漏和过度引用。

## 10. Graphify 复用策略

StoryGraph 不 fork graphify，不修改其源码。

首版优先通过本地覆盖配置指向的 graphify 仓库调用其 CLI 或 Python 包能力；当前测试环境的覆盖值是 `E:\Github_Projects\graphify`。StoryGraph 在外层补充：

- 模板需求提炼。
- 小说领域 schema。
- 图目录 manifest。
- 覆盖账本。
- 模板 readiness 和 gap report。
- 阶段 2 的模板抽取与文档生成。

如果 graphify 原生语义抽取无法满足 37 模板需求，StoryGraph 通过自己的模板感知抽取层补充节点、边、事件和证据索引。补充结果必须在阶段 1 合并进 canonical `graphify-out/graph.json`，让后续查询能看到完整模板支撑数据；旁路 JSON 只作为审计和调试 sidecar。如果 canonical 合并失败，阶段 1 不得标记为通过。

## 11. 错误处理与阻塞

必须显式记录而不是静默跳过：

- 模板文件缺失。
- 原文无法读取。
- 原文编码异常。
- graphify 不可用。
- 图产物缺失。
- 某分块抽取失败。
- 某模板 readiness 低于阈值。
- 某模板没有可靠证据。
- 子 agent 输出 JSON 无法解析。

失败记录写入对应 coverage 或 run ledger。只有关键产物缺失、原文不可读、graphify 不可用、配置无效时才阻塞整个阶段。

## 12. 通用架构、设计模式与配置化检查

通用架构：

- Skill 指令层、配置层、脚本工具层分离。
- 阶段 1 与阶段 2 分离。
- graphify 复用层与 StoryGraph 小说领域层分离。
- 图谱产物与模板文档产物分离。

设计模式适配：

- Orchestrator 模式：主 agent 负责契约、调度和验收。
- Pipeline 模式：detect、requirements、graph、coverage、extract、render、review 分阶段。
- Adapter 模式：对 graphify CLI/Python 包做本地适配。
- Strategy 模式：分块策略、覆盖策略、覆盖写入策略、子 agent 策略可配置。
- Single-writer 规则：避免多个 agent 同时写同一关键文件。

配置化覆盖范围：

- 图目录命名。
- 模板目录。
- graphify 来源。
- 支持原文格式。
- 分块策略。
- 模板需求提炼策略。
- 覆盖阈值。
- 写入策略。
- 子 agent 并发与写入边界。
- 阶段开关。

本设计没有把模板类型、小说路径、测试作品、输出策略写死在代码中；模板清单来自模板目录扫描和配置。

## 13. 实施顺序

1. 初始化 `StoryGraph` Git 仓库。
2. 创建 skill 源码结构。
3. 创建 `storygraph.default.json`。
4. 创建 `SKILL.md` 和必要 reference。
5. 创建同步安装脚本。
6. 验证同步安装后 Codex skill 目录结构完整。
7. 创建阶段 1 脚本骨架：解析原文路径、创建图目录、写 manifest。
8. 接入本地 graphify。
9. 生成模板需求配置和 37 模板需求矩阵。
10. 生成阶段 1 coverage ledger、evidence index 和 readiness。
11. 用 `凡人修仙传.txt` 做阶段 1 验证。
12. 再进入阶段 2 的结构化抽取和模板 Markdown 生成。

## 14. 用户审阅点

进入实施计划前，请重点确认：

- `.storygraph` 图目录命名是否接受。
- 阶段 1 只建模板感知图、不生成最终模板文档是否接受。
- 阶段 2 默认先写 `drafts/`，不覆盖既有 Markdown 是否接受。
- 首版按实际存在的 37 个模板执行；README 提到但文件缺失的两个模板只记录警告，不阻塞阶段 1。
