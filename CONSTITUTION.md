# Intent OS — Constitution

> **Version:** v1.0
> **Status:** Frozen — All design decisions and constraints documented here are binding
> **Last updated:** 2026-07-21

---

## Preamble

This document records the hard constraints, inviolable principles, and architectural decisions that govern the Intent OS project. It serves as the project's constitutional layer — above any single Spec, RFC, or implementation.

---

## Article I: Identity

### Section 1: What Intent OS Is

Intent OS is an **open interoperability layer for AI capabilities, workflows, and execution**. It exists to solve the problem that AI capabilities cannot freely move, combine, and collaborate across different runtimes.

### Section 2: What Intent OS Is Not

The following are permanently outside Intent OS's scope:

| Out of Scope | Rationale |
|---|---|
| A new large language model | Intent OS does not compete with model providers |
| An Agent Framework (e.g., LangChain replacement) | Intent OS standardizes inter-operation, not intra-operation |
| An AI application (e.g., chatbot, assistant) | Intent OS is infrastructure, not a product |
| A closed platform | Intent OS Specs belong to the ecosystem, not to any entity |
| A Prompt optimization framework | Prompt quality is outside Intent OS's concern |

### Section 3: Core Principle (The Firewall)

> **Intent OS does not standardize intelligence. It standardizes interaction.**

Every design decision shall be tested against this principle. Any proposal that attempts to standardize intelligence — model choice, prompt content, reasoning method, output quality — shall be rejected unless it can be re-framed as standardizing interaction.

---

## Article II: Architecture

### Section 1: Five-Plane Architecture

Intent OS's internal architecture consists of five Planes, all communicating through a shared Event Bus:

```
┌──────────────────────────────────┐
│ User Plane                       │
│ Goal / Intent                    │
│ Natural language → structured    │
└──────────────┬───────────────────┘
               │ Event Bus
┌──────────────▼───────────────────┐
│ Control Plane                    │
│ Planner, Execution Engine        │
│ Rule Manager, Security Manager   │
│                                  │
│ ⚠️ HARD RULE: Control Plane      │
│    OWNS NO STATE                 │
└──────────────┬───────────────────┘
               │ Event Bus
┌──────────────▼───────────────────┐
│ Metadata Plane                   │
│ Capability / Workflow / Model    │
│ Registries, Version Management   │
└──────────────┬───────────────────┘
┌──────────────▼───────────────────┐
│ Data Plane                       │
│ Event Store, Knowledge, Memory   │
│ Execution History, Experience    │
└──────────────┬───────────────────┘
┌──────────────▼───────────────────┐
│ Runtime Plane                    │
│ Capability / Model / Tool Pools  │
│ Reviewer                         │
└──────────────────────────────────┘
```

### Section 2: Hard Constraints (Red Lines)

The following architectural constraints are inviolable:

**R1: Control Plane Owns No State**
Control Plane components (Planner, Execution Engine, Rule Manager) shall never store state locally. All execution state flows through the Event Bus to the Data Plane. This is a prerequisite for:
- Distributed deployment
- High availability
- Deterministic replay
- Independent scaling of control vs. data

**R2: No Direct Inter-Processor Communication**
Processors (Capability, Model, Tool) shall never communicate directly with each other. All communication must go through the Scheduler within the Control Plane. This ensures:
- Observability of all interactions
- Consistent policy enforcement
- Ability to intercept, log, and replay

**R3: Event Bus is the Single Source of Truth**
All state changes — task state transitions, capability invocations, failures, costs — must be recorded as Events. There is no other authoritative record of system state.

**R4: Capabilities are Stateless**
A Capability instance shall not maintain internal state between invocations. Stateful contexts are managed by the Context Manager (Data Plane), not by the capability itself.

---

## Article III: Spec Governance

### Section 1: Spec Hierarchy

```
SPEC-0001: Capability Manifest    [Phase 0]
SPEC-0002: Workflow Graph         [Phase 1]
  ├── Workflow Structure Spec
  └── Execution Semantics Spec
SPEC-0003: Event Schema           [Phase 1]
SPEC-0004: Security Model         [Phase 2 — placeholder]
```

### Section 2: Spec Principles

**P1 — Spec First, Runtime Second**
The Reference Runtime is the first proof of a Spec, not its owner. Specs evolve through community consensus, not implementation convenience.

**P2 — Backward Compatibility**
No version of a Spec shall break forward compatibility without a major version increment and a documented migration path.

**P3 — Minimal Surface**
Specs shall specify the minimum necessary to achieve interoperability. Anything that can be left to implementation choice shall be left to implementation choice.

