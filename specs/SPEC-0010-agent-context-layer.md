# SPEC-0010: Agent Context Layer

> **Status:** Draft v0.1
> **Phase:** v1.0 Architecture
> **作者:** Intent OS Project

---

## 1. Purpose

Define Intent OS's **分层上下文（Layered Context）** —— Agent 作为一个"数字人"在运行时需要的全部上下文信息，按照稳定性和来源分层，确保每次运行时只加载相关的部分。

## 2. 核心原则

### 2.1 Context ≠ Memory

Intent OS 的 Context 不是用户偏好记忆。项目的独特价值在于 **Execution-grounded Context**——所有上下文都有执行记录作为证据支撑。

```
别人的 Memory：    用户说"我喜欢简洁回答"
Intent OS Context：过去 500 次执行证明：该 Agent 的简短回答格式成功率高 27%
                                        evidence: [exec_123, ..., exec_500]
```

### 2.2 Execution → Extraction → Context 三阶段

```
Execution Records（原始历史，无限增长）
        ↓  ExperienceExtractor + 压缩流水线
Extracted Patterns（提炼模式，MB 级）
        ↓  Context Retrieval（类似 RAG）
Runtime Context（每次加载，KB 级，~3000 token）
```

Execution Record 不应该被直接喂给 Agent。那是原始历史。**Experience 是从历史中提炼出的资产。**

### 2.3 分层加载

每次 AI 运行不加载全部 Context。只加载与当前任务相关的部分。类似 RAG 的检索模式：

```
User Request "分析 Nvidia"
    ↓
Context Retrieval
    ↓
加载：Identity Layer（固定）+
     Capability Layer（financial_analysis 相关）+
     Experience Layer（Nvidia / 半导体相关）+
     Working Context（当前任务）
    ↓
组装 Prompt（~3000 token）
    ↓
Execution
```

### 2.4 层级总览

| 层级 | 内容 | 稳定性 | 大小 | 每次加载 |
|------|------|--------|------|---------|
| Identity | 我是谁、长期偏好 | 极稳定 | KB 级（<1K token） | **是** |
| Capability | 我会什么、能力证明 | 稳定 | KB-MB 级 | 按需 |
| Experience | 我学到了什么（压缩模式） | 稳定 | MB 级 | 按需 |
| Relationship | 我和谁合作 | 稳定 | KB 级 | 按需 |
| Environment | 我在哪里工作 | 半稳定 | KB 级 | **是** |
| Working | 我现在做什么 | 临时 | KB 级 | **是** |

---

## 3. Identity Context（第一层：身份上下文）

**类比：** 人的基本身份 + 长期习惯。你去面试不会每次重新介绍自己的价值观。

**特点：** 极稳定、每次加载、很少变化。

```yaml
identity:
  name: "金融研究助手"
  persona: "专业金融分析师，专注 SEC 文件分析"
  traits: ["cautious", "analytical", "detail-oriented"]

  domain:
    - finance
    - quantitative_analysis
    - sec_filings

  working_style:
    - data_driven
    - conservative
    - evidence_before_conclusion

  preferences:
    communication:
      concise: true
      language: zh
      format: markdown_tables
    output:
      include_citations: true
      confidence_threshold: 0.7

  principles:
    - prioritize risk control
    - verify before conclusion
    - never speculate without data
    - cite all sources
```

**数据来源：** `agent.persona` + `agent.traits` + `agent update --preference`

**存储方式：** `~/.intent-os/agents/<id>/IDENTITY.yaml`（已实现）

---

## 4. Capability Context（第二层：能力上下文）

**类比：** 简历上的技能，但不是自己写的——是执行记录证明的。

**关键区别：**

| 传统做法 | Intent OS 做法 |
|---------|---------------|
| 用户声明"我擅长 Python" | 系统证明"3200 次 Python 执行，成功率 96%" |
| 标签：`skills: [stock, python]` | 结构化能力：`tasks_completed, success_rate, proven_patterns, limitations` |
| 静态声明 | 动态证明，随执行更新 |

```yaml
capabilities:
  financial_analysis:
    level: expert
    description: "SEC 财报分析、估值建模、行业研究"
    total_tasks: 3200
    success_rate: 0.92
    avg_cost_per_task: 0.08
    preferred_models: ["claude-sonnet-4", "gpt-4o"]

    proven_patterns:
      - task_type: "earnings_analysis"
        success_rate: 0.94
        sample_count: 850
        key_steps:
          - check_cash_flow_first
          - compare_with_guidance
          - peer_benchmarking

      - task_type: "dcf_valuation"
        success_rate: 0.88
        sample_count: 320
        key_steps:
          - revenue_driver_identification
          - wacc_calculation
          - sensitivity_analysis

    limitations:
      - cannot_predict_short_term_price
      - requires_structured_financial_data
      - confidence_drops_below_0.6_for_early_stage_companies
```

