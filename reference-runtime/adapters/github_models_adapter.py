"""
Intent OS — GitHub Models Runtime Adapter

Maps an Intent OS CapabilityManifest to GitHub Models API.

GitHub Models provides free access to GPT-4o, Llama, Mistral and other models
via an OpenAI-compatible API endpoint. This adapter uses your GitHub token
to access these models — no paid API key required.

The adapter is almost identical to the OpenAI adapter, except:
  - Uses GitHub token (GITHUB_TOKEN env var) instead of OpenAI API key
  - Uses a different API base URL: https://models.inference.ai.azure.com
  - Supports GitHub Models' model roster
"""

from __future__ import annotations

import json
import os
from typing import Any

from adapters.base import AdapterBase
from core.models import CapabilityManifest


# Model pricing per 1M tokens (approximate, free-tier GitHub Models)
PRICING: dict[str, dict[str, float]] = {
    "gpt-4o": {"input": 0.00, "output": 0.00},
    "gpt-4o-mini": {"input": 0.00, "output": 0.00},
    "gpt-4.1": {"input": 0.00, "output": 0.00},
    "Llama-3.3-70B": {"input": 0.00, "output": 0.00},
    "Mistral-large": {"input": 0.00, "output": 0.00},
}

GITHUB_MODELS_BASE_URL = "https://models.inference.ai.azure.com"


def _calculate_cost(_model: str, _input_tokens: int, _output_tokens: int) -> float:
    """GitHub Models free tier — no cost."""
    return 0.0


def _schema_to_openai_params(output_schema: dict) -> dict:
    """Convert Intent OS output schema to OpenAI function parameters.

    Identical to the OpenAI adapter's implementation — reused here for
    cross-runtime consistency.
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
        if field.type in ("integer", "number"):
            if field.minimum is not None:
                prop["minimum"] = field.minimum
            if field.maximum is not None:
                prop["maximum"] = field.maximum
        if field.type == "array" and field.items:
            items_type = type_map.get(field.items.type, "string")
            prop["items"] = {"type": items_type}
        if not field.optional:
            required.append(field_name)
        properties[field_name] = prop

    return {"type": "object", "properties": properties, "required": required}


class GitHubModelsAdapter(AdapterBase):
    """
    Runtime adapter for GitHub Models API (free tier).

    Uses the OpenAI-compatible endpoint at models.inference.ai.azure.com.
    Requires the GITHUB_TOKEN environment variable to be set.
    """

    @property
    def name(self) -> str:
        return "github-models"

    @property
    def version(self) -> str:
        return "0.1.0"

    @property
    def default_model(self) -> str:
        return "gpt-4o-mini"

    def execute(
        self,
        manifest: CapabilityManifest,
        input_data: dict[str, Any],
        **kwargs: Any,
    ) -> dict[str, Any]:
        """
        Execute a capability using GitHub Models API.

        Args:
            manifest: The capability manifest.
            input_data: Input data matching the manifest's input schema.
            **kwargs: Optional overrides:
                model: Model identifier override.
                api_key: API key override (default: GITHUB_TOKEN env).

        Returns:
            Execution results as a dict matching the manifest's output schema,
            plus internal metadata keys _token_usage and _cost.
        """
        try:
            from openai import OpenAI
        except ImportError:
            raise RuntimeError(
                "OpenAI package is required. Install with: pip install openai"
            )

        api_key = kwargs.get("api_key") or os.environ.get("GITHUB_TOKEN")
        if not api_key:
            raise RuntimeError(
                "GitHub token not found. Set GITHUB_TOKEN environment variable "
                "or pass api_key=..."
            )

        model = kwargs.get("model", self.default_model)

        # Build the tool/function definition from the manifest's OUTPUT schema
        function_def = {
            "name": manifest.name,
            "description": manifest.metadata.description or "",
            "parameters": _schema_to_openai_params(manifest.output_schema),
        }

        # Build prompt
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

        # Call GitHub Models (OpenAI-compatible endpoint)
        client = OpenAI(
            api_key=api_key,
            base_url=GITHUB_MODELS_BASE_URL,
        )
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