**P4 — All Specs Must be Testable**
Every claim in a Spec must be verifiable through a defined test. "Compliance" is a testable property, not a marketing claim.

---

## Article IV: Algorithm Priority

### Section 1: Priority Hierarchy

```
Tier 1 — Phase 0 Essential (★★★★★)
  1. Capability Registry + Manifest Parsing
  2. Execution Model — Capability Invocation
  3. Event System — Execution Record Generation

Tier 2 — Phase 1+ (★★★★☆)
  4. Workflow Planner
  5. Evolution Loop
```

### Section 2: Phase Boundaries

**Phase 0 shall NOT implement:**
- Workflow Planner (no execution history to optimize against)
- Evolution Loop (no data to learn from)
- Capability Marketplace (no ecosystem yet)
- Security Model implementation (design placeholder only)
- Any user-facing UI

**Reasoning:** These components depend on data that does not exist until interoperability is proven. Building them before Phase 0 would violate the principle: **Do not design systems for data that does not yet exist.**

---

## Article V: Phase 0 — Interoperability Verification

### Section 1: Thesis

> If Runtime A and Runtime B share the same Manifest format and basic execution model, the same AI Capability can be executed across runtimes.

This is a falsifiable hypothesis. Phase 0 exists to test it.

### Section 2: Success Criteria (4-Level Compatibility)

| Level | Criterion | What It Tests |
|---|---|---|
| L1 | **Schema Compatibility** | Both runtimes parse the same Manifest |
| L2 | **Capability Compatibility** | Both runtimes execute the same Capability |
| L3 | **Semantic Contract Compatibility** | Output satisfies the declared schema contract |
| L4 | **Execution Record Compatibility** | Both runtimes produce Events in the same format |

All four levels must pass for Phase 0 to be considered successful.

### Section 3: What Phase 0 Does NOT Prove

- Not proving identical output (AI is probabilistic)
- Not proving optimal performance
- Not proving production readiness
- Not proving ecosystem adoption

Phase 0 proves only one thing: **AI capability interoperability is a working engineering fact.**

---

## Article VI: Data-Driven Evolution

### Section 1: The Evolution Sequence

Intent OS shall evolve through a specific sequence that mirrors the natural generation of data:

```
Interoperability (Phase 0)
    ↓ generates execution data
Capability Marketplace (Phase 1)
    ↓ generates capability relationship data
Execution Graph (Phase 2)
    ↓ generates workflow pattern data
Query Engine (Phase 3)
    ↓ generates optimization data
Self-optimizing Infrastructure (Phase 4)
```

### Section 2: Anti-Patterns

The following are recognized anti-patterns that shall be avoided:

- **Designing for data that does not exist** — e.g., building an optimizer before there are execution records to optimize against
- **Skipping interoperability** — moving directly to Marketplace or Optimization before capabilities can flow
- **Platform nationalism** — favoring one runtime over another in Spec design
- **Over-standardization** — specifying how intelligence works rather than how capabilities interact

---

## Article VII: Ecosystem Strategy

### Section 1: Cold Start Strategy

Intent OS shall not wait for ecosystem adoption. It shall bridge existing ecosystems through:

```
import openai-function ./my_tool.json   → Capability Manifest
import mcp-server http://...            → Capability Manifest
export --format openai ./manifest.yaml  → Export to non-compatible runtimes
```

### Section 2: True Moat

The project's durable competitive advantage comes from three layers, in order:

1. **Reference Runtime** — the lightest, most stable, best-documented implementation
2. **Compatibility Test Suite** — "Intent OS compatible" must be a verifiable claim
3. **Capability Registry** — the accumulation of capabilities creates network effects

Specs can be copied. Execution data cannot.

---

## Article VIII: Relationship with MCP

The following position is fixed and shall be used in all public communications:

> **MCP standardizes Connection (AI ↔ Tool). Intent OS standardizes Execution (Capability → Workflow → Event). They are complementary. Intent OS Runtime can consume MCP servers as Capability Providers.**

---

## Article IX: Amendment Process

This Constitution may be amended only through:

1. A documented proposal describing the change and its rationale
2. Evidence that the current constraint is blocking a demonstrated need
3. A review period of no less than 14 days
4. Consensus among active maintainers

Amendments to Article I (Identity), Article II Section 2 (Hard Constraints), and Article III (Spec Governance) require supermajority approval (>2/3 of active maintainers).

---

*This Constitution is a living document but changes shall not be made lightly. Its purpose is to preserve the project's identity through the pressure of engineering reality.*
