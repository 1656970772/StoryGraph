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

架构分四层：

1. Skill 指令层：`SKILL.md` 保持简洁，只定义触发场景、入口流程、阶段边界和需要读取的参考文件。
2. Codex 编排层：Codex 主 agent 读取配置、生成任务包、调度模板分析 agent、chunk-lane 抽取 agent、reviewer 和 repair agent，并负责阶段验收。
3. 可配置流程层：`storygraph.default.json` 定义图目录、模板目录、graphify 来源、分块策略、要素泳道、并发、重试、审查和写入策略。
4. Python 确定性工具层：`storygraph.py` 只负责目录解析、原文分块、任务包生成、schema 校验、归一化、去重、汇总整理、写盘、ledger、manifest、graph merge、graphify adapter 调用和产物完整性检查，不负责用规则替代 Codex agent 的语义抽取。

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

核心原则：

- Stage 1 的核心生产者是 Codex 主 agent 和子 agent。Python 不做纯规则语义抽取，不把模板感知建图退化成脚本流程。
- Python 是 deterministic tool layer：负责分块、任务包生成、schema 校验、归一化、去重、汇总、写盘、ledger、manifest 和 graph merge。
- 每个小说 chunk 不交给一个 agent 一次性抽取全部要素，而是按配置拆成多个 element lanes，由不同 agent 分别抽取。
- 同一 chunk 的多个 lane agent 可以并行；Python 等待本 chunk 或本批次 lane outputs 完成后，再做结构化校验、归一化、去重，并合并为 chunk extraction bundle。
- chunk 数、chunk 大小、重叠、最大并行、批次大小、lane 列表、重试与 repair 策略均来自配置。默认配置可以给出约 1000 个 chunk 的目标值，或基于 `target_count` 与 `max_chars` 自适应；效果不好时优先调小 chunk 或调小 batch，而不是写死逻辑。

流程：

1. Codex 主 agent 读取 `SKILL.md`、workflow、默认配置和本地 override，确认 Stage 1 目标、写入范围和 graphify 可用性。
2. Python 解析小说目录与小说名。
3. Python 在小说目录下创建独立图目录，默认：

```text
E:\AI_Projects\CultivationWorld\docs\世界观参考\凡人修仙传\凡人修仙传.storygraph\
```

4. Python 检查图状态：
   - 图目录不存在：全量建图。
   - 图目录存在但缺关键产物：补建或重建。
   - 图完整且原文哈希未变化：复用。
   - 原文哈希变化：按配置增量更新或重建。
5. Python 按配置生成全文 chunk ledger 和 agent task packets。默认策略可以配置为目标约 1000 个 chunk，也可以按 `target_count`、`max_chars`、`overlap_chars`、章节边界和最大批次自适应。
6. Codex 主 agent 调度模板需求分析 agent 读取 37 个模板文件。模板需求分析 agent 提炼字段、表格、卡片、案例、证据要求、图节点映射、事件映射、关系映射和 readiness 规则；Python 只校验 schema、归一化 ID 并落盘：

```text
requirements\template-requirements.json
```

7. 生成 37 模板需求矩阵。矩阵必须逐模板记录字段、表格、卡片、案例、证据和缺口判定规则，并把每项需求映射到图节点类型、事件类型、关系类型和证据类型。
8. Codex 主 agent 按 batch 调度 chunk-lane 抽取。每个 chunk 拆成多个 element lanes，例如：
   - 实体 / 道具 / 资源 lane。
   - 人物关系 lane。
   - 事件因果 lane。
   - 视角信息 lane。
   - 行为决策 lane。
   - 情绪记忆 lane。
   - 场景对话 lane。
   - 时间 / 机会窗口 lane。
   - 模板索引 lane。
9. 同一 chunk 内的 lane agent 按 `agent_orchestration.max_parallel_lanes_per_chunk` 和 `agent_orchestration.max_parallel_agents` 并行。每个 lane agent 只产出自己泳道的结构化 JSON、证据引用和不确定项。
10. Python 等待本 chunk 或本 batch 的 lane outputs，执行 schema 校验、字段规范化、稳定 ID 预生成、证据范围检查、重复项整理和冲突标记，生成：

