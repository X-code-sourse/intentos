# SPEC-0001: Capability Manifest

> **Status:** Draft v0.1 — Phase 0
> **Scope:** Defines the format for describing an AI Capability
> **Editor:** Intent OS Project

---

## 1. Purpose

The Capability Manifest defines a **standard format for describing AI capabilities**. It answers one question:

> **What is this capability, what does it need, and what does it produce?**

It is analogous to:
- OpenAPI for REST APIs
- OCI Image Manifest for container images
- package.json for npm packages

---

## 2. Design Principles

### P1: Describe Capability, Not Intelligence

The Manifest describes what a capability does at the interface level — not how it does it. It shall **never** contain:
- ❌ Model-specific prompts or instructions
- ❌ Reasoning strategies or chain-of-thought templates
- ❌ Inference parameters (temperature, top_p, etc.)

### P2: Runtime-Agnostic

The Manifest shall not assume or require any specific runtime. It must be equally valid for:
- OpenAI Function Calling
- Anthropic Tool Use
- MCP Server
- Local execution with no model backend
- Future runtimes not yet invented

### P3: Minimal Sufficient

The Manifest shall contain only the fields required for interoperability. Optional fields for optimization, discovery, and metadata are allowed but must not be required for basic execution.

---

## 3. Specification

### 3.1 Top-Level Structure

```yaml
kind: Capability
metadata:
  name: string               # Required. Unique capability name
  version: string             # Required. Semantic versioning
  publisher: string           # Recommended. Publisher identifier
  digest: string              # Optional. Content hash (sha256)
  description: string         # Recommended. Human-readable description
  tags: string[]              # Optional. Discovery tags
spec:
  input: Schema               # Required. Input contract
  output: Schema              # Required. Output contract
  requirements: Requirements  # Recommended. Operational requirements
  security: Security          # Optional. Security constraints
  cost: Cost                  # Optional. Cost estimation
```

### 3.2 Metadata Section

```yaml
metadata:
  name: text_summarize
  version: 1.0.0
  publisher: intent-os.org
  digest: sha256:e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855
  description: "Summarize text content into key points"
  tags: ["nlp", "summarization", "text"]
```

**Fields:**
- **name** (required): Unique identifier for the capability. Should be globally unique within the registry scope. Convention: `{domain}-{action}` format (e.g., `web-search`, `financial-analysis`).
- **version** (required): Semantic versioning (MAJOR.MINOR.PATCH). MAJOR for breaking interface changes, MINOR for additive changes, PATCH for bug fixes.
- **publisher** (recommended): Identifier of the publishing entity. Should use reverse domain notation (e.g., `org.intent-os`, `com.example`).
- **digest** (optional): SHA-256 hash of the Manifest content for integrity verification.
- **description** (recommended): Human-readable description of what the capability does.
- **tags** (optional): Keywords for discovery and categorization.

### 3.3 Spec Section

#### 3.3.1 Input Schema

Defines the input contract — what the capability expects to receive.

```yaml
spec:
  input:
    text:
      type: string
      description: "The text to summarize"
      min_length: 10
      max_length: 100000
    max_length:
      type: integer
      description: "Maximum summary length in words"
      optional: true
      default: 200
```

**Supported types:** `string`, `integer`, `number`, `boolean`, `array`, `object`, `any`

**Field modifiers:**
- **optional** (default: false): Whether the field can be omitted
- **default**: Default value if the field is not provided
- **description**: Human-readable description
- **constraints**: Type-specific (min_length, max_length, min, max, pattern, enum, format)

#### 3.3.2 Output Schema

Defines the output contract — what the capability guarantees to produce.

```yaml
spec:
  output:
    summary:
      type: string
      description: "The generated summary"
    key_points:
      type: array
      description: "Key points extracted from the text"
      items:
        type: string
      optional: true
```

Output Schema follows the same type system as Input Schema.

#### 3.3.3 Requirements

Defines what the capability needs to execute correctly.

```yaml
spec:
  requirements:
    models:
      - gpt-4
      - claude-3-sonnet
      - gemini-pro
    tools:
      - browser
      - search_api
    min_context: 16000
```

**Fields:**
- **models** (optional): List of compatible model identifiers. If omitted, any capable model may be used. Model URIs follow the format: `{provider}-{model-name}`.
- **tools** (optional): List of required tool capabilities. If a tool is listed, the runtime must provide it or the capability may fail.
- **min_context** (optional): Minimum context window length required (in tokens). Default: 4096.

#### 3.3.4 Security

Defines security constraints and risk level.

