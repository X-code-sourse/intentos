# Hello World — Intent OS Quickstart

A minimal example to demonstrate the basic workflow of Intent OS.

## Files

| File | Purpose |
|---|---|
| `hello_world.yaml` | Capability Manifest describing a simple greeting capability |
| `README.md` | This file |

## Commands

```bash
# Validate the manifest
intent-os validate hello_world.yaml

# Run with Ollama (local, no API key needed)
intent-os run hello_world.yaml --adapter ollama \
  --input '{"name": "World"}'

# Run with OpenAI (requires OPENAI_API_KEY)
intent-os run hello_world.yaml --adapter openai \
  --input '{"name": "World"}'

# Export to OpenAI function format
intent-os export openai hello_world.yaml --as-tool
```
