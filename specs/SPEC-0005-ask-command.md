# SPEC-0005: Natural Language Command — `intent-os ask`

> **Status:** Design Draft v0.1
> **Scope:** Natural language interface for Intent OS operations
> **Editor:** Product Manager — Intent OS Project

---

## 1. 一句话定义

**让一个零技术基础的用户，用自然语言完成 Intent OS 能做的所有事——效果和用 CLI 一样。**

---

## 2. 用户旅程

### 2.1 典型对话

```
用户: "帮我总结这篇文章，用本地模型跑"
系统: 找到 Manifest「text_summarize」
      → 用 Ollama 执行
      → 返回结果

用户: "不对，用 OpenAI 重新跑，我想要英文版的"
系统: 重新执行，adapter=openai，style=concise
      → 返回结果

用户: "把我刚才用 OpenAI 跑的也存一份到我的能力库里"
系统: → 注册到 Registry，添加标签 summarization
```

### 2.2 跟 CLI 的关系

```
CLI 用户: intent-os run examples/translate.yaml --adapter ollama --input '{...}'
Ask 用户: intent-os ask "帮我把这个翻译成英文，用本地模型跑"
```

两者最终走的是**同一套执行引擎**。Ask 只是多了一个"自然语言 → 结构化参数"的翻译层。

---

## 3. 系统架构

```
┌─────────────────────────────────────────────────────┐
│                   用户界面层                         │
│  ┌────────────────────────────────────────────────┐ │
│  │      intent-os ask "自然语言..."                │ │
│  │      → 交互式会话（多轮）                       │ │
│  │      → 单句模式（--message "..."）              │ │
│  └────────────────────────────────────────────────┘ │
└──────────────────────┬──────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────┐
│                  解释器层                            │
│                                                     │
│  ┌──────────────────┐  ┌─────────────────────────┐  │
│  │  意图分类器      │  │  参数提取器              │  │
│  │  → run / registry│  │  → text, style, adapter  │  │
│  │  → security /    │  │  → source_lang, format   │  │
│  │    evolution     │  │  → ...根据 Manifest 动态  │  │
│  └──────────────────┘  └─────────────────────────┘  │
│                                                     │
│  ┌──────────────────────────────────────────────┐   │
│  │  Manifest 匹配器                               │   │
│  │  1. 语义搜索 Registry → 已有 Manifest          │   │
│  │  2. 找不到 → LLM 生成新 Manifest                │   │
│  │  3. 不能完全匹配 → 询问用户补充信息              │   │
│  └──────────────────────────────────────────────┘   │
└──────────────────────┬──────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────┐
│                  执行层（已有）                       │
│                                                     │
│  Executor → Adapter → Model                          │
│  Registry / Security / Event Store                   │
│                                                     │
└──────────────────────┬──────────────────────────────┘
                       │
┌──────────────────────▼──────────────────────────────┐
│                  记忆层                              │
│                                                     │
│  用户偏好SQLite                                      │
│  → 默认 adapter（user_preferred_adapter: ollama）     │
│  → 最近使用的 Manifest                                │
│  → 对话历史                                           │
└─────────────────────────────────────────────────────┘
```

### 3.1 层职责

| 层 | 职责 | 新代码 |
|---|---|---|
| **解释器层** | LLM 调用 + 意图解析 + Manifest 匹配 | **全部新建** |
| **执行层** | 已有的 Executor/Registry/Security | 无需修改 |
| **记忆层** | 用户偏好持久化 | 新增 SQLite 表 |

---

## 4. 数据流

```
用户输入: "帮我把这个分析一下情绪，用 OpenAI"

Step 1: 意图分类
  └→ LLM 判断: action=run, domain=sentiment_analysis

Step 2: Manifest 搜索
  └→ registry.find_by_text("sentiment analysis")
  └→ 找到 examples/sentiment_analyze.yaml (score=0.89)
  └→ 未找到 → LLM 生成新 Manifest

Step 3: 参数提取
  └→ LLM 提取: {text: "...", adapter: "openai"}
  └→ 用户偏好覆盖: 未指定 adapter → 使用默认

Step 4: 安全评估
  └→ SecurityManager.evaluate(risk="low") → ALLOW

Step 5: 执行
  └→ Executor.execute(manifest, input_data, adapter_name)

Step 6: 结果呈现
  └→ 自然语言摘要 + 结构化输出
  └→ 询问是否保存到 Registry
```

---

## 5. API 设计

### 5.1 CLI 接口

```bash
# 单句模式
intent-os ask "帮我总结这段文本"
intent-os ask "分析代码性能" --message "def foo(): pass"
intent-os ask "翻译成英文" --input-file article.txt

# 交互模式
intent-os ask
> 帮我分析这篇文章的情绪
> ...
```

### 5.2 AskSession 类

