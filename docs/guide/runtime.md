# Running Capabilities

Once you have a Manifest, `intent-os run` executes it on any available runtime.

---

## Basic Usage

```bash
# Run from a file
intent-os run examples/translate.yaml --input '{"text": "Hello", "target_lang": "zh"}'

# Run a built-in capability by name
intent-os run translate --input '{"text": "Hello", "target_lang": "zh"}'

# Run with inline parameters
intent-os run translate -p text="Hello" -p target_lang=zh

# Run with inline text (maps to the "text" field)
intent-os run translate "Hello" -p target_lang=zh
```

## Selecting a Runtime

```bash
# Auto-select (uses available adapters in order)
intent-os run translate -p text="Hello" -p target_lang=zh

# Specify a specific adapter
intent-os run translate --adapter openai -p text="Hello" -p target_lang=zh
intent-os run translate --adapter ollama -p text="Hello" -p target_lang=zh
intent-os run translate --adapter anthropic -p text="Hello" -p target_lang=zh
```

## Input Options

```bash
# JSON string
--input '{"text": "Hello", "target_lang": "zh"}'

# JSON file
--input-file input.json

# Key=value pairs (repeatable)
-p text="Hello" -p target_lang=zh

# Inline text (positional argument — maps to "text" field)
intent-os run translate "Hello world" -p target_lang=zh
```

## Output

```bash
# Print to stdout (default)
intent-os run translate -p text="Hello" -p target_lang=zh

# Save execution record to file
intent-os run translate -p text="Hello" -p target_lang=zh --output result.json

# Save execution record
intent-os run translate -p text="Hello" -p target_lang=zh --save records/
```

## Available Adapters

| Adapter | Provider | Requires | Status |
|---------|----------|----------|--------|
| `ollama` | Ollama (local) | `ollama serve` running | :material-check: |
| `openai` | OpenAI API | `OPENAI_API_KEY` env var | :material-check: |
| `anthropic` | Anthropic API | `ANTHROPIC_API_KEY` env var | :material-check: |
| `openrouter` | OpenRouter API | `OPENROUTER_API_KEY` env var | :material-check: |
| `github-models` | GitHub Models | `GITHUB_TOKEN` env var | :material-check: |
| `simulated` | Built-in (no AI) | None (auto-fallback) | :material-check: |

## Compare Across Runtimes

```bash
intent-os compare examples/translate.yaml --input '{"text": "Hello", "target_lang": "fr"}'
```

This runs the same capability on every available adapter and compares latency, cost, and token usage.
