# Code Review

Analyzes source code for bugs, security vulnerabilities, style issues, and provides a structured review report.

```yaml
kind: Capability
metadata:
  name: code_review
  version: 1.0.0
  publisher: intent-os.org
  description: "Analyzes source code for bugs, security vulnerabilities, style issues"
  tags: [code-analysis, security, review, static-analysis]
```

## Input

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `code` | string | Yes | Source code to review |
| `language` | string | No | Programming language (auto-detected if omitted) |

## Output

| Field | Type | Description |
|-------|------|-------------|
| `issues` | array | List of found issues with severity and line numbers |
| `summary` | string | Overall assessment of code quality |
| `score` | number | Code quality score (0.0 to 10.0) |

## Examples

```bash
intent-os run code_review -p code="def add(a,b): return a+b"
```