**数据来源：** EventStore `execution_records` 聚合（已完成）+ 新的聚合查询

**不是简单标签**——能力必须有执行证明。`limitations` 字段和 `proven_patterns` 一样重要，它告诉下游系统什么时候**不**该用这个 Agent。

---

## 5. Experience Context（第三层：经验上下文）

**类比：** 人的经验——不记得"2018 年 3 月 5 日下午 2 点我说了什么"，而是记得"我遇到过类似情况，那次错了因为忽略了现金流"。

### 5.1 压缩流水线

```
1000 条 Execution Records
    ↓  classify_failure / classify_success
失败模式提取    成功模式提取
    ↓  deduplicate_by_pattern    ↓  deduplicate_by_pattern
3 条失败模式     5 条成功策略
    ↓  confidence_scoring
Experience Context
```

### 5.2 数据结构

```yaml
experience:
  patterns:
    - id: "exp_f2a1c3e4"
      type: "failure_pattern"
      situation:
        task_type: "earnings_analysis"
        trigger: "company_high_revenue_growth"
        input_signals:
          - revenue_growth > 30%
          - positive_guidance
          - no_cash_flow_mention
      mistake: "ignored_cash_flow_deterioration"
      consequence: "overvalued_company_by_40%"
      lesson: "always_check_fcf_before_valuation"
      confidence: 0.91
      evidence:
        execution_count: 7
        executions: ["exec_123", "exec_456", "exec_789"]

    - id: "exp_b4d8e2f1"
      type: "success_strategy"
      situation:
        task_type: "dcf_valuation"
        trigger: "company_with_negative_fcf"
      approach: "use_dcf_with_revenue_multiple_hybrid"
      outcome: "more_accurate_valuation"
      evidence:
        success_rate_improvement: "+23%"
        execution_count: 45
```

**数据来源：** ExperienceStore（已实现）+ 新的 Pattern 聚合算法

### 5.3 关键设计决策

- **不包含原始执行记录** — 只包含提炼后的模式
- **每个 pattern 必须有 evidence** — `execution_count` + 至少 3 条引用
- **confidence 随 evidence 增加而提升** — 1 次模式 ≈ 0.3 置信度，7+ 次 ≈ 0.9+
- **situation 字段是关键** — 让检索系统能匹配"什么情况下这个经验适用"
- **经验可以过期** — 如果模式不再出现，confidence 随时间衰减

---

## 6. Working Context（第四层：工作上下文）

**类比：** 你当前工作台上的东西——临时，任务结束就归档。

```yaml
working_context:
  task_id: "exec_nvidia_q3_2026"
  goal: "Analyze Nvidia Q3 2026 earnings and provide investment recommendation"
  constraints:
    - "long_term_investment_horizon_only"
    - "max_10%_position_size"
    - "consider_competitor_landscape"

  current_progress:
    phase: "financial_analysis"
    completed_steps:
      - "revenue_analysis"
      - "margin_analysis"
    pending_steps:
      - "competitive_positioning"
      - "valuation"
      - "risk_assessment"

  available_tools:
    - "bloomberg_api"
    - "sec_edgar"
    - "cap_analysis"

  status: "in_progress"    # in_progress | paused | completed | abandoned
```

**数据来源：** `intent-os context create` 命令（已实现）+ 新字段 `current_progress`

---

## 7. Relationship Context（第五层：关系上下文）

**类比：** 你的通讯录——和谁合作过、谁在做什么。

```yaml
relationships:
  teams:
    - team_id: "team_research"
      name: "Research Squad"
      members:
        - agent_id: "agent_macro"
          role: "宏观分析"
        - agent_id: "agent_risk"
          role: "风险评估"
      shared_context:
        - "ctx_market_conditions"

  delegation_history:
    - task_type: "data_collection"
      delegated_to: "agent_data_engineer"
      collaboration_count: 45
      avg_success_rate: 0.97
```

**数据来源：** `agent team` 命令（已实现）

---

## 8. Environment Context（第六层：环境上下文）

**类比：** 你办公室的布局——你知道文件在哪、工具在哪。

```yaml
environment:
  runtime: "intent-os-reference"  # runtime 标识
  available_adapters: ["openai", "anthropic", "ollama"]
  data_sources:
    - name: "SEC EDGAR"
      type: "api"
      reliability: 0.95
      rate_limit: "10_req_per_sec"
    - name: "Bloomberg"
      type: "api"
      reliability: 0.99
      requires_subscription: true

  tools:
    - "filesystem_write"
    - "database_query"
    - "web_search"
```