```text
intermediate\chunks\<chunk_id>\chunk-extraction-bundle.json
```

11. Codex 主 agent 调度审查 agent：
   - chunk-lane reviewer：检查单个 lane 输出是否遵守 lane contract。
   - chunk coverage reviewer：检查 chunk 的必要 lanes 是否齐全，是否有结构化失败记录。
   - global merge reviewer：检查跨 chunk 合并、别名、同名异物和长程因果。
   - template readiness reviewer：检查 37 模板需求项是否有候选支撑或明确缺口。
   - quality reviewer：检查 manifest、ledger、schema、证据链和 graph merge 是否一致。
12. reviewer 发现问题后，主 agent 必须开启新的 repair/extraction agent，并把 reviewer 的 probe、输入样本、实际输出、期望输出和失败路径交给 repair agent；不得让同一个旧 agent 连续修同类问题。
13. Python 将已审查通过的 chunk extraction bundles 放入 merge queue，做确定性归一化、去重、稳定 ID、冲突保留和 canonical graph merge。
14. Python 写入图谱、manifest、evidence index、agent-run-ledger、review findings、template readiness 和 coverage 产物。

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
    review-findings.json
    template-readiness.json
    gap-report.md
  intermediate\
    task-packets\
    lane-outputs\
    chunks\
    merge-queue.json
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

全量语料与模板验收约束：

- 本次 Stage 1 开发和最终验收必须使用《凡人修仙传》的完整原文：`E:\AI_Projects\CultivationWorld\docs\世界观参考\凡人修仙传\凡人修仙传.txt`。
- 本次 Stage 1 开发和最终验收必须使用完整模板目录：`E:\AI_Projects\CultivationWorld\docs\世界观参考\模板`。
- 所有实际存在的模板都要被处理，并进入最终结果覆盖范围；不能只处理一个模板或几个代表模板。
- 中间调试可以临时只跑一个模板，也可以截取“第几章第几段”、单个 chunk 或一批分块内容做小范围验证；这些只算诊断手段，不能替代最终验收。
- 最终交付必须基于全文，最终结果必须包含全部模板。这是硬性要求，不允许用 `mini_novel`、局部章节、单模板结果冒充完成。
- 不要求中间执行时间长短，但必须完整、准确、按 agent-driven 流程执行；不能为了省时间跳过 agent 产物、review、repair 或全量覆盖校验。
- 不允许偷懒用局部样例代替最终交付。

阶段 1 验收标准：

- 小说目录下生成独立 `.storygraph` 图目录。
- `graphify-out/graph.json` 可被查询，且 canonical graph 来自已审查通过的 agent outputs，而不是 Python 规则抽取的伪结果。
- `manifest.json` 能追溯原文路径、哈希、配置版本和 graphify 来源。
- `chunk-ledger.json` 能证明全文被分块扫描，并记录每个 chunk 的必要 lane 完成状态或结构化失败状态。
- 每个 chunk 至少有配置要求的必要 lane outputs，或有明确 `structured_failure` 记录、失败原因、attempt 和 reviewer_status。
- 每个 lane output 均由真实 Codex agent 产出，并能在 `agent-run-ledger.json` 中追溯 `chunk_id`、`lane_id`、`agent_role`、输入任务包、输出路径、状态和 attempt。
- `evidence-index.json` 能把图节点、边、事件追溯到原文分块和短事实摘要。
- `template-readiness.json` 覆盖 37 个模板，说明每个模板的数据准备情况。
- 图内容能支撑 37 个模板后续抽取，而不是通用概念图。每个模板需求项必须被标记为 `covered`、`needs_review` 或 `not_found_in_source`，不得缺项。
- 模板需求矩阵由模板需求分析 agent 产出，Python 只做校验和落盘。
- review/fix loop 有证据：`review-findings.json` 记录 reviewer 发现、probe 或样本、实际输出、期望输出、repair_of、修复 attempt 和复审状态。
- Python 工具层只做分块、任务包、校验、整理、写盘、ledger、manifest 和 merge；不得把语义抽取逻辑硬编码到 Python 规则中。
- 重复执行不会无意义重建。

阶段 1 验证矩阵：

