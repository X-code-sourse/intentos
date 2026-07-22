# SPEC-0002: Workflow Graph

> **Status:** Draft v0.1 — Phase 0 (Structure) / Phase 1 (Execution Semantics)
> **Scope:** Defines the format for composing capabilities into executable workflows
> **Editor:** Intent OS Project

---

## 1. Purpose

The Workflow Graph Spec defines how AI capabilities are **composed into executable workflows**. It answers two questions:

> **Structure:** How are capabilities connected? (topology, data flow, dependencies)
> **Execution Semantics:** How does the workflow behave during execution? (retry, failure, compensation, parallel control)

This spec is split into two sub-specs because two runtimes can share the same DAG topology but execute it with completely different behaviors. True workflow portability requires **both** structure **and** semantics to be standardized.

---

## 2. Design Principles

### P1: Declarative, Not Imperative

A Workflow Graph declares **what** should happen, not **how** the runtime should execute it. The runtime chooses the concrete execution strategy within the constraints defined by the Execution Semantics.

### P2: Portable by Construction

A Workflow Graph shall have a single deterministic interpretation regardless of the runtime executing it. Two runtimes executing the same Graph with the same input shall produce:
- The same task completion order (topological)
- The same behavior on failure (semantic)
- The same structure of execution record (event)

### P3: Execution Semantics Are Part of the Contract

A Workflow Graph is not fully specified by its DAG alone. The Execution Semantics define the behavioral contract that makes workflows truly portable.

---

## 3. Workflow Structure Spec

### 3.1 Top-Level Structure

```yaml
kind: Workflow
metadata:
  name: string               # Required. Unique workflow name
  version: string             # Required. Semantic versioning
  description: string         # Recommended. Human-readable description

spec:
  goal: string                # Optional. Human-readable goal description
  
  tasks:                      # Required. At least one task
    - id: string              # Required. Unique task ID within workflow
      capability: string      # Required. Reference to Capability Manifest
      input: map              # Required. Input mapping

  edges:                      # Required. Defines data and control flow
    - from: string            # Required. Source task ID
      to: string              # Required. Target task ID
      data: map               # Optional. Data mapping between tasks

  semantics:                  # Required. Execution behavior contract
    # (See Section 4 - Execution Semantics Spec)
```

### 3.2 Tasks

Each task references a Capability Manifest and provides its input.

```yaml
tasks:
  - id: search
    capability: web_search
    input:
      query: "${goal.query}"
      max_results: 10

  - id: analyze
    capability: text_analyze
    input:
      text: "${search.results[0].content}"

  - id: report
    capability: report_generate
    input:
      analysis: "${analyze.result}"
```

**Input mapping syntax:**
- Static values: `max_results: 10`
- Variable references: `${task_id.field.subfield}`
- The variable context includes all preceding tasks' outputs

### 3.3 Edges

Edges define the dependency and data flow between tasks.

```yaml
edges:
  - from: search
    to: analyze
    data:
      text: "${search.results[0].content}"

  - from: analyze
    to: report
    data:
      analysis: "${analyze.result}"
```

**Implicit edges:** If task B's input references task A's output (`${A.field}`), an implicit edge is created. Explicit edges can declare additional dependencies (e.g., control-only dependencies with no data flow).

### 3.4 Graph Structure Rules

1. The task graph MUST be a DAG (Directed Acyclic Graph)
2. Every task MUST have a path from a root task (no inbound edges, or all bindings static)
3. Every task MUST have a path to a terminal task (no outbound edges)
4. Task IDs MUST be unique within a workflow
5. Variable references MUST refer to task IDs that appear earlier in the graph (topologically)
6. Self-referencing edges are FORBIDDEN

---

## 4. Execution Semantics Spec

This is the sub-spec that makes workflows **truly portable**. Without it, two runtimes can parse the same DAG but exhibit different runtime behavior.

### 4.1 Top-Level Structure

```yaml
semantics:
  retry: RetryPolicy              # How failures are retried
  timeout: TimeoutPolicy           # How timeouts are handled
  failure: FailurePolicy           # How failures propagate
  parallel: ParallelPolicy         # How parallel execution is controlled
  lifecycle: LifecyclePolicy       # Task lifecycle behavior
  compensation: CompensationPolicy # How compensation actions work (Phase 2+)
  checkpoint: CheckpointPolicy     # State persistence (Phase 2+)
```

### 4.2 Retry Policy

