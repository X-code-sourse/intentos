# SPEC-0003: Event Schema

> **Status:** Draft v0.1 — Phase 0
> **Scope:** Standard format for recording and describing AI execution events
> **Editor:** Intent OS Project

---

## 1. Purpose

The Event Schema defines a **standard format for recording execution events** from AI capability and workflow execution. It answers one question:

> **What happened during execution?**

Events serve two distinct but interconnected roles:

1. **Observability** — debugging, tracing, auditing, cost analysis, and monitoring in real time
2. **Learning Backbone** — accumulating execution history that feeds the Planner's Cost Model, Evolution Loop, and system optimization

The Event System is not "just logging." It is the **data flywheel** that enables Intent OS to evolve from a static interpreter into a self-optimizing execution infrastructure.

---

## 2. Design Principles

### P1: Structure, Not Content

Events record the **structure and outcome** of execution — not the content of capability inputs and outputs. They answer "what happened" and "what was the result," not "what was said." Full input/output payloads are recorded as references, not inline, to avoid ballooning event stores with model response data.

### P2: Traceable

All events from a single execution (capability invocation, workflow run, or job) share a common `trace_id`. This enables full reconstruction of the execution path from a single entry point.

### P3: Comparable

Two runtimes executing the same capability with the same input MUST produce events with the same structure, the same event types, and the same metric dimensions. The *values* of metrics (latency, cost) may differ by runtime, but the *schema* of the event MUST be identical.

### P4: Append-Only

Events are immutable records of what happened. They are written once and never modified. Corrections are recorded as new events (e.g., `EstimateCorrected`).

---

## 3. Event Types

### 3.1 Core Event Types

| Event Type | When Emitted | Payload |
|---|---|---|
| `TaskStarted` | A task begins execution | task_id, capability_ref, input_ref, timestamp |
| `CapabilityInvoked` | A capability is called (a task is executed) | task_id, capability_ref, input_ref, runtime_id, model_used |
| `TaskCompleted` | A task completes successfully | task_id, output_ref, latency_ms, token_count, cost_usd |
| `TaskFailed` | A task fails | task_id, error_type, error_message, attempt_number |
| `TaskRetried` | A failed task is retried | task_id, attempt_number, backoff_ms, retry_reason |
| `TaskSkipped` | A task is skipped (failure policy) | task_id, reason |
| `TaskCancelled` | A task is cancelled | task_id, cancel_reason |
| `WorkflowStarted` | A workflow begins | workflow_id, goal, task_count |
| `WorkflowCompleted` | A workflow completes | workflow_id, status, total_latency, total_cost |
| `WorkflowFailed` | A workflow fails | workflow_id, failed_task_id, failure_chain |
| `CostAccumulated` | Periodic cost update | task_id, accumulated_cost, token_count |
| `ReviewRequired` | Task requires human review | task_id, reason, review_token |
| `ReviewCompleted` | Human review is complete | task_id, approved, reviewer, feedback |

### 3.2 System Events (Infrastructure)

| Event Type | When Emitted | Payload |
|---|---|---|
| `RuntimeRegistered` | A new runtime adapter is registered | runtime_id, name, version |
| `CapabilityRegistered` | A capability is registered | capability_id, name, version |
| `PolicyEvaluated` | A security/execution policy is checked | policy_id, task_id, result, reason |
| `ResourceWarning` | Token/rate/cost limit approaching | resource_type, current, limit, threshold |

### 3.3 Optimization Events (Phase 1+)

| Event Type | When Emitted | Payload |
|---|---|---|
| `PlanGenerated` | A Planner generates an execution plan | plan_id, goal_id, plan_graph_ref, estimated_cost |
| `PlanDeviation` | Execution deviates from plan | plan_id, deviation_type, actual_vs_expected |
| `SuggestionGenerated` | Evolution Loop suggests a change | suggestion_id, target, evidence, confidence |
| `SuggestionAccepted` | A suggestion is accepted by human reviewer | suggestion_id, reviewer |
| `SuggestionRejected` | A suggestion is rejected | suggestion_id, reviewer, reason |

---

## 4. Event Record Structure

### 4.1 Common Fields

Every event has the following mandatory fields:

```yaml
event:
  spec_version: "1.0"               # Event Schema version
  trace_id: uuid                    # Execution trace identifier
  event_id: uuid                    # Unique event identifier
  event_type: string                # From the event type taxonomy
  timestamp: ISO8601                # Event occurrence time
  source: string                    # Component that emitted the event (e.g., "executor", "planner")
  sequence: integer                 # Monotonic sequence within trace

  # Execution context (present on all task-level events)
  workflow_id: uuid | null          # Parent workflow identifier
  task_id: string | null            # Task identifier within workflow
  capability: string | null         # Capability identifier (name@version)

  # Runtime context
  runtime: string                   # Runtime identifier (e.g., "openai", "anthropic")
  adapter_version: string           # Adapter version

  payload: map                      # Event-specific data (see Section 5)
  metrics: map | null               # Performance metrics (see Section 6)
```

