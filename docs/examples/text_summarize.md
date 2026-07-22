# Text Summarize

Summarizes text content into a concise summary with key points.

```yaml
kind: Capability
metadata:
  name: text_summarize
  version: 1.0.0
  publisher: intent-os.org
  description: "Summarize text content into a concise summary with key points"
  tags: [nlp, summarization, text-analysis]
```

## Input

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `text` | string | Yes | The text to summarize |

## Output

| Field | Type | Description |
|-------|------|-------------|
| `summary` | string | Concise summary of the input text |
| `key_points` | array | List of key points extracted from the text |
| `word_count` | integer | Word count of the original text |

## Examples

```bash
intent-os run text_summarize -p text="The quick brown fox jumps over the lazy dog."
intent-os run text_summarize "Long article text goes here..."
```