```python
class AskSession:
    """
    自然语言交互会话。

    管理多轮对话、上下文积累、用户偏好。

    典型用法:
        session = AskSession(registry, executor, llm_provider)
        result = session.process("帮我总结这篇文章")
        session.process("不对，用 OpenAI")
    """

    def __init__(self, registry, executor, llm_provider=None):
        self._registry = registry
        self._executor = executor
        self._history: list[dict] = []
        self._context: dict = {}  # 当前会话上下文
        self._preferences: dict = {}  # 用户偏好（跨会话）

    def process(self, user_input: str) -> AskResult:
        """处理一条用户输入，返回执行结果。"""
        # 1. 解析意图
        intent = self._parse_intent(user_input)
        # 2. 匹配 Manifest
        manifest = self._resolve_manifest(intent)
        # 3. 提取参数
        params = self._extract_params(intent, manifest)
        # 4. 安全检查
        self._check_security(manifest, params)
        # 5. 执行
        record = self._execute(manifest, params)
        # 6. 呈现
        return AskResult(record=record, summary=self._summarize(record))

    def _parse_intent(self, text: str) -> Intent:
        """LLM 调用: 自然语言 → 结构化意图。"""

    def _resolve_manifest(self, intent: Intent) -> CapabilityManifest:
        """Registry 搜索 → 未找到则 LLM 生成 → 注册。"""

    def _extract_params(self, intent: Intent, manifest: CapabilityManifest) -> dict:
        """LLM 调用: 从自然语言 + Manifest Schema 提取参数。"""

    def _summarize(self, record: ExecutionRecord) -> str:
        """LLM 调用: 把结果翻译成自然语言。"""
```

---

## 6. 提示词设计

### 6.1 意图分类器 Prompt

```
你是一个 Intent OS 的自然语言解释器。
用户输入自然语言，你需要输出结构化的执行意图。

可用的能力清单:
{registry.search("") 返回的所有 Manifest 名称和描述}

输出 JSON:
{
  "action": "run" | "registry" | "security" | "evolution" | "other",
  "capability_name": "text_summarize" | null,
  "confidence": 0.0-1.0,
  "description_match": "用户意图的描述",
  "input_fields": {提取到的输入参数},
  "preferred_adapter": "ollama" | "openai" | null,
  "missing_info": ["还需要哪些信息"]
}

如果用户没有指定 adapter，preferred_adapter 为 null。
如果多个 Manifest 可能匹配，confidence 最高的那个。
confidence < 0.5 时，需要追问用户。
```

### 6.2 Manifest 生成器 Prompt

```
你是一个 Intent OS 的 Capability Manifest 设计师。
用户描述了一个能力，但 Registry 中没有匹配的 Manifest。
请根据用户描述创建一个新的 Manifest。

Manifest 格式:
kind: Capability
metadata:
  name: {snake_case_name}
  version: "1.0.0"
  publisher: "generated"
  description: "{一句话描述}"
  tags: ["generated", ...]
spec:
  input:
    {field_name}:
      type: string | integer | number | boolean | array | object
      description: "{字段说明}"
      optional: true | false
  output:
    {field_name}:
      type: string | ...
      description: "{字段说明}"
  security:
    risk: low | medium | high | critical

只输出有效的 YAML，不要额外说明。
```

### 6.3 参数提取器 Prompt

```
用户说: {user_input}
用到的 Manifest: {manifest YAML}

根据 Manifest 的 input_schema，从用户输入中提取参数值。
Manifest 的输入字段: {manifest.input_schema}

输出 JSON:
{
  "input_data": {按 output_schema 提取的值},
  "missing_fields": ["缺少的用户输入字段"],
  "questions_for_user": ["追问问题"]
}
```

### 6.4 结果总结器 Prompt

```
执行结果: {ExecutionRecord JSON}

用自然语言总结这个结果，让用户能理解发生了什么。
包含:
- 使用了什么能力
- 用了什么模型
- 花费多少时间和成本
- 输出的主要内容摘要（不要输出完整结果，太长了）

控制在 3-5 句话以内。
```

---

## 7. LLM Provider 设计

### 7.1 为什么需要 Provider 抽象

Intent OS 本身就是一个"跨 Runtime"层。`intent-os ask` 需要的 LLM 调用也应该支持多种 Provider——用户可以选 Ollama（免费、离线）、OpenAI、Anthropic。

### 7.2 Provider 接口

```python
class LLMProvider(ABC):
    """LLM 调用抽象，支持多种 Provider。"""

    @abstractmethod
    def chat(self, messages: list[dict], **kwargs) -> str:
        """发送对话，返回文本。"""
        pass

    @abstractmethod
    def chat_json(self, messages: list[dict], **kwargs) -> dict:
        """发送对话，返回 JSON（structured output）。"""
        pass


class OllamaProvider(LLMProvider):
    """通过 Ollama API 调用本地模型。"""

class OpenAIProvider(LLMProvider):
    """通过 OpenAI API 调用。"""

class AnthropicProvider(LLMProvider):
    """通过 Anthropic API 调用。"""
```

