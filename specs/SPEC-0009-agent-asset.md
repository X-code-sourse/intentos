# SPEC-0009: Agent Asset Model

> **Status:** Frozen v1.0
> **Phase:** Phase B — Agent Portable Package
> **对应代码:** v0.7.0
> **作者:** Intent OS Project

---

## 1. Purpose

Define the standardized data model for an **Agent Asset** — the portable representation of an AI agent as a digital entity with identity, personality, capabilities, experience, and reputation.

This spec formalizes the "Agent as a Person" concept: a different agent is a different person. An agent's asset can be created, enriched through execution, exported as a ``.agent`` file, and imported on any runtime.

---

## 2. Agent Profile Fields

An Agent Profile represents **who this agent is** — its identity, role, and character. It is the foundational layer of the Agent Asset.

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `agent_id` | string | yes | Unique identifier (`agent_<8hex>`) |
| `name` | string | yes | Human-readable name |
| `persona` | string | no | Role description — who this agent IS (e.g. "Financial analyst focused on SEC filings") |
| `traits` | string[] | no | Behavioural characteristics (e.g. `["cautious", "analytical"]`) |
| `avatar` | string | no | Emoji or icon representing this agent |
| `description` | string | no | Free-text description |
| `owner` | string | no | User ID or email who owns this agent |
| `capabilities` | string[] | no | Registered capability references |
| `status` | enum | yes | `active` | `paused` | `revoked` |
| `created_at` | ISO 8601 | yes | When the agent was created |
| `last_seen_at` | ISO 8601 | no | Last execution timestamp |

### 2.1 Traits

Traits are free-form short strings. They are intentionally not constrained to an enum — different roles need different trait vocabularies.

**Examples:**
- Professional: `cautious`, `analytical`, `detail-oriented`, `creative`
- Role-based: `technical`, `financial`, `legal`, `medical`
- Communication: `concise`, `verbose`, `formal`, `casual`

### 2.2 Persona vs Description

| | Persona | Description |
|---|---|---|
| Purpose | Role identity — WHO the agent is | Summary — WHAT the agent does |
| Example | "Financial analyst focused on SEC filings" | "Analyzes quarterly reports" |
| Used in | Character card, agent selection, profile | Agent list, search |
| Tone | Role-defining | Functional |

---

## 3. Reputation Summary

An agent's reputation is derived from its execution history. It is a computed summary, never raw execution data.

| Field | Type | Source |
|-------|------|--------|
| `total_executions` | integer | Event Store (execution_records) |
| `success_rate` | float (0.0–1.0) | Successful / Total |
| `total_cost_usd` | float | Sum of all execution costs |
| `total_tokens` | integer | Sum of all execution tokens |
| `avg_cost_per_run` | float | total_cost / total_executions |
| `preferred_models` | string[] | Most-used models from execution records |

---

## 4. Agent Asset Package (.agent)

The ``.agent`` format is the portable packaging format for an Intent OS agent. It bundles identity, reputation summary, and experiences into a single JSON file.

### 4.1 Format Overview

| Property | Value |
|----------|-------|
| File extension | `.agent` |
| MIME type | `application/json` (de facto) |
| Serialization | JSON (UTF-8) |
| spec_version | `"1.0"` |
| format | `"intent-os-agent-v1"` |

### 4.2 JSON Schema

```json
{
  "spec_version": "1.0",
  "format": "intent-os-agent-v1",
  "exported_at": "2026-07-24T12:00:00Z",
  "identity": {
    "agent_id": "agent_a82f91c3",
    "name": "Financial Analyst",
    "persona": "Financial analyst focused on SEC filings",
    "traits": ["cautious", "analytical"],
    "avatar": ":chart:",
    "owner": "hai@example.com",
    "capabilities": ["market_data_read", "report_generate"],
    "created_at": "2026-07-20T14:02:01",
    "last_seen_at": "2026-07-24T09:15:32"
  },
  "reputation": {
    "total_executions": 47,
    "success_rate": 0.89,
    "total_cost_usd": 12.34,
    "total_tokens": 485000,
    "avg_cost_per_run": 0.26,
    "preferred_models": ["claude-sonnet-4", "gpt-4o"]
  },
  "experiences": [
    {
      "type": "failure_pattern",
      "observation": "Rate limit when querying EDGAR during market open",
      "recommendation": "Queue requests during 9:30-10:00 ET",
      "confidence": 0.85
    }
  ]
}
```

