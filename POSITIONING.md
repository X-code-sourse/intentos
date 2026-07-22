# Intent OS — Positioning Statement

> **Version:** v1.0 (Frozen)
> **Status:** Architecture Freeze — Phase 0 Engineering
> **Last updated:** 2026-07-21

---

## 1. One-Sentence Definition

**Intent OS is an open interoperability layer for AI capabilities, workflows, and execution.**

It enables AI capabilities and workflows to be described once, discovered, composed, and executed across different AI runtimes — without modification.

> 中文：Intent OS 是一个开放的 AI 互操作层，使 AI 能力和工作流能够被一次描述，并在不同 AI Runtime 中发现、组合和执行。

---

## 2. Why Intent OS Exists

### The Core Problem

**The growth rate of AI capabilities has exceeded the growth rate of AI capability coordination.**

Over the past few years:
- **Models** have become dramatically more powerful: GPT → Claude → Gemini → DeepSeek
- **Tools** have proliferated: Browser → Code Executor → Search → Database → Enterprise APIs
- **Agents** have grown in complexity: Coding Agents → Research Agents → Data Agents → Business Agents

But a single capability — say, `financial_research` — must be rewritten for every platform: Claude's Tool Schema, OpenAI's Function Calling, Hermes' Skill system, Cursor's Plugin system. **This is unsustainable duplication.**

### The Deeper Problem: Execution Semantic Fragmentation

MCP has already solved "tool mobility" — a tool can be called across platforms through the MCP protocol. But after the tool moves, the real question emerges:

> **Who manages the lifecycle? What happens on failure? How are capabilities composed? How is execution recorded?**

Consider the same workflow (Task A → Task B → Task C) when Task B fails:

| Runtime | Behavior |
|---|---|
| Runtime A | Retry B with exponential backoff |
| Runtime B | Skip B, continue with C |
| Runtime C | Rollback A, abort the entire workflow |

These are no longer the same workflow.

The real enemy is not **Tool Fragmentation** — it is **Execution Semantic Fragmentation**. AI capabilities lack a **portable execution contract** across runtimes.

### The Five Specific Problems

| # | Problem | Manifestation | Intent OS Solution |
|---|---|---|---|
| 1 | **Capability Fragmentation** | Same capability written N times for N platforms | Capability Manifest — unified description language |
| 2 | **Workflow Lock-in** | Orchestration tied to one runtime, cannot migrate | Workflow Spec — structure + semantics separated |
| 3 | **Runtime Lock-in** | Users bound to a specific Agent platform | Common Execution Model via Adapter layer |
| 4 | **Engineering Gap** | Agents lack logs, trace, audit, cost tracking | Event System — unified execution record layer |
| 5 | **Ecosystem Void** | No "npm for AI capabilities" | Registry + Marketplace (Phase 2) |

---

## 3. The Historical Analogy

Every computing era has produced an infrastructure layer to solve that era's coordination problem:

| Era | Problem | Answer | Result |
|---|---|---|---|
| 1980s-90s | How do programs run on different hardware? | **POSIX** | Unix/Linux ecosystem |
| 1990s-2000s | How does information flow between machines? | **HTTP + HTML + JSON** | Web ecosystem |
| 2010s | How do applications deploy across environments? | **OCI + Kubernetes** | Cloud Native ecosystem |
| **2020s** | **How do AI capabilities collaborate across platforms?** | **Intent OS** | **To be built** |

**Intent OS does not claim to be "the Linux of AI."** A more precise formulation:

> Intent OS aims to provide the interoperability layer that POSIX, OCI, and Kubernetes provided for previous computing eras — adapted for the unique challenges of AI capabilities.

| Historical Layer | Intent OS Equivalent |
|---|---|
| POSIX syscall interface | Capability Contract |
| OCI image specification | Capability Packaging |
| Kubernetes API / execution model | Workflow Execution Model |

---

## 4. Core Principle

> **Intent OS does not standardize intelligence. It standardizes interaction.**

This is the project's firewall. Every design decision is tested against this principle.

Intent OS does **not** specify:
- Which model to use (GPT, Claude, Gemini, or future models)
- How to write prompts
- How to reason or think
- The quality of model outputs