```yaml
semantics:
  retry:
    strategy: exponential           # fixed | exponential | none
    max_attempts: 3                 # Maximum retry attempts (default: 3)
    initial_interval: 1s            # Initial retry interval (default: 1s)
    max_interval: 30s               # Maximum retry interval (default: 30s)
    backoff_multiplier: 2           # Multiplier for exponential backoff (default: 2)
    retryable_errors:
      - timeout
      - rate_limit
      - server_error
      - unavailable
```

**Strategies:**
- `fixed`: Retry at a fixed interval (`initial_interval`)
- `exponential`: Retry with exponential backoff: `interval * multiplier^attempt`
- `none`: No retry — fail immediately

**Default** (if omitted):
```yaml
retry:
  strategy: exponential
  max_attempts: 3
  initial_interval: 1s
  max_interval: 30s
  backoff_multiplier: 2
  retryable_errors:
    - timeout
    - rate_limit
    - server_error
```

### 4.3 Timeout Policy

```yaml
semantics:
  timeout:
    task: 30s                       # Per-task timeout (default: 30s)
    workflow: 300s                  # Total workflow timeout (default: 300s)
    on_timeout: fail                # fail | skip | retry
    retry_on_timeout: true          # Whether to retry on timeout (default: true)
```

**Default** (if omitted):
```yaml
timeout:
  task: 30s
  workflow: 300s
  on_timeout: fail
  retry_on_timeout: true
```

### 4.4 Failure Policy

```yaml
semantics:
  failure:
    propagation: immediate          # immediate | deferred | none
    on_failure:                     # Behavior when a task fails
      - cancel_dependents           # Cancel tasks that depend on the failed task
      - continue_independents       # Continue tasks that don't depend on failed task
    max_failures: 1                 # Max task failures before workflow fails
```

**Propagation modes:**
- `immediate`: Cancel all downstream tasks and fail the workflow when any task fails (after retries exhausted). **Most restrictive.**
- `deferred`: Continue executing tasks that don't depend on the failed task; only fail the workflow if the output is unrecoverable.
- `none`: Record the failure but continue all other tasks. The workflow's final output will indicate which tasks failed.

**Default** (if omitted):
```yaml
failure:
  propagation: deferred
  on_failure:
    - cancel_dependents
    - continue_independents
  max_failures: 1
```

### 4.5 Parallel Policy

```yaml
semantics:
  parallel:
    max_concurrency: 0              # 0 = unlimited (default: 0)
    strategy: task_parallel          # task_parallel | sequential
    merge_strategy: collect          # collect | merge | first_complete
```

**Strategies:**
- `task_parallel`: Tasks at the same topological level run in parallel (subject to `max_concurrency`)
- `sequential`: Tasks run one at a time, even if no dependency exists

**Merge strategies** (for fan-in to a single task):
- `collect`: All outputs are collected into an array
- `merge`: Outputs are merged into a single object (keyed by source task ID)
- `first_complete`: Only the first completed output is passed; others are discarded

**Default** (if omitted):
```yaml
parallel:
  max_concurrency: 0
  strategy: task_parallel
  merge_strategy: collect
```

### 4.6 Lifecycle Policy

```yaml
semantics:
  lifecycle:
    task_init: on_demand             # on_demand | eager
    cleanup: on_complete             # on_complete | never
    caching: allowed                 # allowed | disabled
```

**Task init:**
- `on_demand`: Tasks are initialized only when ready to execute (conserves resources)
- `eager`: Tasks are initialized as soon as the workflow starts (faster execution at higher cost)

**Default** (if omitted):
```yaml
lifecycle:
  task_init: on_demand
  cleanup: on_complete
  caching: allowed
```

### 4.7 Compensation Policy (Phase 2+)

```yaml
semantics:
  compensation:
    strategy: rollback               # rollback | compensate | none
    action: "${task.compensate}"     # Compensation capability reference
    order: reverse                    # forward | reverse (reverse = last failed, first compensated)
```

Reserved for Phase 2+ when workflows support compensatory actions for rollback.

### 4.8 Checkpoint Policy (Phase 2+)

```yaml
semantics:
  checkpoint:
    interval: task                   # task | step | never
    store: event_store               # event_store | persistent_volume
    resume: auto                     # auto | manual
```

Reserved for Phase 2+ when workflows support long-running execution with failure recovery.

---

## 5. Complete Examples

### 5.1 Simple Linear Workflow

