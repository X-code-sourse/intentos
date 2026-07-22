"""
Intent OS — OpenAI Runtime Adapter

Maps an Intent OS CapabilityManifest to OpenAI's Function Calling API.

This adapter translates the Intent OS schema (SPEC-0001) into OpenAI's
function/tool format, invokes the model, and maps the response back
to the Intent OS output schema.

Key translation:
  - Manifest input_schema → OpenAI function parameters
  - OpenAI function response → Manifest output_schema structure
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
    "gpt-4o": {"input": 2.50, "output": 10.00},
    "gpt-4o-mini": {"input": 0.15, "output": 0.60},
    "gpt-4.1": {"input": 2.00, "output": 8.00},
    "gpt-4.1-mini": {"input": 0.40, "output": 1.60},
    "gpt-4.1-nano": {"input": 0.10, "output": 0.40},
    "o3": {"input": 10.00, "output": 40.00},
    "o4-mini": {"input": 1.10, "output": 4.40},
}


def _calculate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Calculate approximate cost for a model invocation."""
    pricing = PRICING.get(model, {"input": 2.50, "output": 10.00})
    return (input_tokens / 1_000_000 * pricing["input"]
            + output_tokens / 1_000_000 * pricing["output"])


def _schema_to_openai_params(output_schema: dict) -> dict:
    """Convert Intent OS output schema to OpenAI function parameters.

    In OpenAI function calling, the model generates arguments as if it is
    *calling* the function. We want the model to generate the *output* fields
    as its function arguments. Therefore we describe the output_schema as
    the function's parameters.
    """
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

    for field_name, field in output_schema.items():
        prop: dict[str, Any] = {"type": type_map.get(field.type, "string")}

        if field.description:
            prop["description"] = field.description

        if field.type == "string":
            if field.enum:
                prop["enum"] = field.enum
            if field.min_length is not None:
                prop["minLength"] = field.min_length
            if field.max_length is not None:
                prop["maxLength"] = field.max_length

        if field.type in ("integer", "number"):
            if field.minimum is not None:
                prop["minimum"] = field.minimum
            if field.maximum is not None:
                prop["maximum"] = field.maximum

        if field.type == "array" and field.items:
            items_type = type_map.get(field.items.type, "string")
            prop["items"] = {"type": items_type}
            if field.items.description:
                prop["items"]["description"] = field.items.description

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

    return {"type": "object", "properties": properties, "required": required}


class OpenAIAdapter(AdapterBase):
    """
    Runtime adapter for OpenAI models via the Chat Completions API.

    Uses OpenAI's tool/function calling to execute capabilities.
    Requires the OPENAI_API_KEY environment variable to be set.
    """

    @property
    def name(self) -> str:
        return "openai"

    @property
    def version(self) -> str:
        return "0.1.0"

    @property
    def default_model(self) -> str:
        return "gpt-4o"

    def execute(
        self,
        manifest: CapabilityManifest,
        input_data: dict[str, Any],
        **kwargs: Any,
    ) -> dict[str, Any]:
        """
        Execute a capability using OpenAI's tool/function calling.

        Args:
            manifest: The capability manifest.
            input_data: Input data matching the manifest's input schema.
            **kwargs: Optional overrides:
                model: Model identifier override.
                api_key: API key override (default: OPENAI_API_KEY env).

        Returns:
            Execution results as a dict matching the manifest's output schema,
            plus internal metadata keys _token_usage and _cost.

        Raises:
            RuntimeError: If API call fails or key is not set.
        """
        try:
            from openai import OpenAI
        except ImportError:
            raise RuntimeError(
                "OpenAI package is required. Install with: pip install openai"
            )

        api_key = kwargs.get("api_key") or os.environ.get("OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError(
                "OpenAI API key not found. Set OPENAI_API_KEY environment variable "
                "or pass api_key=..."
            )

        model = kwargs.get("model", self.default_model)

        # Build the tool/function definition from the manifest's OUTPUT schema
        # In OpenAI function calling, the model generates arguments as if
        # calling the function. We want the model to PUT its output into
        # the function arguments. So the function parameters describe the
        # OUTPUT fields, not the input fields.
        function_def = {
            "name": manifest.name,
            "description": manifest.metadata.description or "",
            "parameters": _schema_to_openai_params(manifest.output_schema),
        }

        # Build a prompt that instructs the model to produce its output
        # by calling the function with the output fields as arguments.
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

        # Call OpenAI
        client = OpenAI(api_key=api_key)
        response = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": user_content}],
            tools=[{"type": "function", "function": function_def}],
            tool_choice={"type": "function", "function": {"name": manifest.name}},
        )

        # Extract the result
        choice = response.choices[0]
        result: dict[str, Any] = {}

        if choice.message.tool_calls:
            for tool_call in choice.message.tool_calls:
                if tool_call.function.name == manifest.name:
                    result = json.loads(tool_call.function.arguments)

        # Extract token usage
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