Intent OS **only** specifies:
- How capabilities describe themselves
- How capabilities are combined
- How capabilities are executed
- How capabilities communicate
- How execution is recorded

---

## 5. Operating Principles

### Principle 1: Spec First, Runtime Second

The Reference Runtime is the **first proof** of the Spec — not its owner. The Spec belongs to the ecosystem, not to any single implementation.

### Principle 2: Compatibility Before Replacement

Intent OS is not a replacement for OpenAI, Anthropic, or Google. It is a **common layer above them**. It does not ask developers to migrate platforms — it makes existing platforms interoperable.

### Principle 3: What We Don't Do Is More Important Than What We Do

**Intent OS is NOT:**
- ❌ A new large language model — not an OpenAI competitor
- ❌ An Agent Framework — not a LangChain replacement
- ❌ An AI application — not a personal assistant or automation tool
- ❌ A closed platform — does not require developers to migrate

**Intent OS IS:**
- ✅ A common description language for AI capabilities
- ✅ A common execution model for AI workflows
- ✅ A compatibility layer between AI runtimes

---

## 6. Why Now

Three conditions have converged simultaneously:

1. **Models are capable enough** — Agents are no longer experimental; they are becoming a **new software paradigm**
2. **Agents are proliferating** (2024-2026) — Claude Code, Codex, Cursor, Devin, OpenHands, and the MCP ecosystem all demonstrate that mass adoption is underway
3. **Standards have not yet formed** — MCP has standardized the **connection layer** (AI ↔ Tool), but the **execution layer** (Capability → Workflow → Execution → Event) is still empty. This is the window.

---

## 7. Core Thesis (Falsifiable Hypothesis)

> **If Runtime A and Runtime B share the same Manifest format and basic execution model, then the same AI Capability can be executed across runtimes.**

This is a hypothesis that can be proven **or** disproven. Phase 0 exists to test it.

---

## 8. What Success Looks Like

### Phase 0 Success Criteria (4-Level Compatibility)

| # | Criterion | Meaning | Verification |
|---|---|---|---|
| 1 | **Schema Compatibility** | Both runtimes can parse the same Manifest | No parse errors |
| 2 | **Capability Compatibility** | Both runtimes can execute the same Capability | Returns results for same input |
| 3 | **Semantic Contract Compatibility** | Output satisfies the Manifest's output_schema | Structure conforms to contract |
| 4 | **Execution Record Compatibility** | Both runtimes produce the same Event format | Fields/metrics/events match schemas |

**Not**: identical output text (AI is probabilistic — GPT and Claude will never produce identical text for the same input).

### Ten-Year Vision

> When a developer creates a new AI capability, their first thought should be to write an **Intent OS Manifest** — just as naturally as writing an OpenAPI specification for an API.

If, ten years from now:
- Claude can run it
- OpenAI can run it
- Cursor can run it
- Future new runtimes can run it

Then Intent OS will have achieved the same kind of ecosystem influence as JSON, OpenAPI, or OCI.

---

## 9. The Ecosystem Analogy

| Layer | Traditional Software | AI Software |
|---|---|---|
| **Application** | App | AI Application |
| **Orchestration** | Kubernetes | Workflow Engine |
| **Packaging** | OCI / Docker | Capability Manifest |
| **Interface** | POSIX / syscall | Capability Contract |
| **Runtime** | OS Kernel | Adapter Layer |
| **Hardware** | CPU / Memory / Disk | Models + Tools |

---

## 10. Relationship with MCP

> **MCP standardizes Connection (AI ↔ Tool). Intent OS standardizes Execution (Capability → Workflow → Event).**

| Dimension | MCP | Intent OS |
|---|---|---|
| Problem Solved | AI ↔ Tool protocol | Capability ↔ Capability / Workflow interoperability |
| Standardizes | Tool interface | Capability + Workflow + Execution + Event |
| Relationship | **Complementary** | **Complementary** |

Intent OS Runtime can consume MCP servers as Capability Providers. They are not competitors.

---

## 11. Final Positioning Statement

> **Intent OS is not built to create another AI platform. It is built to give all future AI platforms a common language, a common execution model, and an ecosystem of freely portable capabilities.**
