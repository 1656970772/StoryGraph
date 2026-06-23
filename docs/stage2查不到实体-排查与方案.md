# StoryGraph：Stage 2 查不到丹药实体 —— 排查过程与解决方案

> 日期：2026-06-23
> 对象：凡人修仙传 StoryGraph 图谱（Stage 1 抽取 + Stage 2 模板文档生成）
> 结论一句话：**问题不是查询函数、不是图结构、不是模板规则，而是 Stage 1 抽取从未真正跑过——483 个 chunk 里 462 个（95%）走了 bulk-fallback 占位符，根本没抽实体。**

---

## 一、问题的表象

用户在开发 Stage 2 丹药分析模板流程时，发现：

- 查询函数查不到丹药实体，只能命中"某章正文覆盖片段"这种粗粒度结果
- 给查询函数加了"绕过图、扫 chunk 正文兜底"的补丁后，能搜到一些丹药段落，但仍是片段级、不是实体级
- 怀疑链条逐步升级：查询函数有 bug？→ 图结构有问题？→ 通用抽取规则覆盖不够？→ 要不要给每个模板定制实体规则？

最终陷入一套越来越复杂的设想（mention-index + 通用本体 + 字段覆盖检查 + 缺口补抽的四层架构），感觉"卡住了"。

---

## 二、排查过程（自下而上回溯数据）

之前的排查方向是"在下游打补丁"，没有回溯到数据源头。本次按数据流自底向上逐层验证：

### 第 1 层：图里到底有没有丹药实体？

直接读真实 `graphify-out/graph.json`：

- 总节点 **205**，边 170
- 节点类型分布：character 87、faction 17、location 21……**pill 类型只有 1 个**（`抽髓丸`），外加 1 个 `碧绿色液体`
- 用 筑基丹/黄龙丹/金髓丸 等去搜节点 label：命中接近 0

**初步判断**：图里确实几乎没有丹药实体。但这和"图结构有问题"是两回事——要继续往上查。

### 第 2 层：是原文没有，还是抽取漏了？

扫描 483 个 chunk 正文，统计具名丹药出现次数：

| 丹药 | 出现的 chunk 数 |
| --- | --- |
| 筑基丹 | 50 |
| 黄龙丹 | 16 |
| 金髓丸 | 12 |
| 定颜丹 | 7 |
| 炼气散 | 5 |
| 聚灵丹 | 5 |
| 养精丹 | 3 |
| 辟谷丹 | 1 |

**铁证**：丹药在正文里到处都是，但图里 pill 节点只有 1 个。→ **是抽取漏了，不是原文没有。**

### 第 3 层：抽取 agent 当时抽了什么？

读含丹药的 chunk（如 chunk-0109，筑基丹首次出现）的 lane-output：

- `extracted_nodes`：**0 个**
- 整个 chunk 啥实体都没抽出来

→ 不是"抽了人物漏了丹药"，是这个 chunk **整体空跑**。

### 第 4 层：空跑是个例还是普遍？

聚合统计全部 483 个 lane-output：

- **462 个（95%）的 `extracted_nodes` 为空**
- 只有 21 个 chunk 真正抽出了东西，全书一共才 218 个节点
- 而且这 462 个空跑的 `output_status` 全是 `completed`——被系统当成"成功"接受了

→ **整个 Stage 1 抽取几乎全军覆没。** 图里那 205 个节点全来自最前面 21 个真抽的 chunk（难怪几乎都是开头人物：韩立、他叔叔、江湖小门派……）。

### 第 5 层：为什么会空跑？是 bug 还是人为？

读空跑 lane-output 的完整内容（chunk-0109）：

```json
"model_or_agent_identity": "codex-main-agent-bulk-fallback",
"uncertainties": [{
  "code": "bulk_fallback_low_detail",
  "message": "该 chunk 由主 agent fallback 生成粗粒度覆盖输出，未做细粒度实体关系抽取。"
}]
```

