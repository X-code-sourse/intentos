<p align="center">
  <h1 align="center">Intent OS</h1>
  <p align="center"><strong>The flight recorder for AI coding agents.</strong></p>
  <p align="center">See exactly what your AI agent did, why it failed, and how much it cost.</p>
</p>

<p align="center">
  <a href="https://pypi.org/project/intentos/"><img src="https://img.shields.io/badge/pip-install%20intentos-blue?style=flat&logo=python" alt="pip install"></a>
  <a href="https://x-code-sourse.github.io/intentos/"><img src="https://img.shields.io/badge/docs-intent--os.org-blue?style=flat" alt="Docs"></a>
  <a href="https://github.com/X-code-sourse/intentos/blob/main/LICENSE"><img src="https://img.shields.io/badge/license-AGPLv3-blue?style=flat" alt="License"></a>
</p>

---

```bash
pip install intentos
intent-os demo --auto
```

---

## What is this?

AI coding agents (Claude Code, Cursor, Copilot, etc.) are black boxes. You tell them to do something, they do it, and you have no idea what happened.

**Intent OS records everything your agent does.** Every model call, every tool invocation, every file change, every failure — captured as a structured execution trace.

```bash
# See what the last agent run did
intent-os inspect latest

# Export as a shareable HTML file
intent-os inspect latest --html
```

Example output:

```
[OK]  Goal:        refactor-auth-to-jwt
     Runtime:    anthropic (AnthropicAdapter)
     Duration:   14,327ms
     Cost:       $0.0842
     Tokens:     4,891
     Error:      Tests failed: 2 passed, 1 failed

[14:02:01] > START (planner)
[14:02:06] > INVOKE (adapter) -- 2451 tokens
[14:02:08] OK DONE  (3241ms)
[14:02:09] > INVOKE (adapter) model=claude-sonnet-4
[14:02:14] OK DONE  (5824ms)
[14:02:15] > INVOKE (adapter) run-tests
[14:02:27] !! FAIL  (12713ms) -- reason="test_jwt_verify failed"
```

---

## Quick Start

```bash
# Install
pip install intentos

# Run the demo
intent-os demo --auto

# Run a capability and trace it
intent-os run translate -p text="Hello world" -p target_lang=zh

# See the trace
intent-os inspect latest

# Export as HTML
intent-os inspect latest --html
```

---

## Why?

Modern AI agents touch your codebase, call language models, modify files, and make decisions — but they leave no audit trail. When something breaks:

- **What did the agent actually do?**
- **Which model did it call?**
- **How much did it cost?**
- **Why did it fail?**

Intent OS answers these questions. It's the debugger and flight recorder that AI agents don't have built-in.

---

## Use Cases

| You're using... | Intent OS gives you... |
|----------------|----------------------|
| Claude Code / Cursor | Full trace of every agent action |
| Custom AI agents | Audit trail for compliance and debugging |
| AI-powered CI/CD | Cost tracking and failure analysis |
| Multi-model pipelines | Cross-runtime comparison |

---

## Architecture

```
Agent
  |
Intent OS Runtime
  ├── Manifest Parser (SPEC-0001)
  ├── Execution Engine
  ├── Security Manager (SPEC-0004)
  └── Event Store (SPEC-0003)
        |
        ├── inspect
        ├── cost
        └── audit
```

Intent OS is more than a flight recorder — it's an **agent operating layer** with security policies, cross-runtime execution, cost models, and workflow orchestration. But the flight recorder is where you start.

[See full documentation →](https://x-code-sourse.github.io/intentos/)

---

## Commands

```bash
intent-os inspect <trace-id>     # Show an execution trace
intent-os inspect latest          # Show the most recent trace
intent-os inspect latest --html   # Export as HTML
intent-os run <capability> [...]  # Run a capability
intent-os demo                    # Interactive demo
intent-os ask "..."               # Natural language execution
```

---

## License

AGPLv3 + Commercial Option. See [LICENSE](LICENSE).

- **Personal / open-source use**: free (AGPLv3)
- **Commercial use**: requires a commercial license

---

*Built by one person, for every developer who's asked "what did my agent just do?"*
