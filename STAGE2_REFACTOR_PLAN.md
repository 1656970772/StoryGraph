# Stage 2 完全重构计划 - Graphify 查询流程集成

## 概述
将 StoryGraph Stage 2 的前两个步骤按照 Graphify 的查询流程完全重新设计，删除旧代码，实现完整的 agent-driven 流程。

**核心变化**：
- ❌ 删除：`stage2_query.py` 的旧查询逻辑（基于 evidence_index 遍历）
- ✅ 新增：Graphify 风格的 5 步查询流程（参数规范化 → 词提取 → 节点评分 → 种子选择 → 图遍历 → 文本渲染）
- ✅ 新增：完整的 Stage 2 agent 派发系统（参数查询 → 草稿生成 → 最终文档）

---

## 新文件结构

```
stage2_graph_query.py           # 新：Graphify 风格的查询引擎（第1-2步）
  ├─ normalize_query_params()        # 第1步：参数规范化
  ├─ extract_query_terms()           # 第1步：词提取（中文分词、英文分词）
  ├─ score_nodes()                   # 第2步：IDF 加权评分
  ├─ pick_seed_nodes()               # 第2步：种子选择
  ├─ traverse_graph_bfs_dfs()        # 第2步：BFS/DFS 遍历
  ├─ render_subgraph_text()          # 第2步：文本渲染
  └─ query_graph()                   # 统一入口

stage2_agent_dispatch.py        # 新：Agent 派发系统
  ├─ dispatch_query_agents()         # 第1步：派发查询 agent（参数生成）
  ├─ dispatch_draft_agents()         # 第3步：派发草稿 agent
  ├─ dispatch_final_agents()         # 第4步：派发最终文档 agent
  └─ collect_agent_results()         # 结果收集

stage2.py                       # 改造：主流程协调
  ├─ prepare_stage2()               # 不变
  ├─ run_stage2_full()              # 新：完整流程 = prepare → query → draft → final
  └─ [删除旧的 render 流程]
```

---

## 具体实现步骤

### 第1步：参数规范化 + 词提取

**输入**：来自 template 的 query_parameters
```python
{
  "template_name": "丹药分析",
  "question": "什么样的丹药能帮助修士突破?",
  "mode": "bfs",           # 或 "dfs"
  "depth": 3,
  "token_budget": 2000,
  "context_filter": ["effect", "material"],  # 可选
  "target_node_types": ["pill"],
  "include_terms": ["突破", "晋级"],
  "exclude_terms": ["副作用"],
  "limit": 20
}
```

**处理**：
1. 规范化参数（填充默认值）
2. 根据 `include_terms` + `question` 提取查询词
   - 中文：jieba 分词 + 去停词
   - 英文：按单词切分 + 过滤 ≤2 字符
3. 返回标准化参数 + 查询词列表

---

### 第2步：查询流程（5 个子步）

#### 2a. 节点评分 (`score_nodes`)
对图中所有节点评分：
- 按匹配程度：精确 > 前缀 > 子串
- 按罕见度加权：IDF 权重
- 按节点类型过滤：只评分 target_node_types 中的节点

输出：`list[(score, node_id)]`

#### 2b. 种子选择 (`pick_seed_nodes`)
从评分结果中选择最多 3 个种子：
- 取分数最高的节点
- 如果分数差 > 80%，停止
- 避免噪音节点被选中

输出：`list[node_id]`

#### 2c. 图遍历 (`traverse_graph`)
从种子节点出发，按指定深度和模式遍历：
- BFS：广度优先（默认）
- DFS：深度优先（追踪路径）
- 避免通过高度数节点（hub threshold = p99 度数）
- 如果指定 context_filter，则只保留特定边类型

输出：`(visited_nodes, edge_list)`

#### 2d. 结果过滤
根据原始参数进一步过滤：
- 应用 exclude_terms
- 应用最小匹配数
- 应用 limit

输出：`(final_nodes, final_edges)`

#### 2e. 文本渲染 (`render_subgraph_text`)
将子图渲染为可读的文本：
```
Traversal: BFS depth=3 | Start: [丹药A, 丹药B] | Context: effect,material | 42 nodes found

NODE 筑基丹 [src=凡人修仙传.txt loc=L1234 category=pill]
NODE 黄龙丹 [src=凡人修仙传.txt loc=L5678 category=pill]
...
EDGE 筑基丹 --helps_breakthrough [EXTRACTED context=effect]--> 修士
...
```

---

### 第3步：生成草稿（全 Agent 驱动）

**流程**：
1. 收集所有查询结果（第2步的输出）
2. 为每个模板派发一个 `draft-agent`
3. Draft Agent 负责：
   - 读取查询结果
   - 根据模板的字段定义提取关键信息
   - 生成草稿（带来源标注）
4. 写入 `graph_dir/drafts/<template>.draft.md`