| 检查项 | 通过标准 |
|--------|----------|
| skill 安装结构 | 安装目录存在 `SKILL.md`、`references/`、`scripts/`、`config/` |
| 模板发现 | 实际存在的 `*模板.md` 数量为 37，README 缺失模板只记警告 |
| 全量验收语料 | 最终验收使用 `E:\AI_Projects\CultivationWorld\docs\世界观参考\凡人修仙传\凡人修仙传.txt` 全文和 `E:\AI_Projects\CultivationWorld\docs\世界观参考\模板` 下全部实际存在模板；小样本、单 chunk、局部章节或单模板结果只允许作为中间诊断 |
| 原文分块 | `chunk-ledger.json` 覆盖原文全文范围，且每个 chunk 有必要 lane 输出或结构化失败记录 |
| lane agent 产出 | `agent-run-ledger.json` 中每个 lane output 都有真实 `agent_role`、`chunk_id`、`lane_id`、任务包和输出路径 |
| chunk bundle | 每个通过 chunk 都有 `chunk-extraction-bundle.json`，且由已校验 lane outputs 合并而来 |
| 审查闭环 | `review-findings.json` 记录 chunk-lane、chunk coverage、global merge、template readiness 和 quality reviewer 的状态；必修问题有新的 repair/extraction agent attempt |
| 图 schema | `graphify-out/graph.json` 通过 StoryGraph canonical graph schema 校验 |
| 证据链接 | 每个模板感知节点、边或事件至少能关联 evidence，或标记为 `needs_review` |
| 模板 readiness | 37 个模板都有 `requirement_statuses`，每项状态非空 |
| Python 职责边界 | Python 产物可证明只做 deterministic tool layer；语义抽取产物来自 agent lane outputs |
| 幂等执行 | 原文哈希不变时重复运行不重建 canonical graph |
| 原文变化 | 原文哈希变化时 manifest 标记需要增量更新或重建 |
| graphify adapter 失败 | 按 `graphify_adapter.failure_policy` 写入 ledger：默认记录为 `degraded`，可配置为 `blocking`；不得伪装成 agent 抽取完成，agent outputs 与 StoryGraph canonical graph 可按配置继续生成 |

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

主 agent 负责总控：任务契约、配置、写入范围、任务包、并发批次、验收、缺口复核和最终汇报。子 agent 是 Stage 1 语义抽取和审查的核心生产者；Python 工具只提供确定性输入、校验和落盘能力。

阶段 1 可用子 agent：

- 模板需求分析 agent：读取模板并提炼字段、表格、卡片、案例、证据要求、图映射和 readiness 规则。
- chunk-lane 抽取 agent：按 `chunk_id + lane_id` 领取任务包，只抽取对应要素泳道的数据和证据。
- 实体 / 道具 / 资源 lane agent：抽取人物、势力、地点、物品、功法、材料、丹药、法宝、资源生产与消耗。
- 人物关系 lane agent：抽取师承、从属、敌对、盟友、交易、交换、传播和关系变化。
- 事件因果 lane agent：抽取事件、前置条件、触发、后果、延迟影响和长程因果。
- 视角信息 lane agent：抽取视角持有者、已知信息、未知信息、误判和旁观记录。
- 行为决策 lane agent：抽取角色目标、约束、资源、行动选择、行为链和后果。
- 情绪记忆 lane agent：抽取记忆来源、执念对象、情绪触发、长期影响和行动反馈。
- 场景对话 lane agent：抽取相遇场景、对话参与者、信息交换、态度变化和后续影响。
- 时间 / 机会窗口 lane agent：抽取时间点、耗时、机会窗口、触发条件和截止条件。
- 模板索引 lane agent：把 chunk 内候选证据映射到具体模板和 requirement_id。
- chunk-lane reviewer：检查 lane 输出是否符合 lane schema、证据范围和职责边界。
- chunk coverage reviewer：检查一个 chunk 的必要 lanes 是否齐全，失败是否结构化。
- global merge reviewer：检查跨 chunk 合并、别名、重复、同名异物和长程因果合并风险。
- template readiness reviewer：检查 37 模板需求是否有候选支撑、缺口状态和证据链。
- quality reviewer：检查 graph、manifest、ledger、schema、write scope 和幂等性。
- repair/extraction agent：只处理 reviewer 指定的失败范围，每轮修复都启动新的 agent。

