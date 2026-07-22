"""
Intent OS — Capability Exporter

Exports Intent OS CapabilityManifests to external formats.

Supported targets:
  - openai: OpenAI Function Calling format
  - mcp: MCP server configuration

Each export:
  1. Reads a CapabilityManifest from the Registry or a YAML file
  2. Converts to the target format
  3. Writes to stdout or a file
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from core.models import CapabilityManifest
from core.parser import parse_manifest
from core.registry import CapabilityRegistry
from tools.formats.openai import manifest_to_openai


class ExportError(Exception):
    """Raised when an export operation fails."""
    pass


class Exporter:
    """
    Orchestrates exporting capabilities to external formats.

    Usage:
        exporter = Exporter(registry=my_registry)

        # Export a manifest to OpenAI format
        exporter.export_openai("my_capability", version="1.0.0")

        # Export a YAML file to MCP format
        exporter.export_mcp_tool("./my_cap.yaml")
    """

    def __init__(
        self,
        registry: CapabilityRegistry | None = None,
    ) -> None:
        self._registry = registry

    def set_registry(self, registry: CapabilityRegistry) -> None:
        self._registry = registry

    def _resolve_manifest(
        self,
        source: str | CapabilityManifest,
        version: str | None = None,
    ) -> CapabilityManifest:
        """Resolve a manifest from a name, file path, or existing manifest."""
        if isinstance(source, CapabilityManifest):
            return source

        # Check if it's a file path
        path = Path(source)
        if path.exists() and path.suffix in (".yaml", ".yml"):
            manifest, _ = parse_manifest(path)
            return manifest

        # Try registry lookup
        if self._registry:
            manifest = self._registry.get(source, version)
            if manifest:
                return manifest
            raise ExportError(f"Capability '{source}' not found in registry")

        raise ExportError(
            f"Cannot resolve '{source}': not a file path and no registry available"
        )

    # ── OpenAI Export ──

    def export_openai(
        self,
        source: str | CapabilityManifest,
        version: str | None = None,
        as_tool: bool = False,
        pretty: bool = True,
    ) -> str:
        """
        Export a capability as an OpenAI function definition.

        Args:
            source: Manifest name, YAML file path, or CapabilityManifest.
            version: Version (if looking up by name in registry).
            as_tool: If True, wrap in OpenAI tool format.
            pretty: If True, pretty-print JSON.

        Returns:
            JSON string of the OpenAI function definition.

        Example:
            >>> exporter.export_openai("web_search", as_tool=True)
            '{"type": "function", "function": {"name": "web_search", ...}}'
        """
        manifest = self._resolve_manifest(source, version)
        result = manifest_to_openai(manifest, as_tool=as_tool)
        indent = 2 if pretty else None
        return json.dumps(result, indent=indent, default=str)

    def export_openai_to_file(
        self,
        source: str | CapabilityManifest,
        output_path: str | Path,
        version: str | None = None,
        as_tool: bool = False,
    ) -> Path:
        """
        Export a capability to an OpenAI function definition file.

        Args:
            source: Manifest source.
            output_path: Output file path.
            version: Version (if looking up by name).
            as_tool: If True, wrap in OpenAI tool format.

        Returns:
            Path to the written file.
        """
        output_path = Path(output_path)
        content = self.export_openai(source, version=version, as_tool=as_tool)
        output_path.write_text(content, encoding="utf-8")
        return output_path

    # ── MCP Export ──

    def export_mcp_tool(
        self,
        source: str | CapabilityManifest,
        version: str | None = None,
        pretty: bool = True,
    ) -> str:
        """
        Export a capability as an MCP tool definition.

        Args:
            source: Manifest source.
            version: Version (if looking up by name).
            pretty: If True, pretty-print JSON.

        Returns:
            JSON string of the MCP tool definition.
        """
        manifest = self._resolve_manifest(source, version)
        from tools.formats.mcp import manifest_to_mcp_tool
        result = manifest_to_mcp_tool(manifest)
        indent = 2 if pretty else None
        return json.dumps(result, indent=indent, default=str)

    def export_mcp_tool_to_file(
        self,
        source: str | CapabilityManifest,
        output_path: str | Path,
        version: str | None = None,
    ) -> Path:
        """Export a capability to an MCP tool definition file."""
        output_path = Path(output_path)
        content = self.export_mcp_tool(source, version=version)
        output_path.write_text(content, encoding="utf-8")
        return output_path

    def export_mcp_server_config(
        self,
        sources: list[str | CapabilityManifest],
        server_name: str = "intent-os-exported",
        pretty: bool = True,
    ) -> str:
        """
        Export multiple capabilities as an MCP server configuration.

        Args:
            sources: List of manifest sources.
            server_name: Name for the MCP server.
            pretty: If True, pretty-print JSON.

        Returns:
            JSON string of the MCP server config.
        """
        from tools.formats.mcp import manifests_to_mcp_server_config

        manifests = []
        for src in sources:
            manifest = self._resolve_manifest(src)
            manifests.append(manifest)

        result = manifests_to_mcp_server_config(manifests, server_name=server_name)
        indent = 2 if pretty else None
        return json.dumps(result, indent=indent, default=str)
