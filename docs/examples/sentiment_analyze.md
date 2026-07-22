# Sentiment Analysis

Analyzes the emotional tone of text, returning sentiment classification with confidence score and key phrases.

```yaml
kind: Capability
metadata:
  name: sentiment_analyze
  version: 1.0.0
  publisher: intent-os.org
  description: "Analyzes the emotional tone of text"
  tags: [nlp, sentiment, text-analysis, emotions]
```

## Input

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `text` | string | Yes | Text to analyze for sentiment |

## Output

| Field | Type | Description |
|-------|------|-------------|
| `sentiment` | string | Classification: positive, negative, or neutral |
| `confidence` | number | Confidence score (0.0 to 1.0) |
| `key_phrases` | array | Key emotional phrases detected |

## Examples

```bash
intent-os run sentiment_analyze "I love using Intent OS, it's amazing!"
intent-os run sentiment_analyze -p text="This product is terrible and broken."
```