```yaml
spec:
  security:
    risk: low                         # low | medium | high | critical
    network: true                      # Does this capability make network calls?
    data_access: false                 # Does this access user/organization data?
    require_approval: false            # Does this require human approval?
```

**Risk levels:**
- **low**: Read-only, no side effects (e.g., text summarization, translation)
- **medium**: Has side effects but low impact (e.g., web search, file read)
- **high**: Significant side effects (e.g., file write, email send, API modification)
- **critical**: Could cause material harm (e.g., payment execution, system administration)

#### 3.3.5 Cost (Optional)

Provides hints for cost estimation.

```yaml
spec:
  cost:
    estimated_tokens: 0.1_per_char    # Token estimation formula
    estimated_latency: 2000ms          # Expected latency
    pricing_hint: 0.001_per_1k_tokens # Cost estimation
```

---

## 4. Complete Example

```yaml
kind: Capability
metadata:
  name: web_search
  version: 1.0.0
  publisher: org.intent-os
  description: "Search the web and return relevant results"
  tags:
    - search
    - web
    - information-retrieval

spec:
  input:
    query:
      type: string
      description: "The search query"
      min_length: 1
      max_length: 500
    max_results:
      type: integer
      description: "Maximum number of results to return"
      optional: true
      default: 10

  output:
    results:
      type: array
      description: "Search result items"
      items:
        type: object
        properties:
          title:
            type: string
          url:
            type: string
            format: uri
          snippet:
            type: string
      optional: true
    total_results:
      type: integer
      description: "Total number of results found"
      optional: true

  requirements:
    models:
      - any
    tools:
      - search_api
      - browser

  security:
    risk: low
    network: true
    data_access: false

  cost:
    estimated_tokens: 0.05_per_query
    estimated_latency: 1500ms
```

---

## 5. Validation Rules

### 5.1 Required Fields

The following fields are **always** required:
- `kind` — must equal "Capability"
- `metadata.name`
- `metadata.version`
- `spec.input` — must have at least one field
- `spec.output` — must have at least one field

### 5.2 Semantic Rules

1. **name** + **version** must be globally unique within a registry scope
2. **version** must follow semantic versioning (MAJOR.MINOR.PATCH)
3. All field names in `spec.input` and `spec.output` must be unique within their section
4. If `min_context` is specified, it must be >= 1024

### 5.3 Security Inheritance

If `security` is omitted, the default values are:
```yaml
security:
  risk: low
  network: false
  data_access: false
  require_approval: false
```

---

## 6. Versioning

### 6.1 Version Compatibility

| Change | MAJOR | MINOR | PATCH |
|---|---|---|---|
| Remove input field | ✅ | ❌ | ❌ |
| Add required input field | ✅ | ❌ | ❌ |
| Add optional input field | ❌ | ✅ | ❌ |
| Change output schema | ✅ | ❌ | ❌ |
| Add output field | ❌ | ✅ | ❌ |
| Bug fix in description | ❌ | ❌ | ✅ |
| Change requirements | ❌ | ✅ | ❌ |
| Change security risk level | ✅ | ❌ | ❌ |

### 6.2 Publisher Enforcement

Publishers are expected to:
- Increment MAJOR when making incompatible changes to `spec.input` or `spec.output`
- Increment MINOR when adding functionality in a backward-compatible manner
- Increment PATCH for backward-compatible bug fixes

---

## 7. Serialization Formats

The canonical Manifest format is **YAML** (for human readability).

JSON is also valid (for machine generation/consumption).

Conversion between YAML and JSON should be lossless given that all field names conform to both formats' constraints.

---

## 8. Security Considerations

1. **Digest Verification**: When `digest` is present, consumers should verify the Manifest content matches the digest before execution.
2. **Security Claims**: The `security.risk` field is a self-declared claim. In Phase 2+ environments, this should be verified or overridden by organizational policy.
3. **Requirements Injection**: The `requirements.tools` field should be validated against an allowlist in production environments to prevent capability-scoped privilege escalation.

---

## 9. Future Extensions (Phase 2+)

The following fields are reserved for future versions:

| Field | Purpose | Phase |
|---|---|---|
| `spec.context` | Declares which context dimensions the capability reads/writes | Phase 1 |
| `spec.constraints` | Latency, cost, or quality bounds | Phase 1 |
| `spec.test_schema` | Input/output examples for verification | Phase 2 |
| `spec.dependencies` | Other capabilities this one depends on | Phase 2 |
| `spec.telemetry` | What execution data this capability emits | Phase 2 |

---

## 10. References

- OpenAPI Specification 3.x — for interface contract patterns
- OCI Image Spec — for manifest + digest conventions
- JSON Schema — for type system patterns
