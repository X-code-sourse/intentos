"""
Intent OS — OpenRouter Runtime Adapter

Maps an Intent OS CapabilityManifest to OpenRouter API.

OpenRouter provides a unified API to call 200+ models from different providers
(OpenAI, Anthropic, Google, Meta, etc.) through a single OpenAI-compatible endpoint.

This adapter is the cross-runtime bridge: it uses the OpenAI SDK with a different
base_url and headers to reach any model via OpenRouter. When configured to use
Claude models via OpenRouter, it becomes a true alternative runtime.
"""

from __future__ import annotations

import json
import os
from typing import Any

from adapters.base import AdapterBase
from core.models import CapabilityManifest


# Model pricing per 1M tokens (approximate, via OpenRouter)
PRICING: dict[str, dict[str, float]] = {
    "openai/gpt-4o": {"input": 2.50, "output": 10.00},
    "openai/gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "anthropic/claude-sonnet-4": {"input": 3.00, "output": 15.00},
    "anthropic/claude-3.5-sonnet": {"input": 3.00, "output": 15.00},
    "anthropic/claude-opus-4": {"input": 15.00, "output": 75.00},
    "google/gemini-pro": {"input": 0.50, "output": 1.50},
    "meta-llama/llama-3.3-70b": {"input": 0.25, "output": 0.25},
}

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"


def _calculate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Calculate approximate cost for a model invocation."""
    pricing = PRICING.get(model, {"input": 2.50, "output": 10.00})
    return (input_tokens / 1_000_000 * pricing["input"]
            + output_tokens / 1_000_000 * pricing["output"])


def _schema_to_openai_params(output_schema: dict) -> dict:
    """Convert Intent OS output schema to OpenAI function parameters."""
    type_map = {
        "string": "string", "integer": "integer", "number": "number",
        "boolean": "boolean", "array": "array", "object": "object",
    }
    properties = {}
    required = []
    for field_name, field in output_schema.items():
        prop: dict[str, Any] = {"type": type_map.get(field.type, "string")}
        if field.description:
            prop["description"] = field.description
        if field.type == "array" and field.items:
            prop["items"] = {"type": type_map.get(field.items.type, "string")}
        if not field.optional:
            required.append(field_name)
        properties[field_name] = prop
    return {"type": "object", "properties": properties, "required": required}


class OpenRouterAdapter(AdapterBase):
    """
    Runtime adapter for OpenRouter API.

    Routes capability execution through OpenRouter to any supported model.
    When configured with Claude models, this provides a true cross-runtime
    comparison path without requiring a direct Anthropic API key.
    """

    @property
    def name(self) -> str:
        return "openrouter"

    @property
    def version(self) -> str:
        return "0.1.0"

    @property
    def default_model(self) -> str:
        return "anthropic/claude-sonnet-4"

    def execute(
        self,
        manifest: CapabilityManifest,
        input_data: dict[str, Any],
        **kwargs: Any,
    ) -> dict[str, Any]:
        try:
            from openai import OpenAI
        except ImportError:
            raise RuntimeError(
                "OpenAI package is required. Install with: pip install openai"
            )

        api_key = kwargs.get("api_key") or os.environ.get("OPENROUTER_API_KEY")
        if not api_key:
            raise RuntimeError(
                "OpenRouter API key not found. Set OPENROUTER_API_KEY environment "
                "variable or pass api_key=..."
            )

        model = kwargs.get("model", self.default_model)

        function_def = {
            "name": manifest.name,
            "description": manifest.metadata.description or "",
            "parameters": _schema_to_openai_params(manifest.output_schema),
        }

        input_items = "\n".join(
            f"  {k}: {v}" for k, v in input_data.items()
        )
        user_content = (
            f"You are given the following input for '{manifest.name}':\n"
            f"{input_items}\n\n"
        )
        if manifest.metadata.description:
            user_content += f"Task: {manifest.metadata.description}\n\n"
        user_content += (
            "Analyze the input and produce the output by calling "
            f"the '{manifest.name}' function with the result."
        )

        client = OpenAI(
            api_key=api_key,
            base_url=OPENROUTER_BASE_URL,
        )
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": user_content}],
            tools=[{"type": "function", "function": function_def}],
            tool_choice={"type": "function", "function": {"name": manifest.name}},
            max_tokens=1024,  # Limit token usage for free-tier compatibility
            extra_headers={
                "HTTP-Referer": "https://intent-os.org",
                "X-Title": "Intent OS Reference Runtime",
            },
        )

        choice = response.choices[0]
        result: dict[str, Any] = {}
        if choice.message.tool_calls:
            for tool_call in choice.message.tool_calls:
                if tool_call.function.name == manifest.name:
                    result = json.loads(tool_call.function.arguments)

        usage = response.usage
        if usage:
            input_tokens = usage.prompt_tokens
            output_tokens = usage.completion_tokens
            result["_token_usage"] = {
                "input": input_tokens,
                "output": output_tokens,
                "total": input_tokens + output_tokens,
            }
            result["_cost"] = _calculate_cost(model, input_tokens, output_tokens)

        return result