```yaml
kind: Workflow
metadata:
  name: summarize_article
  version: 1.0.0
  description: "Fetch and summarize a web article"

spec:
  goal: "Summarize a web article by URL"

  tasks:
    - id: fetch
      capability: web_page_fetch
      input:
        url: "${goal.url}"

    - id: summarize
      capability: text_summarize
      input:
        text: "${fetch.content}"

  edges:
    - from: fetch
      to: summarize

  semantics:
    retry:
      strategy: exponential
      max_attempts: 3
    timeout:
      task: 60s
    failure:
      propagation: immediate
    parallel:
      strategy: sequential
    lifecycle:
      task_init: on_demand
```

### 5.2 Fan-Out Research Workflow

```yaml
kind: Workflow
metadata:
  name: company_research
  version: 1.0.0
  description: "Research a company from multiple angles"

spec:
  goal: "Research a company and produce an investment report"

  tasks:
    - id: search_news
      capability: web_search
      input:
        query: "${goal.company_name} ${goal.year} news"
        max_results: 20

    - id: financial_data
      capability: financial_data_query
      input:
        ticker: "${goal.ticker}"

    - id: competitor_check
      capability: web_search
      input:
        query: "${goal.company_name} competitors analysis"
        max_results: 10

    - id: synthesize
      capability: research_synthesize
      input:
        news: "${search_news.results}"
        financials: "${financial_data.statements}"
        competitors: "${competitor_check.results}"

    - id: report
      capability: report_generate
      input:
        synthesis: "${synthesize.report}"

  edges:
    - from: search_news
      to: synthesize
    - from: financial_data
      to: synthesize
    - from: competitor_check
      to: synthesize
    - from: synthesize
      to: report

  semantics:
    retry:
      strategy: exponential
      max_attempts: 3
      initial_interval: 2s

    timeout:
      task: 120s
      workflow: 600s

    failure:
      propagation: deferred
      on_failure:
        - cancel_dependents
        - continue_independents
      max_failures: 1

    parallel:
      max_concurrency: 3
      strategy: task_parallel
      merge_strategy: collect

    lifecycle:
      caching: allowed
```

---

## 6. Semantic Equivalence

Two Workflow Graphs are semantically equivalent if and only if:

1. **Structural equivalence:** Same task set, same edge topology, same data bindings
2. **Semantic equivalence:** Same retry policy, timeout policy, failure policy, parallel policy, and lifecycle policy produce the same observable behavior

Runtime A and Runtime B both compliant with this Spec MUST produce the same observable behavior for the same Workflow Graph under the same conditions (same input, same capability implementations).

---

## 7. Validation Rules

### 7.1 Required Fields
- `kind` — must equal "Workflow"
- `metadata.name`
- `metadata.version`
- `spec.tasks` — at least one task
- `spec.semantics` — all top-level semantic fields have valid defaults if omitted

### 7.2 Graph Validation

1. **Acyclicity**: The graph must contain no cycles. Use topological sort to verify.
2. **Reachability**: Every task must be reachable from at least one root task.
3. **Terminal reachability**: Every task must reach at least one terminal task.
4. **Data flow consistency**: All variable references in task inputs must resolve to valid preceding task outputs.
5. **Schema compatibility**: Each task's input must conform to its referenced Capability Manifest's `spec.input`.

---

## 8. Versioning

Workflow versioning follows the same conventions as Capability versioning (SPEC-0001, Section 6).

Additionally:
- Changes to `spec.semantics` that restrict behavior (e.g., reducing max_attempts) are MINOR
- Changes to `spec.semantics` that broaden behavior are MAJOR if they could affect existing consumers
- Structural changes (tasks, edges) that change the set of possible execution paths are MAJOR

---

## 9. Future Extensions (Phase 2+)

| Extension | Description | Phase |
|---|---|---|
| **Conditional branches** | if/else or switch based on task output | Phase 2 |
| **Loops/iteration** | Execute subgraph N times with dynamic input | Phase 2 |
| **Dynamic task generation** | Tasks created at runtime based on prior output | Phase 2 |
| **Nested workflows** | Workflow as a task within another workflow | Phase 2 |
| **Human review gates** | Workflow pauses for human approval at checkpoint | Phase 2 |
| **Cost budgets** | Enforce per-workflow or per-task cost limits | Phase 2 |
| **Data flow schemas** | Typed data flow with transformation functions | Phase 3 |

---

## 10. References

- Directed Acyclic Graph (DAG) theory — for topological ordering
- Kubernetes Controllers — for declarative state management patterns
- Workflow Management Systems (e.g., Temporal, Airflow) — for execution semantics inspiration
- Database transaction semantics — for failure and compensation patterns
