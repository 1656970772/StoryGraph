# StoryGraph Skill 完整流程图

## 📊 整体架构

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                         StoryGraph Skill 主流程                              │
└─────────────────────────────────────────────────────────────────────────────┘

                              用户提供
                          ┌────────────────┐
                          │ 小说源文件      │
                          │ 模板目录        │
                          │ 目标 graph 目录 │
                          └────────┬────────┘
                                   │
                    ┌──────────────┴──────────────┐
                    │                             │
              选择用户模式                         │
              ┌──────────────────┐                │
              │ • full           │                │
              │ • stage2_incremental   │                │
              │ • full_incremental    │                │
              └──────────┬────────────┘                │
                         │                             │
                    ┌────┴────┐                        │
                    ▼         ▼                        │
            ┌──────────────┐  │                        │
            │  Stage 1     │  │                        │
            │ (图谱构建)    │  │                        │
            └──────┬───────┘  │                        │
                   │          │                        │
                   ▼          ▼                        │
            ┌──────────────────────┐                  │
            │   Stage 2            │                  │
            │ (模板文档生成)        │                  │
            └──────────┬───────────┘                  │
                       │                              │
                       └──────────────────────────────┘
```

---

## 🔄 Stage 1: 图谱构建 (Agent-Driven)

```
Stage 1 完整流程
═══════════════════════════════════════════════════════════════

第0步: 准备阶段
─────────────────────────────────────────────────────────────
  prepare-stage1
    ├─ 加载配置 (config/storygraph.default.json)
    ├─ 发现模板 (inspect-templates)
    ├─ 分块小说 (chunk strategy)
    ├─ 生成 task packets
    └─ 写入 intermediate/agent-dispatch-plan.json
         └─ execution_batches 列表
              ├─ template_requirements phase
              ├─ lane_extraction phase (N 个 chunks)
              └─ agent_policy.max_parallel


第1步: 生成模板需求分析
─────────────────────────────────────────────────────────────
  ┌─ next-agent-batches --phase template_requirements
  │    按 max_parallel 并行派发
  │
  ├─ 每个 TemplateRequirementsAgent 消费 1-5 个模板
  │    ├─ 分析模板 Markdown
  │    ├─ 提取需求目标 (required_extraction_targets)
  │    ├─ 提取证据需求 (evidence_requirements)
  │    ├─ 分类覆盖 (template_coverage)
  │    └─ 写入 intermediate/template-requirements-parts/batch-*.json
  │
  └─ 等待所有分片产物
       └─ ingest-template-requirements (单次)
            ├─ 汇总 → intermediate/template-requirements.json
            ├─ 简单冲突检测 (同名模板合并/报错)
            └─ 校验 schema → requirements/template-requirements.json


