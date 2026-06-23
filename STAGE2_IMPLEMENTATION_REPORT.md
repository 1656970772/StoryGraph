# Stage 2 重构完成报告

## 实现完成

### ✅ 已完成的模块

#### 1. `stage2_graph_query.py` - Graphify 风格查询引擎
实现了完整的 5 步查询流程：

**第1步：参数规范化 + 词提取**
- `normalize_query_params()` — 规范化参数（模式、深度、预算等）
- `extract_query_terms()` — 中英文混合词提取
  - 中文：jieba 分词 + 原词精确匹配
  - 英文：单词切分 + 过滤短词（≤2字符）
  - 结果：`list[str]` 去重、小写、无重音

**第2步：查询流程**
- `score_nodes()` — IDF 加权评分
  - 精确匹配：1000x
  - 前缀匹配：100x
  - 子串匹配：1x
  - 来源文件：0.5x
  - IDF 权重：`log(1 + N / (1 + df))`

- `pick_seed_nodes()` — 种子选择（最多3个）
  - 按分数排序
  - 当分数下降到顶分的20%以下时停止
  - 防止噪音节点被选中

- `traverse_graph_bfs()` / `traverse_graph_dfs()` — 图遍历
  - BFS：广度优先（默认）
  - DFS：深度优先（追踪路径）
  - Hub 避免：p99 度数阈值，防止高度数节点扩展

- `render_subgraph_text()` — 文本渲染
  - 格式：`NODE ... [src=... loc=... type=...]`
  - 边格式：`EDGE ... --relation [confidence context=...]`
  - 自动截断：按 token_budget 切割

- `query_graph()` — 统一入口
  - 接收查询参数，返回完整结果

**统计**：
- 代码行数：~800 行
- 单元测试：19 个（全部通过）
- 测试覆盖率：所有核心功能

#### 2. `stage2_agent_dispatch.py` - Agent 派发系统
实现了完整的 3 个 agent 派发阶段：

**第3步：查询参数生成**
- `prepare_query_task_packet()` — 准备查询任务包
- `dispatch_query_agent()` — 派发查询 agent
  - Agent 接收：模板定义 + 查询提示
  - Agent 输出：标准化查询参数 JSON

**第3步：草稿生成**
- `prepare_draft_task_packet()` — 准备草稿任务包
- `dispatch_draft_agent()` — 派发草稿 agent
  - Agent 接收：查询结果 + 模板定义 + 原始 Markdown
  - Agent 输出：结构化草稿（带来源标注）
- `save_draft()` — 保存草稿到 `graph_dir/drafts/`

**第4步：最终文档生成**
- `prepare_final_task_packet()` — 准备最终任务包
- `dispatch_final_agent()` — 派发最终 agent
  - Agent 接收：草稿 + 模板 + 渲染策略
  - Agent 输出：干净的 Markdown（无来源标注）
- `save_final_markdown()` — 保存最终文档到 `graph_dir/generated/`

**批量派发**
- `prepare_stage2_query_batches()` — 批量准备查询任务
- `prepare_stage2_draft_batches()` — 批量准备草稿任务
- `prepare_stage2_final_batches()` — 批量准备最终任务

**结果收集**
- `collect_query_results()` — 收集查询结果（JSON 解析 + 反序列化）
- `collect_draft_results()` — 收集草稿结果（嵌套结构处理）
- `collect_final_results()` — 收集最终结果（Markdown 字符串）

**统计**：
- 代码行数：~450 行
- 单元测试：13 个（全部通过）
- 测试覆盖率：所有任务包准备 + 结果收集

### ✅ 测试验证

**测试执行结果**：
```
32 passed in 0.49s
- test_stage2_graph_query.py: 19 tests ✓
- test_stage2_agent_dispatch.py: 13 tests ✓
```

**测试覆盖范围**：
1. ✓ 参数规范化（默认值、覆盖、边界）
2. ✓ 词提取（英文、中文、混合、空输入）
3. ✓ 节点评分（空图、匹配、精确 > 前缀）
4. ✓ 种子选择（排序、上限、空列表）
5. ✓ 图遍历（BFS、DFS、边界）
6. ✓ 文本渲染（简单、截断）
7. ✓ 完整查询流程
8. ✓ 任务包准备（查询、草稿、最终）
9. ✓ 结果收集（JSON 解析、嵌套、过滤）

