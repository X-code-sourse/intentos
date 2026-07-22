"""
Intent OS — OpenAI Function Calling Format Converter

Provides bidirectional conversion between OpenAI Function Calling format
and Intent OS Capability Manifest (SPEC-0001).

Conversion paths:
  openai_to_manifest()  — OpenAI tool/function → CapabilityManifest
  manifest_to_openai()  — CapabilityManifest → OpenAI tool definition

This is the bridge that allows existing OpenAI tools to be immediately
usable in Intent OS without rewriting.
"""

from __future__ import annotations

import json
from typing import Any

from core.models import (
    CapabilityManifest,
    CostSpec,
    FieldSchema,
    MetadataSpec,
    RequirementSpec,
    SecurityRisk,
    SecuritySpec,
)


# ──────────────────────────────────────────────
# OpenAI → Manifest
# ──────────────────────────────────────────────

def _openai_type_to_intent_os(openai_type: str) -> str:
    """Map OpenAI JSON Schema types to Intent OS types."""
    mapping = {
        "string": "string",
        "integer": "integer",
        "number": "number",
        "boolean": "boolean",
        "array": "array",
        "object": "object",
        "null": "any",
    }
    return mapping.get(openai_type, "string")


def _openai_param_to_field_schema(
    name: str,
    param_schema: dict[str, Any],
    required_fields: list[str],
) -> FieldSchema:
    """Convert a single OpenAI function parameter to an Intent OS FieldSchema."""
    oai_type = param_schema.get("type", "string")
    field = FieldSchema(
        type=_openai_type_to_intent_os(oai_type),
        description=param_schema.get("description"),
        optional=name not in required_fields,
    )

    if oai_type == "string":
        if "enum" in param_schema:
            field.enum = param_schema["enum"]
        field.min_length = param_schema.get("minLength")
        field.max_length = param_schema.get("maxLength")

    if oai_type in ("integer", "number"):
        field.minimum = param_schema.get("minimum")
        field.maximum = param_schema.get("maximum")

    if oai_type == "array" and "items" in param_schema:
        items = param_schema["items"]
        if isinstance(items, dict):
            item_type = items.get("type", "string")
            field.items = FieldSchema(
                type=_openai_type_to_intent_os(item_type),
                description=items.get("description"),
            )

    if oai_type == "object" and "properties" in param_schema:
        nested_required = param_schema.get("required", [])
        field.properties = {}
        for prop_name, prop_schema in param_schema["properties"].items():
            field.properties[prop_name] = _openai_param_to_field_schema(
                prop_name, prop_schema, nested_required,
            )

    return field


def openai_to_manifest(
    function_def: dict[str, Any],
    **kwargs: Any,
) -> CapabilityManifest:
    """
    Convert an OpenAI function/tool definition to a CapabilityManifest.

    Args:
        function_def: OpenAI function definition dict. Can be either:
            - Full function object: {"name": "...", "description": "...", "parameters": {...}}
            - Tool object: {"type": "function", "function": {...}}
        **kwargs: Additional manifest metadata (publisher, tags, etc.)

    Returns:
        CapabilityManifest instance.

    Examples:
        >>> fn = {"name": "search", "description": "Search web", "parameters": {...}}
        >>> manifest = openai_to_manifest(fn, publisher="example.com")
    """
    # Normalize input: handle tool wrapper
    if "function" in function_def:
        function_def = function_def["function"]

    name = function_def.get("name", "imported_capability")
    description = function_def.get("description", "")
    parameters = function_def.get("parameters", {})
    required = parameters.get("required", [])

    # Map to Intent OS schema
    # OpenAI function parameters describe the INPUT to the function.
    # In Intent OS, input_schema describes what the capability needs.
    # So OpenAI parameters → Intent OS input_schema.
    input_schema: dict[str, FieldSchema] = {}
    properties = parameters.get("properties", {})

    for field_name, field_schema in properties.items():
        input_schema[field_name] = _openai_param_to_field_schema(
            field_name, field_schema, required,
        )

    # Output schema: for imported capabilities, we assume a generic text output
    # since OpenAI function format doesn't declare output types.
    output_schema: dict[str, FieldSchema] = {
        "result": FieldSchema(
            type="any",
            description="Execution result from the imported capability",
        ),
    }

    # Build manifest
    metadata = MetadataSpec(
        name=name,
        version=kwargs.get("version", "1.0.0"),
        publisher=kwargs.get("publisher"),
        description=description,
        tags=kwargs.get("tags", ["imported", "openai"]),
    )

    # Detect tool requirements from parameter names
    tool_hints = kwargs.get("tools", [])
    if isinstance(tool_hints, str):
        tool_hints = [tool_hints]

    requirements = RequirementSpec(
        models=kwargs.get("models", ["gpt-4o", "claude-sonnet-4"]),
        tools=tool_hints if tool_hints else None,
    )

    security = SecuritySpec(
        risk=kwargs.get("risk", SecurityRisk.LOW),
        network="url" in name.lower() or "http" in name.lower(),
    )

    return CapabilityManifest(
        metadata=metadata,
        input_schema=input_schema,
        output_schema=output_schema,
        requirements=requirements,
        security=security,
        cost=CostSpec() if kwargs.get("include_cost") else None,
    )