**数据来源：** Runtime 自检（新功能）

---

## 9. Context Retrieval（上下文检索）

### 9.1 加载策略

每次用户请求时，不是加载全部 Context，而是按策略选择：

```
1. 固定加载
   Identity Context（~500 token） ← 每次都加载
   Environment Context（~300 token） ← 每次都加载

2. 按需加载（RAG 式检索）
   User Request → 向量化 → 匹配 Capability / Experience 中的 situation 字段
   → 只加载匹配的条目（~2000 token）

3. 任务态加载
   Working Context（~500 token） ← 当前任务存在时加载

4. 不加载
   已完成的任务记录
   不匹配的 Capability 证明
   原始 Execution Records
```

### 9.2 Token 预算

```
每次 Agent 调用总 Context budget：~3000-5000 token

Identity:         ~500 token（固定）
Environment:      ~200 token（固定）
Working:          ~300 token（如有）
Capability:       ~1000 token（检索匹配）
Experience:       ~1000 token（检索匹配）
剩余 buffer:      ~1000 token
```

### 9.3 检索优先级

```
1. Identity（命中率 100%，因为固定加载）
2. Working Context 的 goal 匹配 Experience 的 situation
3. User Request 关键词匹配 Capability 的 task_type
4. User Request 关键词匹配 Experience 的 situation.trigger
5. Relationship 中的合作者能力匹配（跨 Agent 场景）
```

---

## 10. 和现有 Intent OS 架构的关系

### 已实现的部分

| 层级 | 现有代码 | 状态 |
|------|---------|------|
| Identity | `agent.persona`, `agent.traits`, `IDENTITY.yaml` | ✅ 已有 |
| Capability | `agent.capabilities`（但只是标签，无证明） | ⬜️ 需要 Deepen |
| Experience | `experience_store.py` + `experience_extractor.py` | ✅ 已有，需 Pattern 化 |
| Working | `context_store.py`（goal, constraints） | ✅ 已有 |
| Relationship | `agent team` | ✅ 已有 |
| Environment | 无 | ❌ 新增 |

### 需要 Deepen 的部分

1. **Capability 层** — 从纯标签改为"证明结构"，聚合 EventStore 数据
2. **Experience 层** — 从纯文本 observation 改为结构化 pattern（situation → mistake → lesson）
3. **Context Retrieval** — 新增 RAG 式检索模块
4. **Environment 层** — 新增 runtime 自检
5. **注入机制** — Phase C 的 `context_injector.py` 升级为分层注入

### 不需要修改

- Agent 的数据模型（persona, traits, avatar）
- AgentStore, ExperienceStore 的 CRUD
- EventStore 的事件记录
- Proxy 的拦截逻辑
- MCP Server 的资源暴露

---

## 11. 当前阶段建议优先级

| 优先级 | 做什么 | 为什么现在做 |
|--------|--------|-------------|
| **P0** | Capability 层数据模型 + 聚合 | 现有 `agent.capabilities` 就是标签，需要变成"证明"。数据已经在 EventStore 里，只需要新的聚合查询。 |
| **P1** | Experience Pattern 结构化 | 现有经验是纯文本 `observation`。改成 `situation → mistake → lesson` 结构。检索效果大幅提升。 |
| **P2** | Context Retrieval 模块 | RAG 式按需加载，解决"每次跑多少 Context"的问题 |
| **P3** | Environment 层 | Runtime 自检，新功能但独立 |
| **P4** | Relationship 动态化 | 需要跨 Agent 执行数据积累后才有意义 |

---

## 12. 不做

- **不把原始 Execution Record 当成 Context** — Record 是历史，不是知识
- **不做 Memory Store（用户偏好）** — 那是特定 Agent 角色的功能，不是通用层
- **不做向量数据库** — 初期关键词 + situation 字段匹配就够，需要时再加 embedding
- **不替换现有的 Phase C 注入** — Phase C 是简单的注入，Layered Context 是升级版

---

## 13. 生命周期

```
Create（agent create）
    │
    ▼
Identity 固化
    │
    ▼
Execute（proxy start 积累执行记录）
    │
    ▼
Capability 聚合（EventStore → 能力证明）
    │
    ▼
Experience 提取（Execution → Pattern）
    │
    ▼
Export（agent export → .agent 包含所有层）
    │
    ▼
Import（agent import → 新实例重建所有层）
    │
    ▼
Runtime Context Retrieval（每次执行按需加载）
```

---

*Context 不是记忆。Context 是基于执行证据的能力和经验。Intent OS 不存"用户喜欢什么"，它存"这个 Agent 的 3200 次执行证明了什么"。*
