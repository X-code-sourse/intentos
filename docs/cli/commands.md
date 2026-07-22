# CLI Reference

Intent OS provides 16 CLI commands organized into five categories.

---

## Global Flags

```bash
intent-os --help        # Show help
intent-os --version     # Show version (0.4.0)
```

---

## Basic Commands

### `validate`

Validate a Capability Manifest YAML file.

```bash
intent-os validate <manifest.yaml>
intent-os validate examples/translate.yaml
```

### `run`

Execute a capability on a runtime.

```bash
intent-os run <manifest.yaml | capability-name> [text] [options]

# Options:
  --adapter, -a       Runtime adapter (openai, anthropic, ollama)
  --input, -i         Input JSON string
  --input-file, -f    Input JSON file
  --param, -p         Input parameter as key=value (repeatable)
  --output, -o        Save execution record to file
  --save, -s          Save execution record path

# Examples:
  intent-os run translate -p text="Hello" -p target_lang=zh
  intent-os run translate "Hello world" -p target_lang=zh
  intent-os run ../examples/translate.yaml --input '{"text":"Hello"}'
```

### `compare`

Execute the same capability on all available adapters and compare results.

```bash
intent-os compare <manifest.yaml> [options]

# Options:
  --input, -i    Input JSON string
  --save, -s     Directory to save records

# Example:
  intent-os compare examples/translate.yaml --input '{"text":"hello","target_lang":"fr"}'
```

### `list`

List available adapters and registered capabilities.

```bash
intent-os list
```

---

## Management Commands

### `registry`

Manage the capability registry.

```bash
intent-os registry list                          # List all capabilities
intent-os registry get <name>                    # Get capability details
intent-os registry register <manifest.yaml>      # Register a capability
intent-os registry unregister <name>             # Unregister a capability
intent-os registry search <query>                # Semantic search
intent-os registry export <output.json>          # Export registry
```

### `security`

Manage security policies and evaluation.

```bash
intent-os security policy list              # List all policies
intent-os security policy get <name>        # Get policy details
intent-os security policy apply <file.yaml> # Apply a policy
intent-os security evaluate <manifest.yaml> # Evaluate capability
intent-os security audit                    # Export compliance report
```

### `event`

Query execution events.

```bash
intent-os event list                         # Event store statistics
intent-os event trace <trace-id>             # View events for a trace
intent-os event query [--trace-id] [--event-type] [--capability]
                     [--runtime] [--limit]
```

### `analytics`

Analyze execution history.

```bash
intent-os analytics summary           # Overall summary
intent-os analytics capabilities     # Capability rankings
intent-os analytics runtimes         # Runtime comparison
intent-os analytics failures         # Failure analysis
intent-os analytics trends           # Cost trends
intent-os analytics suggestions      # Optimization suggestions
intent-os analytics export           # Export cost model data
```

---

## Workflow Commands

### `workflow`

Plan, run, and optimize workflows.

```bash
intent-os workflow run <file.yaml>        # Execute a workflow
intent-os workflow plan <goal>            # Plan from a goal
intent-os workflow optimize <goal>        # Multi-plan optimization

# Options (for run):
  --input, -i     Input JSON
  --adapter, -a   Runtime adapter
  --simulate      Force simulated execution
```

---

## Ecosystem Commands

### `import`

Import a capability from an external format.

```bash
intent-os import openai-function <file.json>
intent-os import mcp-server <url>
```

### `export`

Export a capability to an external format.

```bash
intent-os export openai <manifest.yaml>
intent-os export mcp <manifest.yaml>
```

### `mcp-server`

Start or manage the Intent OS MCP Server (SSE transport).

```bash
intent-os mcp-server start --port 8080
intent-os mcp-server status --port 8080
```

---

## AI / UX Commands

### `ask`

Execute capabilities using natural language.

```bash
intent-os ask "translate hello to French"     # Single query
intent-os ask                                  # Interactive REPL mode

# Options:
  --provider    LLM provider (auto, ollama, openai, anthropic)
```

### `evolution`

Run the Evolution Loop for continuous optimization.

```bash
intent-os evolution run          # Run one iteration
intent-os evolution status       # Pending suggestions count
intent-os evolution queue        # List pending suggestions
intent-os evolution approve <id> # Approve a suggestion
intent-os evolution reject <id>  # Reject a suggestion
```

### `quickstart`

Display a 7-step getting-started guide.

```bash
intent-os quickstart
```

### `demo`

Run an interactive terminal demo (no API key required).

```bash
intent-os demo         # Interactive mode
intent-os demo --auto  # Non-interactive mode
```