每个空跑 chunk 只生成一条 `text_coverage_fragment` 占位 event + 一条 full-text evidence，`extracted_nodes` 永远是空。

在 skill 代码里搜 `bulk-fallback`：只在 `references/workflow.md` 出现，Python 代码里没有。说明 fallback 不是 Python 工具生成的，而是**主 agent 按 workflow.md 的指示手写的**。

workflow.md 第 35-36 行写得很清楚：

> "主 agent **不得**把主观补写或 bulk fallback 混同为高质量 agent 精抽…… bulk fallback **只能用于恢复 deterministic pipeline、验证 ingest/merge/validate 链路，不能替代正常分块语义抽取。**"

**真相**：之前跑 Stage 1 时，主 agent 为了"打通工具链"，对 462 个 chunk 走了 bulk-fallback——每个 chunk 只糊一条占位、没派真抽取 agent。这本来是合法的临时手段（验证管道），但它**从未被替换成真抽取**，却被当成正式结果留下来，喂给了 Stage 2。

---

## 三、根因结论

```
462/483 chunk 走 bulk-fallback 占位（root cause，没人发现）
   → 图里只有 218 个节点、几乎全是开头人物、丹药只有 1 个
   → 看到"图里没丹药"
   → 误判为"图结构有问题 / 通用规则覆盖不够"
   → 给 stage2_query 加 chunk 全文兜底补丁（治标）
   → 兜底能搜到丹药 → 看似"修好了"，但 Stage 1 仍是坏的
   → 追问"通用规则能抽到吗"
   → 推演出 mention-index + 缺口补抽 四层架构（为绕开假问题而生）
```

**架构本身是对的**（agent 抽实体 → 建图，一份通用本体服务全部 38 个模板，与 graphify 范式一致），坏的只是**这一次抽取的执行**。整晚的弯路全部建立在一个错误前提上：以为 Stage 1 数据是真的。

---

## 四、关于"38 个模板的实体规则怎么定义"

这是排查中用户最关心的设计问题。结论：

**不要为每个模板写实体规则。** 原因：

1. Stage 1 抽取时还不知道有哪些模板——它是**通用世界观抽取**，跑一次服务全部 38 个模板。给每个模板塞规则会让 prompt 爆炸，且模板增删就得重跑全书。
2. 38 个模板要的"实体"高度重合，可归并成**一张通用本体（ontology）**，约 15-22 类 node_type：

| node_type | 覆盖的模板 |
| --- | --- |
| character | NPC、人物关系、角色修炼历程、AI行为… |
| faction / facility | 势力设定、宗门任务、建筑设施… |
| location / secret_realm | 秘境遗迹、坊市… |
| cultivation_method / technique | 功法术法神通、境界提升、修炼流派… |
| pill / medicine | 丹药分析、炼丹师… |
| material / formula | 材料分析、物资产出… |
| artifact / weapon / tool | 法宝分析、武器分析、炼器师… |
| formation / inscription | 阵法师、符师… |
| beast | 妖兽分析、妖兽与修士关系… |
| event / conflict / opportunity / rule | 冲突事件、因果链、动态事件… |

**正确分工**：
- Stage 1：按通用本体抽实体 + 关系 + evidence，不绑定任何模板
- Stage 2：每个模板只说"我要 pill 类节点 + 这 9 个字段"，查图 + 筛选 + 渲染

---

## 五、关于别名 / 法宝怪名能否抽到

排查中确认的三件事（影响方案）：

