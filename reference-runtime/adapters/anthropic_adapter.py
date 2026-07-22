"""
Intent OS — Anthropic Runtime Adapter

Maps an Intent OS CapabilityManifest to Anthropic's Tool Use API.

This adapter translates the Intent OS schema (SPEC-0001) into Anthropic's
tool format, invokes the model, and maps the response back to the
Intent OS output schema.

Key translation:
  - Manifest input_schema → Anthropic tool input_schema
  - Anthropic tool response → Manifest output_schema structure
  - Token usage and cost are extracted for ExecutionRecord metrics
"""

from __future__ import annotations

import json
import os
from typing import Any

from adapters.base import AdapterBase
from core.models import CapabilityManifest


# Model pricing per 1M tokens (approximate, as of July 2026)
PRICING: dict[str, dict[str, float]] = {
    "claude-sonnet-4": {"input": 3.00, "output": 15.00},
    "claude-sonnet-4-20250514": {"input": 3.00, "output": 15.00},
    "claude-3.5-sonnet": {"input": 3.00, "output": 15.00},
    "claude-opus-4": {"input": 15.00, "output": 75.00},
    "claude-haiku-3.5": {"input": 0.80, "output": 4.00},
}


def _calculate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Calculate approximate cost for a model invocation."""
    pricing = PRICING.get(model, {"input": 3.00, "output": 15.00})
    return (input_tokens / 1_000_000 * pricing["input"]
            + output_tokens / 1_000_000 * pricing["output"])


def _schema_to_anthropic_tool(input_schema: dict, name: str, description: str) -> dict:
    """Convert Intent OS input schema to Anthropic tool format."""
    type_map = {
        "string": "string",
        "integer": "integer",
        "number": "number",
        "boolean": "boolean",
        "array": "array",
        "object": "object",
    }

    properties = {}
    required = []

    for field_name, field in input_schema.items():
        prop: dict[str, Any] = {"type": type_map.get(field.type, "string")}

        if field.description:
            prop["description"] = field.description

        if field.type == "string":
            if field.enum:
                prop["enum"] = field.enum

        if field.type == "object" and field.properties:
            nested_props = {}
            nested_required = []
            for pn, pf in field.properties.items():
                nested_props[pn] = {"type": type_map.get(pf.type, "string")}
                if pf.description:
                    nested_props[pn]["description"] = pf.description
                if not pf.optional:
                    nested_required.append(pn)
            prop["properties"] = nested_props
            if nested_required:
                prop["required"] = nested_required

        if not field.optional:
            required.append(field_name)

        properties[field_name] = prop

    return {
        "name": name,
        "description": description or "",
        "input_schema": {
            "type": "object",
            "properties": properties,
            "required": required,
        },
    }


class AnthropicAdapter(AdapterBase):
    """
    Runtime adapter for Anthropic models via the Messages API.

    Uses Anthropic's tool use to execute capabilities.
    Requires the ANTHROPIC_API_KEY environment variable to be set.
    """

    @property
    def name(self) -> str:
        return "anthropic"

    @property
    def version(self) -> str:
        return "0.1.0"

    @property
    def default_model(self) -> str:
        return "claude-sonnet-4-20250514"

    def execute(
        self,
        manifest: CapabilityManifest,
        input_data: dict[str, Any],
        **kwargs: Any,
    ) -> dict[str, Any]:
        """
        Execute a capability using Anthropic's tool use.

        Args:
            manifest: The capability manifest.
            input_data: Input data matching the manifest's input schema.
            **kwargs: Optional overrides:
                model: Model identifier override.
                api_key: API key override (default: ANTHROPIC_API_KEY env).

        Returns:
            Execution results as a dict matching the manifest's output schema,
            plus internal metadata keys _token_usage and _cost.

        Raises:
            RuntimeError: If API call fails or key is not set.
        """
        try:
            from anthropic import Anthropic
        except ImportError:
            raise RuntimeError(
                "Anthropic package is required. Install with: pip install anthropic"
            )

        api_key = kwargs.get("api_key") or os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise RuntimeError(
                "Anthropic API key not found. Set ANTHROPIC_API_KEY environment "
                "variable or pass api_key=..."
            )

        model = kwargs.get("model", self.default_model)

        # Build the tool definition from the manifest
        tool_def = _schema_to_anthropic_tool(
            manifest.input_schema,
            manifest.name,
            manifest.metadata.description or "",
        )

        # Build the user message
        user_content = f"Execute the capability '{manifest.name}' with the following input:\n"
        user_content += json.dumps(input_data, indent=2)

        # Call Anthropic
        client = Anthropic(api_key=api_key)
        response = client.messages.create(
            model=model,
            max_tokens=8192,
            messages=[{"role": "user", "content": user_content}],
            tools=[tool_def],
            tool_choice={"type": "tool", "name": manifest.name},
        )

        # Extract the result
        result: dict[str, Any] = {}

        for content_block in response.content:
            if content_block.type == "tool_use" and content_block.name == manifest.name:
                result = content_block.input

        # Extract token usage
        usage = response.usage
        if usage:
            input_tokens = usage.input_tokens
            output_tokens = usage.output_tokens
            result["_token_usage"] = {
                "input": input_tokens,
                "output": output_tokens,
                "total": input_tokens + output_tokens,
            }
            result["_cost"] = _calculate_cost(model, input_tokens, output_tokens)

        return result