### 7.3 降级策略

```
用户没有 API Key → Ollama 本地模型（需要 ollama serve）
用户有 OpenAI Key → GPT-4o-mini（便宜 + 够用）
用户有 Anthropic Key → Claude Sonnet（更高质量）
都没装 → 提示用户至少安装一个 Provider
```

---

## 8. 记忆层

### 8.1 偏好存储

```sql
-- 用户偏好表
CREATE TABLE user_preferences (
    key   TEXT PRIMARY KEY,  -- 'default_adapter', 'last_manifest', 'output_style'
    value TEXT NOT NULL
);

-- 对话历史表
CREATE TABLE conversation_history (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id  TEXT NOT NULL,
    role        TEXT NOT NULL,  -- 'user' | 'assistant' | 'system'
    content     TEXT NOT NULL,
    timestamp   TEXT NOT NULL DEFAULT (datetime('now')),
    metadata    TEXT  -- JSON, 包含 intent/params/result 等
);
```

### 8.2 自动学习的偏好

| 偏好 | 从什么推断 | 例子 |
|---|---|---|
| `default_adapter` | 用户连续 3 次指定同一 adapter | "用 OpenAI" × 3 → 默认用 OpenAI |
| `output_style` | 用户要求的格式 | "简洁一点" → verbose=False |
| `frequent_capabilities` | 高频使用的 Manifest | 自动放到搜索结果的顶部 |

---

## 9. 最小可行版本 (MVP) 范围

### 9.1 MVP 包含

- [x] `intent-os ask "..."` 单句模式
- [x] LLM Provider 抽象（Ollama + OpenAI）
- [x] 意图解析（分类 + Manifest 匹配）
- [x] 参数提取
- [x] 执行 + 结果返回
- [x] 用户偏好持久化
- [x] 安全性：低风险能力自动放行，高风险要求确认

### 9.2 MVP 不包含

- [ ] 多轮对话（只做单句 + adapter 切换）
- [ ] LLM 自动生成 Manifest（找不到就报错 + 引导用户创建）
- [ ] 交互式会话（`intent-os ask` 无参数模式）
- [ ] Web UI

### 9.3 用户场景覆盖

```
MVP 能做的事:
  ✅ "总结这篇文章" → 已有 Manifest → 执行 → 返回
  ✅ "翻译成英文" → 已有 Manifest → 执行 → 返回
  ✅ "分析情绪" → 已有 Manifest → 执行 → 返回
  ✅ "用 OpenAI 重新跑" → 切换 adapter → 重新执行
  ✅ "搜索能力库里的翻译工具" → registry search → 展示

MVP 做不了的事:
  ❌ "帮我做一个简历匹配器" → 需要新 Manifest → MVP 报错
  ❌ "先分析再翻译" → 工作流组合 → MVP 不支持
  ❌ 对话历史超过 5 轮 → MVP 不做长期记忆
```

---

## 10. 文件结构

```
reference-runtime/
├── core/
│   ├── ask.py              # AskSession + Intent + AskResult
│   ├── llm_provider.py     # LLMProvider 接口 + 实现
│   └── ask_preferences.py  # 用户偏好管理
│
├── commands/
│   └── ask.py              # "ask" CLI 命令
│
├── tests/
│   └── test_ask.py         # Ask 模块测试
│
└── prompts/
    ├── intent_classifier.md    # 意图分类 Prompt
    ├── manifest_generator.md   # Manifest 生成 Prompt
    ├── param_extractor.md      # 参数提取 Prompt
    └── result_summarizer.md    # 结果总结 Prompt
```

---

## 11. 与现有系统的集成

| 已有组件 | 集成方式 | 是否需要修改 |
|---|---|---|
| **Registry + 语义搜索** | AskSession 搜索 Manifest | 不用改 |
| **Executor** | AskSession 调 executor.execute() | 不用改 |
| **SecurityManager** | 执行前安全检查 | 不用改 |
| **AnalyticsEngine** | 记录 Ask 执行的统计数据 | 不改，自动记录 |
| **CLI 框架** | 添加 ask 子命令 | 改 cli.py |
| **pyproject.toml** | LLM Provider 需要 httpx 等依赖 | 需要添加 optional deps |
| **EventType** | 可以添加 ASK_EXECUTED 事件 | 可选 |
| **.env.example** | 新增 LLM_PROVIDER、ASK_DEFAULT_ADAPTER | 改 .env.example |

---

## 12. 版本规划

```
v0.4.0 ─ MVP（单句 + Ollama/OpenAI + 已存在 Manifest）
  ↓
v0.5.0 ─ 交互模式 + Manifest 自动生成
  ↓
v0.6.0 ─ 多轮对话 + 偏好学习 + Web UI
```