阶段 2 可用子 agent：

- 模板专题 agent：负责一个或一组模板的结构化抽取。
- 证据复核 agent：检查事实、判断和待核验标注。
- 遗漏审查 agent：检查图中高相关候选是否漏进文档。
- 合并修订 agent：把补抽结果合并回 JSON 和 Markdown。
- 最终审查 agent：检查 37 个模板文档整体一致性和覆盖性。

调度规则：

- 可并行：同一 chunk 的不同 element lanes、不同 chunk、不同模板、只读审查、互不冲突的结构化抽取。
- 不并行：多个 agent 同时写同一个 manifest、同一个模板文档、同一个合并索引。
- 每个 chunk-lane agent 必须返回处理范围、lane_id、产物路径、覆盖情况、疑点、失败片段、证据引用和结构化输出。
- 主 agent 按 batch 调度；Python 只等待、校验和汇总，不冒充 agent role。
- Spec Review 先检查是否满足用户目标和模板要求。
- Quality Review 再检查证据、去重、结构、维护性和风险。
- StoryGraph 执行流程中的 reviewer 发现必修问题后，派新的 repair/extraction agent 修复并复审；这条规则不要求只读审查任务自行修改文件。
- 同一个旧 agent 不得连续修 reviewer 发现的问题；`repair_of` 必须指向 review finding 或失败 run。

子 agent 运行记录写入 `coverage/agent-run-ledger.json`，每条记录至少包含：