---

## 新增文件

```
skill-src/storygraph/scripts/storygraph_lib/
├─ stage2_graph_query.py        (新增，800行，Graphify查询引擎)
└─ stage2_agent_dispatch.py      (新增，450行，Agent派发系统)

tests/
├─ test_stage2_graph_query.py    (新增，19个测试)
└─ test_stage2_agent_dispatch.py (新增，13个测试)
```

---

## 后续工作（待做）

### 第5步：删除老代码并集成

需要完成以下工作（下一步）：

1. **删除旧文件**：
   - `stage2_query.py` ❌ 删除
   - `stage2_render.py` ❌ 删除
   - `stage2_evidence.py` ❌ 删除

2. **改造 stage2.py**：
   - 导入新模块
   - 替换旧的 `query_stage2_cases()` 调用 → `query_graph()`
   - 替换旧的 render 流程 → agent 派发
   - 删除对旧模块的依赖

3. **删除旧的单元测试**：
   - `test_stage2_query.py` ❌ 删除
   - `test_stage2_render.py` ❌ 删除

4. **更新 stage2_schema.py**：
   - 如需要，适配新的查询结果格式

5. **完整端到端测试**：
   - 验证 Stage 2 完整流程
   - 验证生成的最终文档质量

---

## 设计亮点

### 1. Graphify 兼容性
- 采用完全相同的 5 步查询流程
- IDF 加权、Hub 避免、种子选择逻辑一致
- 可复用 Graphify 的查询优化经验

### 2. 中英文支持
- jieba 分词用于中文
- 正则表达式用于英文
- 自动检测并处理混合输入

### 3. 完全 Agent 驱动
- 第3-4步完全由 agent 决策
- Python 只负责数据流和 I/O
- Agent 可自定义去重、归并、排序策略

### 4. 来源追溯
- 草稿中保留完整的来源标注（节点ID、证据ID、覆盖度）
- 最终文档干净，无内部细节
- 便于审查和调试

### 5. 稳定的数据格式
- 所有任务包都是标准化的 JSON
- Agent 输出支持 JSON 解析和字符串解析
- 易于扩展和调试

---

## 关键参数参考

### query_graph() 输入
```python
{
    "question": "天然气如何形成",  # 查询文本
    "mode": "bfs",                 # bfs | dfs
    "depth": 3,                    # 1-6
    "token_budget": 2000,          # 输出大小
    "target_node_types": {"pill"},  # 过滤节点类型
    "context_filter": ["effect"],   # 过滤边类型
    "include_terms": ["丹药"],      # 必含词
    "exclude_terms": ["副作用"],    # 必排除词
    "limit": 20                     # 结果数上限
}
```

### query_graph() 输出
```python
{
    "question": "...",
    "mode": "bfs",
    "depth": 3,
    "nodes_found": 42,
    "edges_found": 30,
    "text": "NODE ...\nEDGE ...",
    "seeds": ["node1", "node2"],
    "visited_nodes": ["node1", ...]
}
```

### Draft 格式
```python
[
    {
        "case_id": "pill_01",
        "title": "筑基丹分析",
        "fields": {"effect": "...", "material": "..."},
        "source_nodes": ["pill:zhuji_dan"],
        "source_evidence": ["evidence_id_123"],
        "coverage": "complete|partial|missing"
    }
]
```

---

## 验收标准

- ✅ 所有新测试通过
- ✅ 代码无 linting 错误
- ✅ 文档完整
- ✅ 5步流程完整实现
- ⏳ 完成 stage2.py 集成（下一步）
- ⏳ 删除旧代码（下一步）
- ⏳ 端到端测试（下一步）

---

## 总结

成功实现了 Stage 2 的查询和 Agent 派发系统，采用 Graphify 的 5 步查询流程，支持完整的 agent-driven 文档生成。代码质量高（32/32 测试通过），设计清晰（中英文、来源追溯、稳定格式），可直接集成到 stage2.py。

下一步：删除旧代码、改造 stage2.py、完成端到端测试。
