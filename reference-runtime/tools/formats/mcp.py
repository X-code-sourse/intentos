"""
Agent OS — MCP (Model Context Protocol) Format Converter

Provides conversion between MCP Server tool definitions and Agent OS
Capability Manifest (SPEC-0001).

MCP Servers expose tools via a standardized JSON-RPC endpoint.
This module can:
  1. Connect to a live MCP Server via HTTP and discover its tools
  2. Convert individual MCP tool schemas to CapabilityManifests
  3. Export Agent OS capabilities as MCP-compatible tool definitions

Relationship with Agent OS:
  - MCP standardizes Connection (AI ↔ Tool)
  - Agent OS standardizes Execution (Capability → Workflow → Event)
  - Agent OS Runtime can consume MCP servers as Capability Providers
"""

from __future__ import annotations

import json
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import urlparse

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
# MCP Server Connection
# ──────────────────────────────────────────────

def discover_mcp_tools(
    server_url: str,
    timeout: int = 30,
) -> list[dict[str, Any]]:
    """
    Connect to a running MCP Server and discover its available tools.

    MCP uses JSON-RPC over HTTP. This sends a 'tools/list' request.

    Args:
        server_url: The MCP server URL (e.g., http://localhost:8080/mcp).
        timeout: Request timeout in seconds.

    Returns:
        List of MCP tool definitions.

    Raises:
        ConnectionError: If the server cannot be reached.
        ValueError: If the server response is malformed.
    """
    # Validate URL
    parsed = urlparse(server_url)
    if not parsed.scheme:
        server_url = f"http://{server_url}"

    # Build MCP JSON-RPC request for tools/list
    payload = json.dumps({
        "jsonrpc": "2.0",
        "method": "tools/list",
        "params": {},
        "id": "agent-os-1",
    }).encode("utf-8")

    req = urllib.request.Request(
        url=server_url,
        data=payload,
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "AgentOS/0.1.0",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            response_data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raise ConnectionError(
            f"MCP server at {server_url} returned HTTP {exc.code}: {exc.reason}"
        ) from exc
    except urllib.error.URLError as exc:
        raise ConnectionError(
            f"Cannot connect to MCP server at {server_url}: {exc.reason}"
        ) from exc
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"Invalid JSON response from MCP server: {exc}"
        ) from exc

    # Parse JSON-RPC response
    if "error" in response_data:
        raise ValueError(
            f"MCP server error: {response_data['error'].get('message', str(response_data['error']))}"
        )

    result = response_data.get("result", {})
    tools = result.get("tools", [])

    if not isinstance(tools, list):
        raise ValueError("MCP server returned non-list 'tools' field")

    return tools


# ──────────────────────────────────────────────
# MCP Schema → Agent OS Schema
# ──────────────────────────────────────────────

def _mcp_type_to_agent_os(mcp_type: str) -> str:
    """Map MCP/JSON Schema types to Agent OS types."""
    mapping = {
        "string": "string",
        "integer": "integer",
        "number": "number",
        "boolean": "boolean",
        "array": "array",
        "object": "object",
        "null": "any",
    }
    return mapping.get(mcp_type, "string")


def _mcp_param_to_field_schema(
    name: str,
    param_schema: dict[str, Any],
    required_fields: list[str],
) -> FieldSchema:
    """Convert an MCP tool input schema parameter to an Agent OS FieldSchema."""
    mcp_type = param_schema.get("type", "string")
    field = FieldSchema(
        type=_mcp_type_to_agent_os(mcp_type),
        description=param_schema.get("description"),
        optional=name not in required_fields,
    )

    if mcp_type == "string":
        field.enum = param_schema.get("enum")
        field.min_length = param_schema.get("minLength")
        field.max_length = param_schema.get("maxLength")

    if mcp_type in ("integer", "number"):
        field.minimum = param_schema.get("minimum")
        field.maximum = param_schema.get("maximum")

    if mcp_type == "array" and "items" in param_schema:
        items = param_schema["items"]
        if isinstance(items, dict):
            field.items = FieldSchema(
                type=_mcp_type_to_agent_os(items.get("type", "string")),
                description=items.get("description"),
            )

    if mcp_type == "object" and "properties" in param_schema:
        nested_required = param_schema.get("required", [])
        field.properties = {}
        for pn, ps in param_schema["properties"].items():
            field.properties[pn] = _mcp_param_to_field_schema(pn, ps, nested_required)

    return field


