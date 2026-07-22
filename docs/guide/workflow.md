# Composing Workflows

Workflows let you chain multiple capabilities together into a directed acyclic graph (DAG) with conditional branching, retry logic, and failure propagation.

---

## Workflow YAML

```yaml
kind: Workflow
metadata:
  name: research_and_report
  version: 1.0.0
  description: "Research a topic, analyze findings, and generate a report"

spec:
  tasks:
    - id: search
      capability: web_search
      input:
        query: "{{goal}}"

    - id: analyze
      capability: text_analyze
      depends_on: [search]
      input:
        text: "{{search.results}}"
      conditions:
        - if: "search.result_count > 0"
          status: run
        - else:
          status: skip

    - id: summarize
      capability: text_summarize
      depends_on: [analyze]
      input:
        text: "{{analyze.result}}"

    - id: report
      capability: report_generate
      depends_on: [summarize]
      input:
        content: "{{summarize.summary}}"

  execution:
    max_retries: 2
    retry_delay: 5
    failure_strategy: abort
```

---

## Running a Workflow

```bash
intent-os workflow run examples/research_workflow.yaml --input '{"goal": "research AI trends"}'
```

## Planning a Workflow from a Goal

```bash
intent-os workflow plan "research AI trends and summarize findings"
```

## Execution Semantics

| Parameter | Values | Default | Description |
|-----------|--------|---------|-------------|
| `failure_strategy` | `abort`, `skip`, `retry` | `abort` | What happens when a task fails |
| `max_retries` | integer | `0` | Maximum retry attempts per task |
| `retry_delay` | seconds | `0` | Delay before retry |
| `timeout` | seconds | `300` | Task timeout |

## Conditions DSL

```yaml
conditions:
  - if: "task_count > 0"
    status: run
  - if: "confidence > 0.8"
    status: run
  - else:
    status: skip
```

Supported operators: `>`, `<`, `==`, `>=`, `<=`, `!=`, `exists`, `in`, `contains`