### 4.2 Event ID Uniqueness

Each `event_id` MUST be globally unique. UUID v4 is the RECOMMENDED format.

### 4.3 Trace ID

The `trace_id` is the single identifier that links all events from a single execution root (capability invocation or workflow run). It MUST be propagated to all child events.

---

## 5. Payload Schemas by Event Type

### 5.1 TaskStarted

```yaml
payload:
  task_id: string
  capability: string                 # name@version
  input_ref: string                  # Reference to input record (URI or hash)
  depends_on: string[]               # Task IDs this task depends on
```

### 5.2 CapabilityInvoked

```yaml
payload:
  task_id: string
  capability: string
  runtime_id: string                 # Which runtime adapter was selected
  model_used: string                 # Which model was actually used
  input_schema_version: string       # Version of the input schema used
  adapter_parameters:                # Parameters passed to the adapter
    model: string
    max_tokens: integer
    temperature: number | null
  input_truncated: boolean           # Whether input was truncated due to context limits
```

### 5.3 TaskCompleted

```yaml
payload:
  task_id: string
  output_ref: string                 # Reference to output record
  output_schema_valid: boolean       # Whether output conformed to Manifest schema
  latency_ms: integer
  token_count:
    input: integer
    output: integer
    total: integer
  cost_usd: number
  attempt: integer                   # Which attempt succeeded (1 = first)
```

### 5.4 TaskFailed

```yaml
payload:
  task_id: string
  error_type: string                 # "timeout" | "rate_limit" | "server_error" |
                                      # "schema_mismatch" | "permission_denied" |
                                      # "capability_not_found" | "tool_unavailable" |
                                      # "model_unavailable" | "unknown"
  error_message: string
  error_code: string | null          # Provider-specific error code
  attempt: integer                   # Which attempt failed
  retry_allowed: boolean             # Whether retry is possible
  recovery_action: string | null     # "retry" | "skip" | "cancel" | "compensate"
```

### 5.5 TaskRetried

```yaml
payload:
  task_id: string
  attempt: integer                   # The retry attempt number
  previous_attempt: integer          # Which attempt preceded this retry
  backoff_ms: integer                # How long we waited before retrying
  retry_reason: string               # Why the retry was triggered
```

### 5.6 WorkflowStarted

```yaml
payload:
  workflow_id: string
  workflow_name: string
  workflow_version: string
  goal: string                       # The user's original goal
  task_count: integer                # Number of tasks in the workflow
  semantic_hash: string              # Hash of the Execution Semantics in effect
```

### 5.7 WorkflowCompleted

```yaml
payload:
  workflow_id: string
  status: "success" | "partial" | "degraded"
  total_latency_ms: integer
  total_cost_usd: number
  total_tokens: integer
  tasks_succeeded: integer
  tasks_failed: integer
  tasks_skipped: integer
  tasks_retried: integer
  semantic_hash: string
```

### 5.8 WorkflowFailed

```yaml
payload:
  workflow_id: string
  failed_task_id: string
  failure_chain:                     # Chain of failures leading to workflow failure
    - task_id: string
      error_type: string
      error_message: string
  total_cost_usd: number
  total_latency_ms: integer
  compensation_action: string | null # What compensation was taken, if any
```

---

## 6. Metrics Schema

Metrics are present on events that represent execution outcomes (TaskCompleted, TaskFailed, WorkflowCompleted).

```yaml
metrics:
  latency_ms: integer               # Wall-clock execution time
  token_count:
    input: integer
    output: integer
    total: integer
  cost_usd: number                  # Estimated execution cost
  retry_count: integer              # Number of retries performed
  cache_hit: boolean | null         # Whether result was served from cache
  data_transfer_bytes: integer | null  # Data transferred (for tool calls)
```

---

## 7. Event Stream Format

Events are typically transmitted as a sequence of JSON objects, one per line (JSON Lines format).

```
{"event_type": "WorkflowStarted", "trace_id": "abc-123", "timestamp": "...", ...}
{"event_type": "TaskStarted", "trace_id": "abc-123", "task_id": "search", ...}
{"event_type": "CapabilityInvoked", "trace_id": "abc-123", "task_id": "search", ...}
{"event_type": "TaskCompleted", "trace_id": "abc-123", "task_id": "search", ...}
{"event_type": "TaskStarted", "trace_id": "abc-123", "task_id": "analyze", ...}
{"event_type": "WorkflowCompleted", "trace_id": "abc-123", ...}
```

### 7.1 Execution Record (Complete Bundle)

For Phase 0, a complete Execution Record bundles the event stream with metadata:

```yaml
execution_record:
  spec_version: "1.0"
  trace_id: uuid
  
  manifest:
    kind: "Capability" | "Workflow"
    name: string
    version: string
  
  runtime:
    id: string
    adapter: string
    adapter_version: string
  
  input: any                         # Original input (may be a reference in production)
  output: any                        # Final output (may be a reference in production)
  
  events: Event[]                    # The event stream
  metrics:                           # Aggregated metrics
    total_latency_ms: integer
    total_cost_usd: number
    total_tokens: integer
    was_retried: boolean
    error_count: integer
  
  status: "success" | "failure" | "partial"
```