1. **名字本身（哪怕"饲灵丸""青竹蜂云剑"这种怪名）能抽到** —— 靠 LLM 语义理解，不是关键词匹配；不需要预先知道词表。前提仍是该 chunk 真的被抽取。
2. **跨 chunk 别名归一是当前架构短板** —— `canonical_writer.py` 的 merge **只按 ID 精确去重**（ID = 哈希(node_type + 名字)）。所以"小绿瓶"和"掌天瓶"若名字不同，merge 不会合并，会变成两个节点。全项目**没有任何别名/模糊归一逻辑**。
3. **`aliases` 字段在 merge 里被丢** —— 抽取 agent 会写 aliases，但 `graph_schema.py` / `lane_outputs.py` 都不把它列为字段，merge 时也只合并 provenance，其他字段只保留第一次出现的。

---

## 六、解决方案

### 已完成

**强化 Stage 1 抽取规则**（`references/stage1-extraction-agent-quality-rules.md`，新增 3 条规则）：

- **Rule 8 统一 node_type 本体**：22 类词表，禁止自由发明类型，一份服务全部 38 个模板
- **Rule 9 具名物品必抽**：丹药/法宝/材料/功法/阵法/符箓只要有名字就必抽，信息不全也不跳过（抵消旧规则偏"防过度抽取"的保守性格）
- **Rule 10 称呼归一**：同 chunk 多称呼收敛到一个节点（label + aliases），但禁止把"金髓丸/金髓液"错并
- 自检清单（Rule 11）补 3 条对应检查项

注：这步**只改抽取规则文件，不动任何 Codex 流程文本**，Codex 与 Claude Code 双环境兼容。

### 待执行（核心修复）

1. **正经重跑 Stage 1 抽取**：把 462 个 fallback chunk 换成真 agent 抽取。这是唯一总开关，跑完图节点从 205 增长到几千量级，pill 节点从 1 增长到几十个。
2. **（可选）merge 阶段保守别名合并**：仅当 A.label 出现在 B.aliases 且 node_type 相同才合并；同时把 aliases 纳入 schema 保留、同 ID 节点字段并集。解决跨 chunk 别名归一。策略已定为**保守**（只合明确别名，绝不猜测，宁留重复也不错并）。
3. **stage2_query 的 chunk-fallback 补丁**：用户决定暂时保留作兜底，但应加 warning log（走 fallback 就记一笔"图覆盖不足"），让它从"隐形拐杖"变成"暴露图质量的探针"。Stage 1 修好后应删。

### 重跑的执行方式（Claude Code 版）

由于当前用 Claude Code 而非 Codex，需要一个编排器替代 Codex subagent runner：

- skill 的 Python CLI（prepare-stage1 / claim-agent-batches / ingest-stage1 / merge-stage1 / validate-graph）**已经 orchestrator-agnostic**，无需改动
- 新增 `run_claude_code_dispatch.py`：读 dispatch plan → 主会话用 Agent 工具并发派子 agent 抽取 → 解析输出写 lane-output → 跑 ingest/merge/validate
- 派发粒度 batch:1、并发 16、全量 462 chunk

---

## 七、重要数据丢失记录

排查后期发现：**`凡人修仙传.storygraph/` 整个目录已从磁盘删除**（chunk 文件、462 个 lane-output、graph.json、Stage 2 草稿、证据索引全部丢失），且从未 commit、git reflog 也无记录，**无法恢复**。

影响：
- 好处：全量重跑从干净状态起步，无需清理旧 fallback 产物
- 代价：之前生成的 Stage 2 文档基本全没（只剩 NPC设定.md、丹药分析.md）

---

## 八、经验教训

1. **"图里实体少 / 查不到"先验证数据源头**：查 lane-outputs 的 `extracted_nodes` 是否真有内容、`model_or_agent_identity` 是不是 fallback，再往下游找。不要直接在查询/渲染层打补丁。
2. **临时降级手段（bulk-fallback）必须显式标记并最终替换**，否则会被误当成正式结果污染整条下游。
3. **通用本体 > 模板级规则**：用一份 ontology 服务多模板，而不是为每个模板定制抽取。
4. **跨 chunk 实体归一是 merge 层的责任**，不是抽取层、也不是查询层能解决的。
