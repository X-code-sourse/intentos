# Translate

Translates text between natural languages with optional source language auto-detection.

```yaml
kind: Capability
metadata:
  name: translate
  version: 1.2.0
  publisher: intent-os.org
  description: "Translates text between natural languages"
  tags: [nlp, translation, i18n, localization, language]
```

## Input

| Field | Type | Required | Description |
|-------|------|----------|-------------|
| `text` | string | Yes | The text to translate (1–100,000 chars) |
| `source_lang` | string | No | Source language code (ISO 639-1). Auto-detected if omitted |
| `target_lang` | string | Yes | Target language code (ISO 639-1). e.g. `zh`, `es`, `fr`, `de` |

## Output

| Field | Type | Description |
|-------|------|-------------|
| `translated_text` | string | The translated text |
| `detected_language` | string | Detected source language (when source_lang omitted) |
| `confidence` | number | Confidence score (0.0 to 1.0) |

## Examples

```bash
# Basic translation
intent-os run translate -p text="Hello world" -p target_lang=zh

# With source language specified
intent-os run translate -p text="Hello" -p source_lang=en -p target_lang=fr

# Inline text (positional argument)
intent-os run translate "Good morning" -p target_lang=ja
```

## Requirements

| Requirement | Value |
|-------------|-------|
| Models | claude-sonnet-4, gpt-4o, gemini-2.5-pro |
| Min Context | 32,000 tokens |
| Risk Level | Low |