---

## 8. Event Bus Architecture (Internal)

The Event Bus is the communication backbone of the Intent OS runtime. All Planes communicate through it.

```
┌──────────┐     ┌──────────┐     ┌──────────┐
│  Control │     │ Metadata │     │ Runtime  │
│  Plane   │────▶│  Plane   │────▶│  Plane   │
└──────────┘     └──────────┘     └──────────┘
      │               │               │
      └───────────────┼───────────────┘
                      │
                      ▼
                 Event Bus
                      │
                      ▼
              ┌──────────────┐
              │   Data Plane │
              │ (Event Store)│
              └──────────────┘
```

### 8.1 Bus Properties

1. **Ordered**: Events from a single trace are delivered in sequence order
2. **Durable**: Events are persisted before being consumed
3. **Observable**: The Event Bus itself is observable — its throughput and latency are monitored
4. **Decoupled**: Producers and consumers do not know about each other

---

## 9. Validation Rules

### 9.1 Required Fields

Every event MUST include:
- `spec_version`, `trace_id`, `event_id`, `event_type`, `timestamp`, `source`, `sequence`
- At least one of: `workflow_id`, `task_id`, or `capability`

### 9.2 Type Constraints

- `trace_id` and `event_id` MUST be valid UUIDs (v4)
- `timestamp` MUST be ISO 8601 with timezone
- `sequence` MUST be a monotonically increasing integer within a trace
- `metrics.latency_ms` MUST be non-negative if present
- `metrics.cost_usd` MUST be non-negative if present

### 9.3 Sequence Constraints

Within a single trace:
- `TaskStarted` MUST precede `CapabilityInvoked` for the same task
- `TaskCompleted` or `TaskFailed` MUST follow `CapabilityInvoked`
- `WorkflowCompleted` MUST be the last event for a workflow trace
- `TaskRetried` MUST follow `TaskFailed` and precede the next `TaskStarted` for the same task

---

## 10. Event Store (Phase 2+)

The Event Store is the long-term persistence layer for events. It enables:

- **Replay**: Reconstruct the exact execution path of any past execution
- **Analytics**: Query execution patterns, cost trends, failure modes
- **Cost Model Training**: Feed historical execution data into the Planner's Cost Model
- **Audit**: Compliance and governance review of AI system behavior

```
Event Store Schema (Phase 2+):

TABLE events:
  trace_id      UUID        PRIMARY KEY
  sequence      INTEGER     PRIMARY KEY
  event_type    VARCHAR(50)
  timestamp     TIMESTAMPTZ
  payload       JSONB
  metrics       JSONB

TABLE execution_records:
  trace_id      UUID        PRIMARY KEY
  manifest_id   VARCHAR(255)
  runtime       VARCHAR(50)
  status        VARCHAR(20)
  total_cost    DECIMAL(10,6)
  total_latency INTEGER
  created_at    TIMESTAMPTZ
```

---

## 11. Phase 0 Implementation

In Phase 0, the Event System is minimal:

1. Events are written to stdout/stderr as JSON Lines
2. Execution Records are saved to disk as JSON files
3. No Event Store, no queries, no analytics
4. The focus is on **Event format compatibility** — proving that two runtimes produce the same event structure

### Phase 0 Compatibility Verification

```
Event Record from Runtime A:
  trace_id: "abc-123"
  events:
    - type: "TaskStarted"
    - type: "CapabilityInvoked"
    - type: "TaskCompleted"
  metrics:
    latency_ms: 3200
    cost_usd: 0.04

Event Record from Runtime B:
  trace_id: "def-456"
  events:
    - type: "TaskStarted"
    - type: "CapabilityInvoked"
    - type: "TaskCompleted"
  metrics:
    latency_ms: 1800
    cost_usd: 0.02

→ Both records have the same event type sequence
→ Both records have the same metric dimensions
→ Different values (expected — runtimes have different performance)
```

---

## 12. Future Extensions

| Extension | Description | Phase |
|---|---|---|
| **Event Store** | Durable, queryable event storage | Phase 2 |
| **Event Stream Processing** | Real-time analysis of event streams | Phase 2 |
| **Cost Model Feed** | Events automatically feed Planner's Cost Model | Phase 3 |
| **Anomaly Detection** | Automatic detection of execution anomalies | Phase 3 |
| **Audit Trail** | Immutable, verifiable event chain for compliance | Phase 3 |
| **Federated Events** | Cross-registry event sharing | Phase 4 |

---

## 13. References

- CloudEvents — event format inspiration
- OpenTelemetry — trace and span concepts
- JSON Lines — event stream serialization format
- Apache Kafka / AWS Kinesis — event bus architecture patterns
- Database query logs — the analogy for Cost Model training data