- run_id
- chunk_id
- lane_id
- agent_role
- stage
- assigned_chunk_ids
- assigned_template_names
- prompt_or_input_packet
- input_paths
- output_paths
- write_scope
- status
- errors
- merge_owner
- reviewer_status
- repair_of
- attempt

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
    "run_stage1_agent_graph_build": true,
    "extract_template_documents": false
  },
  "graphify_adapter": {
    "mode": "optional-local-repo-or-cli",
    "failure_policy": "degrade-visualization-and-query"
  },
  "agent_output_merge_policy": {
    "allowed_inputs": ["reviewed_lane_outputs", "reviewed_chunk_extraction_bundles"],
    "merge_unreviewed_outputs": false,
    "review_required": true
  },
  "canonical_graph_writer": {
    "implementation": "python-deterministic-writer",
    "allowed_inputs": ["reviewed_agent_outputs"],
    "semantic_generation": "disabled",
    "fail_stage_if_canonical_merge_fails": true
  },
  "chunk_strategy": {
    "mode": "chapter-aware",
    "target_count": 1000,
    "max_chars": 8000,
    "min_chars": 3000,
    "overlap_chars": 800,
    "adaptive_to_target_count": true,
    "shrink_chunk_on_low_quality": true
  },
  "agent_orchestration": {
    "enabled": true,
    "primary_producer": "codex-agents",
    "python_role": "deterministic-tool-layer",
    "max_parallel_agents": 8,
    "max_parallel_lanes_per_chunk": 4,
    "batch_size_chunks": 8,
    "write_conflict_policy": "single-writer",
    "require_real_agent_runs": true
  },
  "element_lanes": [
    {
      "lane_id": "entities_resources",
      "required": true,
      "agent_role": "实体道具资源抽取 agent",
      "schema": "lane-output.schema.json"
    },
    {
      "lane_id": "character_relationships",
      "required": true,
      "agent_role": "人物关系抽取 agent",
      "schema": "lane-output.schema.json"
    },
    {
      "lane_id": "event_causality",
      "required": true,
      "agent_role": "事件因果抽取 agent",
      "schema": "lane-output.schema.json"
    },
    {
      "lane_id": "perspective_information",
      "required": true,
      "agent_role": "视角信息抽取 agent",
      "schema": "lane-output.schema.json"
    },
    {
      "lane_id": "behavior_decision",
      "required": true,
      "agent_role": "行为决策抽取 agent",
      "schema": "lane-output.schema.json"
    },
    {
      "lane_id": "emotion_memory",
      "required": true,
      "agent_role": "情绪记忆抽取 agent",
      "schema": "lane-output.schema.json"
    },
    {
      "lane_id": "scene_dialogue",
      "required": true,
      "agent_role": "场景对话抽取 agent",
      "schema": "lane-output.schema.json"
    },
    {
      "lane_id": "time_opportunity",
      "required": true,
      "agent_role": "时间机会窗口抽取 agent",
      "schema": "lane-output.schema.json"
    },
    {
      "lane_id": "template_index",
      "required": true,
      "agent_role": "模板索引抽取 agent",
      "schema": "lane-output.schema.json"
    }
  ],
  "review_policy": {
    "enabled": true,
    "reviewers": [
      "chunk-lane-reviewer",
      "chunk-coverage-reviewer",
      "global-merge-reviewer",
      "template-readiness-reviewer",
      "quality-reviewer"
    ],
    "require_review_before_canonical_merge": true,
    "require_new_repair_agent": true
  },
  "retry_repair_policy": {
    "max_attempts_per_lane": 2,
    "max_repair_attempts_per_finding": 2,
    "record_probe_in_review_findings": true,
    "block_on_required_lane_failure": true
  },
  "template_requirements_strategy": {
    "mode": "auto-from-templates",
    "producer": "template-requirements-analysis-agent",
    "allow_manual_overrides": true,
    "python_validate_only": true
  },
  "overwrite_policy": "draft",
  "coverage_thresholds": {
    "require_all_templates": true,
    "require_all_chunks_scanned": true,
    "require_all_required_lanes_or_structured_failure": true,
    "require_review_findings_for_repairs": true,
    "readiness_warning_threshold": 0.8,
    "block_on_missing_requirement_mapping": true
  }
}
```

这些值是可移植默认配置，不写入本机绝对路径。本机路径写入不提交的 `storygraph.local.json` 或命令参数，例如模板目录和 graphify 仓库位置。`target_count: 1000` 和 `element_lanes` 只是默认示例，逻辑必须读取配置；不同小说、不同模板质量或抽取效果不好时，可以通过 override 调整 chunk 大小、目标 chunk 数、lane 列表、并发、batch 和 repair 策略。`require_all_templates_scope` 表示“全部模板”以实际存在的模板文件为准；README 索引缺文件按 `readme_missing_policy` 记警告。`readiness_warning_threshold` 只用于提示薄弱模板；阶段 1 的硬性验收是 37 个模板均有需求矩阵、全文分块均被扫描、每个必要 lane 有 agent 输出或结构化失败记录、每个需求项都有覆盖状态。

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
- 同一原文、同一配置、同一 agent output bundle 和同一 canonical graph writer 版本重复运行时 ID 必须稳定；graphify adapter 版本只影响可视化或查询适配元数据，不参与语义 ID 生成。

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

`intermediate/task-packets/<chunk_id>/<lane_id>.json` 应记录：

- task_packet_id
- stage
- chunk_id
- lane_id
- agent_role
- source_path
- source_range
- chapter_hint
- chunk_text_path
- relevant_template_requirements
- lane_contract
- allowed_output_schema
- required_evidence_policy
- attempt

`intermediate/lane-outputs/<chunk_id>/<lane_id>/<run_id>.json` 应记录：

- run_id
- task_packet_id
- chunk_id
- lane_id
- agent_role
- model_or_agent_identity
- extracted_nodes
- extracted_edges
- extracted_events
- extracted_evidence
- supports_templates
- uncertainties
- rejected_candidates
- structured_failures
- output_status
- produced_at

`intermediate/chunks/<chunk_id>/chunk-extraction-bundle.json` 应记录：

- chunk_id
- source_range
- lane_output_paths
- lane_statuses
- normalized_nodes
- normalized_edges
- normalized_events
- normalized_evidence
- conflicts
- duplicate_groups
- reviewer_status
- ready_for_merge

`intermediate/merge-queue.json` 应记录：

- queue_id
- source_bundle_paths
- merge_status
- merge_attempt
- merge_owner
- dependency_order
- blocked_by_findings
- canonical_graph_target
- merged_node_ids
- merged_edge_ids
- merged_event_ids

`coverage/review-findings.json` 应记录：

- finding_id
- reviewer_role
- stage
- chunk_id
- lane_id
- related_template_name
- input_paths
- probe_or_sample
- actual_output
- expected_output
- severity
- status
- repair_required
- repair_of
- repair_agent_run_id
- reviewer_status
- closed_at

`coverage/agent-run-ledger.json` 应记录真实 agent 任务，不得由 Python 伪造角色名。每条记录至少包含：

- run_id
- chunk_id
- lane_id
- agent_role
- prompt_or_input_packet
- input_paths
- output_paths
- status
- errors
- reviewer_status
- repair_of
- attempt
- started_at
- ended_at

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
- target_lane_ids
- required_lane_ids
- lane_output_paths
- lane_statuses
- structured_failure_paths
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

graphify 是可选适配层、可视化层和查询增强底座，不是 StoryGraph 的模板感知语义抽取核心。Stage 1 的智能抽取只能来自 Codex 主 agent 与 chunk-lane 子 agent；不能依赖 graphify 或 Python 规则替代模板感知抽取。

首版可以通过本地覆盖配置指向的 graphify 仓库调用其 CLI 或 Python 包能力；当前测试环境的覆盖值是 `E:\Github_Projects\graphify`。graphify 不可用时，按 `graphify_adapter.failure_policy` 决定处理方式：默认 `degrade-visualization-and-query` 只把 graphify adapter 产物、可视化和查询增强标记为 degraded，不阻塞 Stage 1 agent extraction 与 StoryGraph canonical graph 生成；只有显式配置为 `blocking` 时才阻塞阶段通过。任何策略下都不得把 graphify 缺席伪装成 agent 抽取完成。StoryGraph 在外层补充：

- Codex agent 驱动的模板需求提炼。
- 小说领域 schema。
- 图目录 manifest。
- 覆盖账本。
- 模板 readiness 和 gap report。
- 阶段 2 的模板抽取与文档生成。

StoryGraph 通过自己的 Codex agent 模板感知抽取层生成节点、边、事件和证据索引；Python 只把已审查的 lane outputs 和 chunk bundles 合并进 StoryGraph canonical graph。必需能力是将 Codex agent outputs 合并为 canonical `graphify-out/graph.json`，让后续查询能看到完整模板支撑数据；旁路 JSON 只作为审计和调试 sidecar。如果 canonical 合并失败，阶段 1 不得标记为通过。可选且可降级的是 graphify adapter 产物、可视化和查询增强；graphify adapter 不可用默认只记录 degraded，配置为 blocking 时才阻塞。

## 11. 错误处理与阻塞

必须显式记录而不是静默跳过：

- 模板文件缺失。
- 原文无法读取。
- 原文编码异常。
- graphify 不可用，阻塞或降级由 `graphify_adapter.failure_policy` 决定。
- 图产物缺失。
- 某分块抽取失败。
- 某模板 readiness 低于阈值。
- 某模板没有可靠证据。
- 子 agent 输出 JSON 无法解析。
- 某 chunk 缺少必要 lane output 且没有结构化失败记录。
- agent-run-ledger 缺少真实 `chunk_id`、`lane_id`、`agent_role`、任务包或输出路径。
- reviewer 发现必修问题但没有新的 repair/extraction agent attempt。
- Python 工具层产物无法证明语义抽取来自 agent lane outputs。

失败记录写入对应 coverage 或 run ledger。只有关键产物缺失、原文不可读、配置无效，或 `graphify_adapter.failure_policy` 配置为 `blocking` 且 graphify 不可用时，才阻塞整个阶段。默认 `degrade-visualization-and-query` 只记录 degraded，不阻塞 Stage 1 agent extraction 和 StoryGraph canonical graph 生成。

## 12. 通用架构、设计模式与配置化检查

通用架构：

- Skill 指令层、Codex 编排层、配置层、Python 确定性工具层分离。
- 阶段 1 与阶段 2 分离。
- graphify 复用层与 StoryGraph 小说领域层分离。
- 图谱产物与模板文档产物分离。
- 语义生产者与确定性整理工具分离：Stage 1 模板需求、lane outputs、review findings 均由 agent 产生，Python 只校验、整理和写盘。
- chunk、lane、bundle、merge queue、canonical graph 分层，避免把全文抽取逻辑写成一次性脚本。

设计模式适配：

- Orchestrator 模式：主 agent 负责契约、调度和验收。
- Fan-out/Fan-in 模式：chunk 拆成多个 element lanes 并行抽取，再由 Python 校验汇总为 chunk extraction bundle。
- Pipeline 模式：detect、chunk、requirements、lane extraction、review、bundle、merge、coverage、extract、render 分阶段。
- Adapter 模式：对 graphify CLI/Python 包做本地适配。
- Strategy 模式：分块策略、element lanes、批次、并发、覆盖策略、覆盖写入策略、审查策略、repair 策略可配置。
- Single-writer 规则：避免多个 agent 同时写同一关键文件。
- Review/Repair Loop：reviewer 只审查和记录 findings；必修问题由新的 repair/extraction agent 处理。

配置化覆盖范围：

- 图目录命名。
- 模板目录。
- graphify 来源。
- 支持原文格式。
- 分块策略，包括 `target_count`、`max_chars`、`min_chars`、`overlap_chars` 和自适应策略。
- 模板需求提炼策略，包括 agent producer、manual override 和 Python validate-only。
- element lane 列表、lane schema、required 标记和 agent_role。
- agent orchestration，包括最大并发、每 chunk 最大 lane 并发、batch 大小和 single-writer 策略。
- review policy，包括 reviewer 列表、merge 前审查要求和新 repair agent 要求。
- retry/repair 策略，包括每 lane attempt、每 finding repair attempt 和阻塞条件。
- 覆盖阈值。
- 写入策略。
- 子 agent 并发与写入边界。
- 阶段开关。

本设计没有把模板类型、小说路径、测试作品、输出策略、chunk 数、lane 列表、并发数或 repair 策略写死在代码中；模板清单来自模板目录扫描和配置，Stage 1 的 lane 与调度策略来自 `storygraph.default.json` 或本地 override。

## 13. 实施顺序

1. 初始化 `StoryGraph` Git 仓库。
2. 创建 skill 源码结构。
3. 创建 `storygraph.default.json`。
4. 创建 `SKILL.md` 和必要 reference。
5. 创建同步安装脚本。
6. 验证同步安装后 Codex skill 目录结构完整。
7. 创建阶段 1 Python 确定性工具骨架：解析原文路径、创建图目录、写 manifest、按配置分块、生成 task packets。
8. 定义并验证 Stage 1 数据契约：lane outputs、chunk extraction bundle、merge queue、review findings、agent-run-ledger、chunk-ledger、evidence-index 和 canonical graph schema。
9. 实现 Codex 主 agent 编排参考流程：读取配置、调度模板需求分析 agent、调度 chunk-lane extraction agents、等待 batch、触发 reviewer、派发新的 repair/extraction agent。
10. 实现模板需求分析 agent 流程，生成 37 模板需求矩阵；Python 只做 schema 校验和落盘。
11. 实现 chunk-lane task packet 生成和 lane output 校验，先用小样本验证每个必要 lane 都能由 agent 产出或结构化失败。
12. 实现 review/fix loop 记录：chunk-lane reviewer、chunk coverage reviewer、global merge reviewer、template readiness reviewer、quality reviewer 和新的 repair/extraction agent attempt。
13. 接入可选 graphify adapter，仅用于可视化和查询增强，不承担 canonical graph 输出职责，也不替代 agent 抽取。
14. 实现 StoryGraph deterministic writer：只读取已审查的 agent outputs，完成已审查 chunk bundles 的 merge queue、归一化、去重、稳定 ID、evidence index、template readiness 和 canonical graph 写入。
15. 用 `凡人修仙传.txt` 做阶段 1 验证，重点验证 chunk/lane/agent ledger、review findings、canonical graph 来源和 37 模板 readiness。
16. 再进入阶段 2 的结构化抽取和模板 Markdown 生成。

## 14. 用户审阅点

进入实施计划前，请重点确认：

- `.storygraph` 图目录命名是否接受。
- 阶段 1 只建模板感知图、不生成最终模板文档是否接受。
- 阶段 2 默认先写 `drafts/`，不覆盖既有 Markdown 是否接受。
- 首版按实际存在的 37 个模板执行；README 提到但文件缺失的两个模板只记录警告，不阻塞阶段 1。