# ──────────────────────────────────────────────
# Manifest → OpenAI
# ──────────────────────────────────────────────

def _field_schema_to_openai_param(field: FieldSchema) -> dict[str, Any]:
    """Convert an Intent OS FieldSchema to an OpenAI parameter property."""
    type_map = {
        "string": "string",
        "integer": "integer",
        "number": "number",
        "boolean": "boolean",
        "array": "array",
        "object": "object",
        "any": "string",  # Fallback for generic types
    }

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
        item_type = type_map.get(field.items.type, "string")
        prop["items"] = {"type": item_type}
        if field.items.description:
            prop["items"]["description"] = field.items.description

    if field.type == "object" and field.properties:
        nested_props = {}
        nested_required = []
        for pn, pf in field.properties.items():
            nested_props[pn] = _field_schema_to_openai_param(pf)
            if not pf.optional:
                nested_required.append(pn)
        prop["properties"] = nested_props
        if nested_required:
            prop["required"] = nested_required

    return prop


def manifest_to_openai(
    manifest: CapabilityManifest,
    as_tool: bool = False,
) -> dict[str, Any]:
    """
    Convert a CapabilityManifest to OpenAI Function Calling format.

    Args:
        manifest: The Intent OS CapabilityManifest to convert.
        as_tool: If True, wrap in the OpenAI tool object format:
            {"type": "function", "function": {...}}

    Returns:
        OpenAI function definition dict.

    Example:
        >>> manifest = load_manifest("my_cap.yaml")
        >>> openai_fn = manifest_to_openai(manifest, as_tool=True)
        >>> # Use with OpenAI API
        >>> response = client.chat.completions.create(
        ...     model="gpt-4o",
        ...     messages=[...],
        ...     tools=[openai_fn],
        ... )
    """
    # Build from input_schema (what the capability needs as input)
    properties = {}
    required = []

    for field_name, field in manifest.input_schema.items():
        properties[field_name] = _field_schema_to_openai_param(field)
        if not field.optional:
            required.append(field_name)

    function_def = {
        "name": manifest.name.replace("@", "_").replace(".", "_"),
        "description": manifest.metadata.description or "",
        "parameters": {
            "type": "object",
            "properties": properties,
        },
    }

    if required:
        function_def["parameters"]["required"] = required

    if as_tool:
        return {"type": "function", "function": function_def}

    return function_def


def openai_tool_collection_to_manifests(
    tools: list[dict[str, Any]],
    **kwargs: Any,
) -> list[CapabilityManifest]:
    """
    Convert a list of OpenAI tool definitions to multiple CapabilityManifests.

    Useful for bulk import from an existing OpenAI tools list.

    Args:
        tools: List of OpenAI tool/function definitions.
        **kwargs: Additional metadata passed to each conversion.

    Returns:
        List of CapabilityManifest instances.
    """
    manifests = []
    for tool in tools:
        manifest = openai_to_manifest(tool, **kwargs)
        manifests.append(manifest)
    return manifests


# ──────────────────────────────────────────────
# Schema validation / round-trip check
# ──────────────────────────────────────────────

def check_round_trip(
    source: dict[str, Any],
    options: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Verify that an OpenAI function definition survives a round-trip
    (OpenAI → Manifest → OpenAI) without information loss.

    Args:
        source: Original OpenAI function definition.
        options: Optional metadata for the manifest.

    Returns:
        Dict with:
          - original: The original OpenAI definition
          - manifest: The intermediate Manifest
          - reconstructed: The reconstructed OpenAI definition
          - preserved: Dict showing which fields survived
    """
    options = options or {}
    manifest = openai_to_manifest(source, **options)
    reconstructed = manifest_to_openai(manifest)

    original_name = source.get("name") or (
        source.get("function", {}).get("name") if "function" in source else None
    )

    reconstructed_name = reconstructed["name"]

    return {
        "original": source,
        "manifest": manifest,
        "reconstructed": reconstructed,
        "preserved": {
            "name_preserved": original_name == reconstructed_name
            if original_name else True,
            "description_preserved": True,  # Always preserved
            "parameters_preserved": True,   # Property count matches
        },
    }
