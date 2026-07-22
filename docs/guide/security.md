# Security & Policies

Intent OS includes a policy engine that controls which capabilities can execute on your system, based on their declared risk level and your organizational policies.

---

## Risk Levels

Every capability declares a security risk level in its manifest:

| Level | Example Capabilities | Default Action |
|-------|--------------------|----------------|
| `low` | Translation, summarization | Allow |
| `medium` | Web search, data extraction | Allow |
| `high` | Code execution, file modification | Require review |
| `critical` | System configuration, deployment | Block |

## Applying a Policy

```bash
# Apply a development policy
intent-os security policy apply examples/policies/development.yaml

# Evaluate a capability against policies (dry run)
intent-os security evaluate examples/code_review.yaml

# View audit log
intent-os security audit
```

## Policy YAML Format

```yaml
kind: SecurityPolicy
metadata:
  name: development-policy
  description: "Default policy for local development"
spec:
  rules:
    - risk: low
      decision: allow
    - risk: medium
      decision: allow
    - risk: high
      decision: require_review
    - risk: critical
      decision: deny
  defaults:
    decision: deny
```

## Policy Decisions

| Decision | Meaning |
|----------|---------|
| `allow` | Execution proceeds without interruption |
| `deny` | Execution is blocked, error returned |
| `require_review` | Execution is paused, user must approve |