**Prompt 示例**：
```
你是 StoryGraph 的草稿生成 agent。

查询结果：
{query_result}

模板定义：
{template_definition}

任务：
1. 基于查询结果中的节点和边，提取关键信息
2. 为每条信息标注来源（节点 ID、位置、置信度）
3. 生成结构化的草稿条目（JSON 或 Markdown）
4. 标记数据覆盖缺口

输出格式：
[
  {
    "case_id": "pill_01",
    "title": "筑基丹分析",
    "content": "...",
    "source_nodes": ["pill:zhuji_dan"],
    "source_evidence": ["evidence_id_123"],
    "coverage": "complete|partial|missing"
  },
  ...
]
```

---

### 第4步：生成最终文档（全 Agent 驱动）

**流程**：
1. 收集所有草稿（第3步的输出）
2. 为每个模板派发一个 `final-agent`
3. Final Agent 负责：
   - 读取草稿
   - 读取原始模板的结构（标题、格式）
   - 根据模板规则进行去重、归并、排序
   - 生成最终 Markdown（无来源标注，只有案例）
4. 写入 `graph_dir/generated/<template>.md`

**Prompt 示例**：
```
你是 StoryGraph 的最终文档生成 agent。

草稿内容：
{draft_content}

原始模板：
{template_markdown}

模板规则：
{template_rules}

任务：
1. 基于草稿内容和模板规则生成最终文档
2. 去重：相同的 case 只写一次
3. 归并：相似的案例合并为一条
4. 排序：按相关性或重要性排序
5. 渲染：按模板的 Markdown 结构渲染
6. 不写来源标注，只写最终案例

输出格式：Markdown 文本
```

---

### 第5步：删除老代码

**删除文件**：
- `stage2_query.py` (旧查询逻辑)
- `stage2_render.py` (旧渲染逻辑)
- `stage2_evidence.py` (旧证据索引)

**删除函数**：
- `query_stage2_cases()`
- `render_template_draft()`
- `render_template_final()`
- `_normalize_query_parameters()` (用新的替代)
- `_linked_graph_records()`
- 等等所有旧的辅助函数

**修改 stage2.py**：
- 删除旧的 `render_template_draft()` 和 `render_template_final()` 调用
- 替换为新的 agent 派发流程

---

## 新的完整流程（高层）

```python
async def run_stage2_full(graph_dir, template_dir, config):
    # 第0步：准备（不变）
    prepare_result = prepare_stage2(graph_dir, template_dir, config)
    
    # 第1-2步：查询（新 Graphify 风格）
    for template in templates:
        query_params = generate_query_params(template)
        query_result = query_graph(
            graph_dir,
            query_params,
            mode="bfs",
            depth=3
        )
        save_query_result(query_result)
    
    # 第3步：派发草稿 agents
    draft_jobs = []
    for template, query_result in zip(templates, query_results):
        job = dispatch_draft_agent(
            template=template,
            query_result=query_result,
            graph_dir=graph_dir
        )
        draft_jobs.append(job)
    
    draft_results = await gather_agent_jobs(draft_jobs)
    
    # 第4步：派发最终文档 agents
    final_jobs = []
    for template, draft in zip(templates, draft_results):
        job = dispatch_final_agent(
            template=template,
            draft=draft,
            graph_dir=graph_dir
        )
        final_jobs.append(job)
    
    final_results = await gather_agent_jobs(final_jobs)
    
    # 完成
    return {
        "status": "completed",
        "query_results": len(query_results),
        "draft_results": len(draft_results),
        "final_results": len(final_results)
    }
```

---

## 测试覆盖

新增测试：
- `test_normalize_query_params.py` — 参数规范化
- `test_extract_query_terms.py` — 中英文词提取
- `test_score_nodes.py` — IDF 评分
- `test_pick_seeds.py` — 种子选择
- `test_traverse_graph.py` — BFS/DFS 遍历
- `test_render_text.py` — 文本渲染
- `test_query_graph_integration.py` — 完整查询流程
- `test_agent_dispatch.py` — Agent 派发

删除测试：
- `test_stage2_query.py` (旧查询)
- `test_stage2_render.py` (旧渲染)

---

## 关键设计决策

1. **无兼容性**：完全替换旧逻辑，不留转接层
2. **IDF 加权**：采用 Graphify 的 IDF 权重策略
3. **Hub 避免**：p99 度数阈值，防止噪音扩散
4. **Agent 全驱动**：第3-4步完全由 agent 决策，Python 只做工具层
5. **来源标注仅在草稿**：最终文档干净，不暴露内部细节
6. **上下文过滤可选**：如果模板指定 context_filter，则自动推断

---

## 迁移时间线

1. **实现第1-2步**：`stage2_graph_query.py` + 单元测试（1-2h）
2. **实现第3-4步**：`stage2_agent_dispatch.py` + 集成测试（1-2h）
3. **集成 stage2.py**：改造主流程 + 验证（0.5h）
4. **删除旧代码**：清理 + 验证没有遗留引用（0.5h）
5. **端到端测试**：完整流程验证（1h）

总计：4-6h