def mcp_tool_to_manifest(
    tool_def: dict[str, Any],
    **kwargs: Any,
) -> CapabilityManifest:
    """
    Convert an MCP tool definition to a CapabilityManifest.

    Args:
        tool_def: MCP tool definition from tools/list response.
            Format: {"name": "...", "description": "...", "inputSchema": {...}}
        **kwargs: Additional manifest metadata (publisher, tags, etc.)

    Returns:
        CapabilityManifest instance.

    Example:
        >>> mcp_tool = {
        ...     "name": "search",
        ...     "description": "Search the web",
        ...     "inputSchema": {
        ...         "type": "object",
        ...         "properties": {"query": {"type": "string"}},
        ...         "required": ["query"],
        ...     },
        ... }
        >>> manifest = mcp_tool_to_manifest(mcp_tool, publisher="example.com")
    """
    name = tool_def.get("name", "mcp_tool")
    description = tool_def.get("description", "")
    input_schema = tool_def.get("inputSchema", {})

    required = input_schema.get("required", [])
    properties = input_schema.get("properties", {})

    # Build input schema
    aos_input: dict[str, FieldSchema] = {}
    for field_name, field_schema in properties.items():
        aos_input[field_name] = _mcp_param_to_field_schema(
            field_name, field_schema, required,
        )

    # MCP doesn't have an output schema concept in tools/list
    output_schema: dict[str, FieldSchema] = {
        "result": FieldSchema(
            type="any",
            description="Result from the MCP tool execution",
        ),
    }

    # Detect network dependency
    is_network_tool = any(
        keyword in name.lower()
        for keyword in ["search", "web", "http", "api", "fetch", "browse"]
    )

    metadata = MetadataSpec(
        name=name,
        version=kwargs.get("version", "1.0.0"),
        publisher=kwargs.get("publisher"),
        description=description,
        tags=kwargs.get("tags", ["imported", "mcp"]),
    )

    requirements = RequirementSpec(
        models=kwargs.get("models", ["gpt-4o", "claude-sonnet-4"]),
    )

    security = SecuritySpec(
        risk=kwargs.get("risk", SecurityRisk.LOW),
        network=kwargs.get("network", is_network_tool),
    )

    return CapabilityManifest(
        metadata=metadata,
        input_schema=aos_input,
        output_schema=output_schema,
        requirements=requirements,
        security=security,
    )


def mcp_server_to_manifests(
    server_url: str,
    **kwargs: Any,
) -> list[CapabilityManifest]:
    """
    Connect to an MCP server, discover all its tools, and convert each
    to a CapabilityManifest.

    This is the "one-command" import path for MCP:
        agent-os import mcp-server http://localhost:8080/mcp

    Args:
        server_url: MCP server URL.
        **kwargs: Additional metadata passed to each conversion.

    Returns:
        List of CapabilityManifest instances.

    Raises:
        ConnectionError: If the server cannot be reached.
        ValueError: If the response is malformed.
    """
    tools = discover_mcp_tools(server_url, timeout=kwargs.get("timeout", 30))
    manifests = []
    for tool in tools:
        manifest = mcp_tool_to_manifest(tool, **kwargs)
        manifests.append(manifest)
    return manifests


# ──────────────────────────────────────────────
# Manifest → MCP
# ──────────────────────────────────────────────

def _field_schema_to_mcp_param(field: FieldSchema) -> dict[str, Any]:
    """Convert an Agent OS FieldSchema to an MCP parameter property."""
    type_map = {
        "string": "string", "integer": "integer", "number": "number",
        "boolean": "boolean", "array": "array", "object": "object",
        "any": "string",
    }
    prop: dict[str, Any] = {"type": type_map.get(field.type, "string")}
    if field.description:
        prop["description"] = field.description
    if field.type == "string" and field.enum:
        prop["enum"] = field.enum
    if field.type in ("integer", "number"):
        if field.minimum is not None:
            prop["minimum"] = field.minimum
        if field.maximum is not None:
            prop["maximum"] = field.maximum
    if field.type == "array" and field.items:
        prop["items"] = {"type": type_map.get(field.items.type, "string")}
    if field.type == "object" and field.properties:
        nested_props = {}
        nested_required = []
        for pn, pf in field.properties.items():
            nested_props[pn] = _field_schema_to_mcp_param(pf)
            if not pf.optional:
                nested_required.append(pn)
        prop["properties"] = nested_props
        if nested_required:
            prop["required"] = nested_required
    return prop


def manifest_to_mcp_tool(manifest: CapabilityManifest) -> dict[str, Any]:
    """
    Convert a CapabilityManifest to an MCP tool definition.

    Args:
        manifest: The Agent OS CapabilityManifest.

    Returns:
        MCP tool definition dict.
    """
    properties = {}
    required = []

    for field_name, field in manifest.input_schema.items():
        properties[field_name] = _field_schema_to_mcp_param(field)
        if not field.optional:
            required.append(field_name)

    input_schema: dict[str, Any] = {
        "type": "object",
        "properties": properties,
    }
    if required:
        input_schema["required"] = required

    return {
        "name": manifest.name,
        "description": manifest.metadata.description or "",
        "inputSchema": input_schema,
    }


def manifests_to_mcp_server_config(
    manifests: list[CapabilityManifest],
    server_name: str = "agent-os-exported",
) -> dict[str, Any]:
    """
    Generate an MCP server configuration from a list of CapabilityManifests.

    This is useful for generating an MCP server that exposes Agent OS
    capabilities through the MCP protocol.

    Args:
        manifests: List of CapabilityManifests to include.
        server_name: Name for the MCP server.

    Returns:
        MCP server configuration dict.
    """
    tools = [manifest_to_mcp_tool(m) for m in manifests]

    return {
        "name": server_name,
        "version": "1.0.0",
        "tools": tools,
        "description": f"Agent OS exported capabilities ({len(tools)} tools)",
    }