第2步: 综合抽取 (Lane 滑动窗口)
─────────────────────────────────────────────────────────────
  ┌─ claim-agent-batches (滑动窗口模式)
  │
  ├─ 首次: --limit max_parallel_agents
  │    └─ 派发 N 个 lane extraction agents
  │         ├─ 消费 chunk task packet
  │         ├─ 读取抽取质量规则
  │         ├─ 抽取节点、边、事件、证据
  │         └─ 写入 intermediate/lane-outputs/<chunk>/*.json
  │
  ├─ 循环: 每完成一个 batch 就 --limit 1
  │    ├─ 检查 completed batches
  │    ├─ 派发新的 lane extraction agent
  │    └─ 更新 intermediate/agent-dispatch-state.json
  │
  └─ 终止条件
       ├─ pending_count == 0
       ├─ in_flight_count == 0
       └─ 所有 expected_output_paths 存在


第3步: 摄取 & 合并 (确定性)
─────────────────────────────────────────────────────────────
  ┌─ ingest-stage1
  │    ├─ 校验所有 lane outputs (schema, 引用)
  │    ├─ 标记 merge_gate_status (unreviewed_usable)
  │    └─ 返回 bundle 列表
  │
  └─ merge-stage1
       ├─ 读取所有通过 merge gate 的 bundles
       ├─ Canonical writer 确定性归一化
       │    ├─ 稳定 ID 生成 (hash based)
       │    ├─ 去重、收敛别名
       │    ├─ 合并 provenance
       │    ├─ 建立 evidence index
       │    └─ 标记 review_status
       ├─ 写出 graphify-out/graph.json
       └─ 记录 manifest/ledger


第4步: 验证 (质量门槛)
─────────────────────────────────────────────────────────────
  validate-graph
    ├─ 检查必需产物
    ├─ 校验 schema 完整性
    ├─ 验证 evidence index 一致性
    ├─ 检查 manifest 状态
    └─ 返回 ok: true/false


💾 Stage 1 主要产物
──────────────────
  ├─ graphify-out/graph.json              (图谱)
  ├─ requirements/template-requirements.json
  ├─ coverage/evidence-index.json
  ├─ coverage/chunk-ledger.json
  ├─ coverage/template-readiness.json
  ├─ coverage/agent-run-ledger.json
  ├─ intermediate/agent-dispatch-state.json
  └─ manifest.json (stage_status.stage1 = success)
```

---

## 📄 Stage 2: 模板文档生成 (Agent-Driven)

```
Stage 2 完整流程
═══════════════════════════════════════════════════════════════

第0步: 准备阶段
─────────────────────────────────────────────────────────────
  prepare-stage2
    ├─ 验证 Stage 1 完成
    ├─ 发现 Stage 2 模板
    ├─ 按模板生成 task packets
    ├─ 写入 intermediate/stage2/task-packets/*.json
    └─ 初始化 dispatch-state.json


第1步: 查询参数生成 (NEW - Graphify风格)
─────────────────────────────────────────────────────────────
  ┌─ 并行派发查询 Agent
  │
  ├─ QueryAgent 消费 task packet
  │    ├─ 分析模板需求
  │    ├─ 生成查询参数
  │    │    ├─ question (自然语言查询)
  │    │    ├─ mode (bfs|dfs)
  │    │    ├─ depth (1-6)
  │    │    ├─ target_node_types (节点类型过滤)
  │    │    ├─ context_filter (边类型过滤)
  │    │    ├─ include_terms (必含词)
  │    │    └─ exclude_terms (必排除词)
  │    └─ 返回参数 JSON
  │
  └─ 保存查询参数


第2步: 图谱查询 (Python - 确定性)
─────────────────────────────────────────────────────────────
  query_graph (Graphify 兼容引擎)
    │
    ├─ 步骤 2a: 参数规范化
    │    ├─ 填充默认值
    │    └─ 类型转换 & 验证
    │
    ├─ 步骤 2b: 词提取
    │    ├─ 中文: jieba 分词
    │    ├─ 英文: 单词切分 + 过滤短词
    │    └─ 去重、小写、去重音
    │
    ├─ 步骤 2c: 节点评分 (IDF加权)
    │    ├─ 精确匹配: 1000x
    │    ├─ 前缀匹配: 100x
    │    ├─ 子串匹配: 1x
    │    └─ 文件名匹配: 0.5x
    │
    ├─ 步骤 2d: 种子选择
    │    ├─ 取分数最高的节点
    │    └─ 当分数 < 顶分的20% 时停止 (最多3个)
    │
    ├─ 步骤 2e: 图遍历
    │    ├─ BFS 或 DFS
    │    ├─ Hub 避免 (p99 度数)
    │    └─ 按 context_filter 过滤边
    │
    └─ 步骤 2f: 文本渲染
         ├─ 格式化输出
         ├─ 按 token_budget 截断
         └─ 返回查询结果


第3步: 草稿生成 (Agent驱动)
─────────────────────────────────────────────────────────────
  ┌─ 并行派发草稿 Agent
  │
  ├─ DraftAgent 消费查询结果 + task packet
  │    ├─ 读取查询结果中的节点和边
  │    ├─ 读取模板定义和字段要求
  │    ├─ 提取结构化信息
  │    ├─ 为每条信息标注来源
  │    │    ├─ 来源节点 ID
  │    │    ├─ 证据 ID
  │    │    └─ 置信度
  │    ├─ 生成结构化草稿
  │    │    ├─ case_id
  │    │    ├─ title
  │    │    ├─ fields {...}
  │    │    ├─ source_nodes []
  │    │    ├─ source_evidence []
  │    │    └─ coverage (complete|partial|missing)
  │    └─ 返回草稿 JSON 数组
  │
  └─ 保存草稿到 graph_dir/drafts/<template>.draft.json
       ├─ 包含完整来源标注
       └─ 保留数据覆盖缺口标记


第4步: 最终文档生成 (Agent驱动)
─────────────────────────────────────────────────────────────
  ┌─ 并行派发最终 Agent
  │
  ├─ FinalAgent 消费草稿 + task packet
  │    ├─ 读取结构化草稿
  │    ├─ 读取原始模板 Markdown (校验hash)
  │    ├─ 读取渲染策略
  │    ├─ 执行处理
  │    │    ├─ 去重 (dedup_strategy)
  │    │    ├─ 归并 (merge_strategy)
  │    │    └─ 排序 (sort_strategy)
  │    ├─ 按模板结构渲染
  │    ├─ 移除来源标注
  │    └─ 返回干净的 Markdown
  │
  └─ 保存最终文档到 graph_dir/generated/<template>.md
       ├─ 无来源标注
       └─ 只保留最终案例


第5步: 输出策略 (Python确定性)
─────────────────────────────────────────────────────────────
  根据 overwrite_policy:

  draft (默认)
    ├─ 写入 graph_dir/drafts/<template>.md
    ├─ 只包含审查型结构 (名称、分类、字段)
    ├─ 保留来源标注
    └─ 不渲染前置声明和资料来源

  backup-and-overwrite
    ├─ 读取原始模板 hash
    ├─ 先备份小说目录中的同名文件
    ├─ 写入 graph_dir/generated/<template>.md
    ├─ 基于模板结构渲染
    ├─ 执行准入、去重、归并
    └─ 只输出正式案例

  merge
    ├─ 需要单独的 merge contract
    └─ 返回 merge_contract_required


💾 Stage 2 主要产物
──────────────────
  ├─ intermediate/stage2/task-packets/*.json
  ├─ intermediate/stage2/dispatch-state.json
  ├─ intermediate/stage2/extraction-records/<template>/*.json
  ├─ drafts/<template>.draft.json
  ├─ generated/<template>.md (or drafts/<template>.md)
  └─ manifest.json (stage_status.stage2 = rendered)
```

---

## 🔄 用户模式详解

```
1️⃣  full (默认全量)
    ├─ Stage 1: 完整流程 (prepare → requirements → extraction → merge → validate)
    │            不再包括三轮需求整理，直接单轮处理
    └─ Stage 2: 完整流程 (prepare → query → draft → final)
    
    使用场景: 第一次构建或完全重建
    优势: 速度快 30%+


2️⃣  stage2_incremental (Stage 2 增量)
    ├─ Stage 1: 只验证 (validate-graph)
    └─ Stage 2: 按 selection 策略
         ├─ changed-or-missing
         └─ only 处理变更、缺失或未渲染的模板
    
    使用场景: 模板或 Stage 2 发生变更


3️⃣  full_incremental (全量增量)
    ├─ Stage 1: 只重做受影响模板相关支撑
    │    ├─ 单轮生成 template requirements
    │    └─ 仅重做 scope = changed-template-support 的 chunks
    └─ Stage 2: 按 selection 策略处理受影响或缺失模板
    
    使用场景: 模板内容发生实质性变更
```

---

## 🎯 关键设计点

```
┌─────────────────────────────────────────────────────────┐
│ Agent 驱动 vs Python 确定性 的分工                       │
└─────────────────────────────────────────────────────────┘

Stage 1:
  ✨ Agent 驱动
    ├─ Template Requirements Agent (需求分析)
    ├─ Lane Extraction Agent (语义抽取)
    └─ Refinement Agent x3 (需求整理)

  🔧 Python 确定性
    ├─ prepare-stage1 (配置+分块+任务包)
    ├─ ingest-stage1 (校验+标记)
    ├─ merge-stage1 (确定性归一化+ID稳定)
    └─ validate-graph (质量门槛)


Stage 2 (NEW - 改进版):
  ✨ Agent 驱动
    ├─ Query Agent (参数生成)
    ├─ Draft Agent (结构化抽取 + 来源标注)
    └─ Final Agent (Markdown渲染 + 去重归并)

  🔧 Python 确定性
    ├─ prepare-stage2 (模板发现+任务包)
    ├─ query_graph (Graphify兼容查询引擎)
    ├─ render-stage2 (输出策略+截断)
    └─ validate-stage2 (质量检查)


┌─────────────────────────────────────────────────────────┐
│ 核心特点                                                 │
└─────────────────────────────────────────────────────────┘

✅ 完全 Agent 驱动语义生产
  └─ Python 只做确定性工具层 (无语义决策)

✅ 证据链完整追溯
  ├─ Stage 1: provenance + evidence_index
  └─ Stage 2: 草稿保留来源，最终文档干净

✅ 增量支持
  ├─ 模板变更: full_incremental
  └─ Stage 2 变更: stage2_incremental

✅ Graphify 兼容
  ├─ 采用相同的查询流程
  └─ 可选可视化和查询增强

✅ 质量门槛
  ├─ Schema 校验
  ├─ 证据闭合检查
  └─ 最终 validate-graph
```

---

## 📋 CLI 命令参考

```
CLI 入口: scripts/storygraph.py

Stage 1 子命令:
  validate-skill              验证 skill 结构
  prepare-stage1              第0步：准备
  next-agent-batches          获取下一批任务
  ingest-template-requirements 摄取模板需求
  ingest-stage1               摄取 lane outputs
  merge-stage1                合并 & 规范化
  validate-graph              质量检查

Stage 2 子命令:
  prepare-stage2              第0步：准备
  claim-stage2-batches        获取下一批任务
  render-stage2               渲染最终文档
  validate-stage2             质量检查

实际流程由主 Agent 编排，不由 CLI 直接调用
```

---

## 总结对比

```
┌──────────────────┬─────────────┬──────────────┬──────────────┐
│ 阶段              │ 主要 Agent   │ Python 工具   │ 输出产物      │
├──────────────────┼─────────────┼──────────────┼──────────────┤
│ Stage 1 需求分析  │ ✨ 必需      │ 🔧 支撑       │ requirements │
│ Stage 1 抽取      │ ✨ 必需      │ 🔧 支撑       │ graph.json   │
│ Stage 1 合并      │ ❌ 无        │ 🔧 完全自动   │ canonical    │
│ Stage 2 查询参数  │ ✨ 可选*     │ 🔧 Python    │ query result │
│ Stage 2 草稿      │ ✨ 必需      │ 🔧 支撑       │ 草稿 JSON    │
│ Stage 2 最终文档  │ ✨ 必需      │ 🔧 支撑       │ 最终 Markdown│
└──────────────────┴─────────────┴──────────────┴──────────────┘

* Stage 2 查询参数生成可由 Agent 执行，也可由 Python 模板规则执行
```
