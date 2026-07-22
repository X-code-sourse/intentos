"""
Intent OS — Ollama Runtime Adapter (Native API)

Maps an Intent OS CapabilityManifest to Ollama's native API.

Ollama's native API at /api/chat has a fundamentally different protocol
from OpenAI's Chat Completions. There is no tool/function calling —
instead, we instruct the model to output structured JSON via prompt.

This adapter is the TRUE cross-protocol test: it translates the Intent OS
schema into a completely different API format, proving that the Adapter
layer works for non-OpenAI-compatible runtimes.
"""

from __future__ import annotations

import json
import os
import urllib.request
import urllib.error
from typing import Any

from adapters.base import AdapterBase
from core.models import CapabilityManifest


# Cost is $0 (local inference)
PRICING: dict[str, dict[str, float]] = {}


def _calculate_cost(_model: str, _input_tokens: int, _output_tokens: int) -> float:
    """Local inference — no cost."""
    return 0.0


def _build_output_prompt(
    manifest: CapabilityManifest,
    input_data: dict[str, Any],
) -> str:
    """Build a prompt that instructs the model to output structured JSON
    matching the manifest's output schema.

    Ollama's native API has no tool/function calling, so we encode
    the expected output structure as a JSON schema in the prompt.
    """
    # Build output schema description
    schema_lines = ["{"]
    for i, (field_name, field) in enumerate(manifest.output_schema.items()):
        comma = "," if i < len(manifest.output_schema) - 1 else ""
        optional = " (optional)" if field.optional else ""
        desc = f" // {field.description}" if field.description else ""
        if field.type == "array" and field.items:
            schema_lines.append(f'  "{field_name}": [{field.items.type}]{optional}{desc}{comma}')
        else:
            schema_lines.append(f'  "{field_name}": {field.type}{optional}{desc}{comma}')
    schema_lines.append("}")

    input_text = json.dumps(input_data, ensure_ascii=False)

    prompt = (
        f"You are an AI capability named '{manifest.name}'.\n"
        f"Description: {manifest.metadata.description or 'No description provided.'}\n\n"
        f"Input:\n{input_text}\n\n"
        f"Produce the output as valid JSON matching this schema:\n"
        f"```json\n{chr(10).join(schema_lines)}\n```\n\n"
        "Return ONLY the JSON object. No explanation, no markdown formatting, "
        "no code fences."
    )
    return prompt


class OllamaAdapter(AdapterBase):
    """
    Runtime adapter for Ollama's native API (local inference).

    Uses the /api/chat endpoint with structured JSON output prompt.
    This adapter is the TRUE cross-protocol test — the API format
    is completely different from OpenAI/Anthropic.

    Requires Ollama server running locally. Install from:
      https://ollama.com/download
    Then: ollama pull llama3.2
    """

    def __init__(self, base_url: str = "http://localhost:11434") -> None:
        self._base_url = base_url
        self._model = self.default_model

    @property
    def name(self) -> str:
        return "ollama"

    @property
    def version(self) -> str:
        return "0.1.0"

    @property
    def default_model(self) -> str:
        return "llama3.2:1b"

    def execute(
        self,
        manifest: CapabilityManifest,
        input_data: dict[str, Any],
        **kwargs: Any,
    ) -> dict[str, Any]:
        """
        Execute a capability using Ollama's native /api/chat endpoint.

        This is a completely different API protocol from OpenAI:
          - No tool/function calling
          - Structured output via prompt instruction
          - API format is unique to Ollama

        Args:
            manifest: The capability manifest.
            input_data: Input data matching the manifest's input schema.
            **kwargs: Optional overrides:
                model: Model identifier override.
                base_url: Ollama server URL override.

        Returns:
            Execution results as a dict matching the manifest's output schema,
            plus internal metadata keys _token_usage and _cost.
        """
        base_url = kwargs.get("base_url", self._base_url)
        model = kwargs.get("model", self._model)

        # Build the prompt with output schema instruction
        user_content = _build_output_prompt(manifest, input_data)

        # Call Ollama's native /api/chat endpoint
        payload = {
            "model": model,
            "messages": [{"role": "user", "content": user_content}],
            "stream": False,
            "options": {
                "temperature": 0.1,  # Low temperature for consistent JSON
            },
        }

        req = urllib.request.Request(
            url=f"{base_url}/api/chat",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        try:
            with urllib.request.urlopen(req, timeout=120) as resp:
                response_data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            error_body = exc.read().decode("utf-8") if exc.fp else str(exc)
            raise RuntimeError(f"Ollama API error: {exc.code} - {error_body}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(
                f"Cannot connect to Ollama at {base_url}. "
                f"Is Ollama running? Error: {exc.reason}"
            ) from exc

        # Parse the response
        message_content = response_data.get("message", {}).get("content", "")

        # Try to parse JSON from the response
        result: dict[str, Any] = {}
        try:
            # Find JSON in the response (model might wrap it in markdown)
            content = message_content.strip()
            if content.startswith("```"):
                # Strip markdown code fences
                lines = content.split("\n")
                content = "\n".join(
                    line for line in lines
                    if not line.strip().startswith("```")
                )
            content = content.strip()
            # Try to find JSON object boundaries
            start = content.find("{")
            end = content.rfind("}")
            if start >= 0 and end > start:
                json_str = content[start:end + 1]
                result = json.loads(json_str)
            else:
                # If no JSON found, wrap the text as a flat output
                result = {"output": content}
        except json.JSONDecodeError:
            result = {"output": message_content}

        # Extract token usage from response
        usage = response_data.get("eval_count", 0)
        prompt_usage = response_data.get("prompt_eval_count", 0)
        result["_token_usage"] = {
            "input": prompt_usage,
            "output": usage,
            "total": prompt_usage + usage,
        }
        result["_cost"] = 0.0

        return result
