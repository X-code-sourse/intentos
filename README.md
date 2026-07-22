# Intent OS

> **An open interoperability layer for AI capabilities, workflows, and execution.**

Intent OS defines a common model for describing, composing, and executing AI capabilities across different AI runtimes. It is not a new model, not a framework, not a platform — it is the **interoperability layer** that AI needs to evolve from isolated capabilities into an open ecosystem.

## Why Intent OS

AI capabilities are growing exponentially — but the infrastructure for them to work together is still fragmented. A research capability written for Claude cannot run on OpenAI. A workflow built in Codex cannot migrate to Cursor. Developers rewrite the same capability for every platform.

Intent OS solves this by defining:

- **Capability Manifest** — a standard way to describe what an AI capability is, what it needs, and what it produces
- **Workflow Graph** — a standard way to compose capabilities into executable workflows with portable execution semantics
- **Event Schema** — a standard way to record what happened during execution

## Core Principle

> **Intent OS does not standardize intelligence. It standardizes interaction.**

It does not specify which model to use, how to write prompts, or how to reason. It specifies how capabilities describe themselves, how they are composed, how they are executed, and how they communicate.

## Project Status

**Current Phase: Phase 0 — Interoperability Verification**

We are proving that a single Capability Manifest can be parsed, loaded, and executed across two different runtimes, producing a comparable Execution Record.

## Repository Structure

```
intent-os/
├── README.md                       # This file
├── POSITIONING.md                  # Strategic positioning document
├── CONSTITUTION.md                 # Core principles and hard constraints
├── ROADMAP.md                      # Evolution roadmap (Phase 0 → Phase 4)
│
├── specs/
│   ├── SPEC-0001-capability-manifest.md    # Capability description format
│   ├── SPEC-0002-workflow-graph.md         # Workflow structure + execution semantics
│   └── SPEC-0003-event-schema.md           # Execution event format
│
├── schemas/                        # JSON/YAML schemas for Spec validation
│
├── reference-runtime/              # Reference implementation
│   ├── core/                       # Core runtime engine
│   └── adapters/                   # Runtime adapters (OpenAI, Anthropic, etc.)
│
├── examples/
│   └── hello-capability/           # First demo: text_summarize
│
└── tests/
    └── compatibility/              # Compatibility test suite (future)
```

## Quick Start (Phase 0)

```bash
# Clone the repository
git clone https://github.com/intent-os/intent-os.git

# Write a Capability Manifest
cat > my-capability.yaml << 'EOF'
kind: Capability
metadata:
  name: text_summarize
  version: 1.0.0
  publisher: example.ai
spec:
  input:
    text: string
  output:
    summary: string
  requirements:
    models: ["gpt-4", "claude-3"]
EOF

# Run on OpenAI
intent-os run my-capability.yaml --adapter openai \
  --input '{"text": "Long article text..."}'

# Run on Claude (same Manifest)
intent-os run my-capability.yaml --adapter anthropic \
  --input '{"text": "Long article text..."}'
```

## The Five Problems We Solve

| # | Problem | Manifestation | Intent OS Solution |
|---|---|---|---|
| 1 | **Capability Fragmentation** | Same capability rewritten for N platforms | Capability Manifest — unified description |
| 2 | **Workflow Lock-in** | Orchestration logic tied to one runtime | Workflow Spec — portable execution model |
| 3 | **Runtime Lock-in** | Users locked into a single platform | Common Execution Model via Adapters |
| 4 | **Engineering Gap** | No logs, trace, audit, or cost tracking | Event System — unified execution records |
| 5 | **Ecosystem Void** | No "npm for AI capabilities" | Registry + Marketplace (Phase 2) |

## How It Works

```
            AI Applications
                  |
          Workflow Orchestration
                  |
    ┌──────────────────────────────┐
    │     Intent OS Common Model     │
    │  ┌────────┐┌──────┐┌──────┐  │
    │  │Capabili││Workfl││Event │  │
    │  │ty Spec ││ow Sp ││Spec  │  │
    │  └────────┘└──────┘└──────┘  │
    │  + Execution Model + Registry │
    └──────────────────────────────┘
                  |
        Runtime Implementation Layer
    ┌────────┬─────────┬────────────┐
    │OpenAI  │Anthropic│ MCP / Other│
    │Adapter │Adapter  │ Adapter    │
    └────────┴─────────┴────────────┘
                  |
            Models + Tools
```

## Relationship with Other Projects

| Project | What It Solves | Relationship with Intent OS |
|---|---|---|
| **MCP** | Standardizes AI ↔ Tool connection | **Complementary**. Intent OS can consume MCP servers as Capability Providers |
| **OpenAI / Anthropic** | Provide models and basic agent capabilities | **Lower layer**. Intent OS provides a common execution layer above them |
| **LangChain** | Simplifies LLM invocation and orchestration | **Compatible**. Intent OS Runtime can use them as underlying implementation |
| **Kubernetes** | Orchestrates containers | **Different layer**. K8s manages compute, Intent OS manages AI capabilities |

## Evolution Path

```
Phase 0: AI Interoperability Layer    ← now
    ↓ (capabilities begin to flow)
Phase 1: AI Capability Marketplace
    ↓ (enough capabilities exist)
Phase 2: AI Execution Graph
    ↓ (execution records accumulate)
Phase 3: AI Query Engine
    ↓ (planner has data to optimize)
Phase 4: Self-optimizing AI Computing Infrastructure
```

## Vision

> When a developer creates a new AI capability, their first thought should be to write an **Intent OS Manifest** — just as naturally as writing an OpenAPI specification for an API.

## License

Copyright (C) 2026 Intent OS Project

Intent OS is licensed under the **GNU Affero General Public License v3.0 (AGPLv3)**.

**For individuals and non-commercial use:** Free. Use, modify, and distribute under AGPLv3 terms.

**For commercial use:** If you integrate Intent OS into a proprietary product or use it as part of a commercial service without releasing your modifications, you must obtain a commercial license. Contact the project maintainer for details.

This dual-licensing model ensures Intent OS remains open and free for the community while enabling sustainable commercial development.