### 4.3 Field Descriptions

**Top-level:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `spec_version` | string | yes | Schema version. Current: `"1.0"` |
| `format` | string | yes | Fixed `"intent-os-agent-v1"` |
| `exported_at` | ISO 8601 | yes | When the package was generated |
| `identity` | object | yes | Agent identity (Section 2 fields, minus `status`) |
| `reputation` | object | yes | Computed execution summary (Section 3) |
| `experiences` | array | yes | List of experience entries (may be empty) |

**Experience entry:**

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `type` | string | yes | One of: `failure_pattern`, `success_strategy`, `tool_preference`, `model_performance`, `data_source_reliability`, `environment_constraint`, `user_feedback` |
| `observation` | string | yes | What was observed |
| `recommendation` | string | no | Suggested action |
| `confidence` | float | no | Confidence (0.0–1.0) |

### 4.4 What Is NOT Included

For privacy and portability, the following are intentionally excluded:

- Raw execution records (prompts, responses, tool calls)
- API keys, tokens, or credentials
- Evidence data (claims, source references)
- Event store data (individual events, metrics)
- Runtime-specific fields (model names are included only in `preferred_models` summary)

### 4.5 Design Rationale

- **JSON not YAML**: Zero-dependency parsing across all languages. `json.load()` is a standard library function in Python, JavaScript, Go, Rust, etc.
- **Single file not directory**: Can be emailed, attached to GitHub releases, copied via USB.
- **Summary not full data**: An agent package represents the agent's *identity and knowledge*, not its raw execution log.

---

## 5. Export / Import Behaviour

### 5.1 Export (`intent-os agent export <id>`)

1. Read agent identity from AgentStore (SQLite)
2. Read experiences from ExperienceStore (up to 50 most recent)
3. Compute reputation from execution_records (EventStore)
4. Assemble into `.agent` JSON file
5. Agent is not deleted or modified by export

### 5.2 Import (`intent-os agent import <path.agent>`)

1. Validate `spec_version` (must be `"1.0"`) and `format` (must be `"intent-os-agent-v1"`)
2. Generate a **new** `agent_id` — never reuses the original (prevents conflicts)
3. Create agent via AgentStore with identity fields
4. Import experiences via ExperienceStore (deduplicated by observation text)
5. Write IDENTITY.yaml to filesystem (`~/.intent-os/agents/<new_id>/`)
6. Original `agent_id` is preserved in the `identity` section for provenance

### 5.3 What the User Can Do With a .agent File

- Copy to another machine → import
- Edit the JSON → import as a modified version of the agent
- Archive (store as a backup)
- Share with another team member → they import and get the same agent profile
- Attach to a GitHub issue or release

---

## 6. Lifecycle

```
Create (agent create --persona --traits)
    │
    ▼
Enrich (proxy start --agent → execution data accumulates)
    │
    ▼
Update (agent update --traits +newtrait --persona "...")
    │
    ▼
Export (agent export → .agent file)
    │
    ▼
Transport (copy, email, attach to GitHub)
    │
    ▼
Import (agent import → new machine, new agent_id)
    │
    ▼
Run (agent now has identity and experience on new machine)
```

---

## 7. Design Constraints

- **Agent Profile is Metadata Plane** — Identity data, not Control Plane state. CONSTITUTION R1 does not apply.
- **No user-preference memory** — An Agent is a person/role, not a "preference store." Role-specific memory belongs to the agent type, not the universal spec.
- **Traits are free-form** — Not constrained to an enum.
- **Reputation is computed** — Derived from Event Store, never stored as a static value.
- **Backward compatibility** — Existing agents without persona/traits/avatar default to empty strings.
- **Privacy by design** — Agent packages contain only identity + summary. No raw execution data.
- **No encryption in format** — Transport security is the user's responsibility (e.g., encrypted USB, HTTPS download).

---

## 8. Future Work

- Cross-Runtime Agent Identity — agent profiles consumed natively by Claude, Codex, OpenClaw
- Agent Discovery — registry-based agent asset search
- Signed agent packages (Ed25519) for trust verification
- Incremental export (delta updates)
