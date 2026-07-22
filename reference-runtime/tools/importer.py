"""
Intent OS — Capability Importer

Orchestrates importing capabilities from external formats into Intent OS.

Supported sources:
  - openai-function: OpenAI Function Calling tools
  - mcp-server: MCP Server tools (via HTTP)

Each import:
  1. Reads/parses the source format
  2. Converts to CapabilityManifest
  3. Registers in the local Registry
  4. Optionally writes the Manifest YAML to disk
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from core.models import CapabilityManifest
from core.registry import CapabilityRegistry
from tools.formats.openai import openai_to_manifest, openai_tool_collection_to_manifests
from tools.formats.mcp import mcp_server_to_manifests, mcp_tool_to_manifest


class ImportError(Exception):
    """Raised when an import operation fails."""
    pass


class ImportResult:
    """Result of a single capability import."""

    def __init__(
        self,
        manifest: CapabilityManifest,
        source: str,
        output_path: Path | None = None,
        registered: bool = False,
    ) -> None:
        self.manifest = manifest
        self.source = source
        self.output_path = output_path
        self.registered = registered

    @property
    def name(self) -> str:
        return self.manifest.name

    @property
    def id(self) -> str:
        return self.manifest.id


class Importer:
    """
    Orchestrates importing capabilities from external formats.

    Usage:
        importer = Importer(registry=my_registry)

        # Import from OpenAI function definition
        result = importer.import_openai_function(
            source='{"name": "search", ...}',
            output_dir="./manifests",
        )

        # Import from MCP server
        results = importer.import_mcp_server(
            server_url="http://localhost:8080/mcp",
            output_dir="./manifests",
        )
    """

    def __init__(
        self,
        registry: CapabilityRegistry | None = None,
        auto_register: bool = True,
    ) -> None:
        self._registry = registry
        self._auto_register = auto_register

    def set_registry(self, registry: CapabilityRegistry) -> None:
        self._registry = registry

    # ── OpenAI Function Calling ──

    def import_openai_function(
        self,
        source: str | dict[str, Any],
        output_dir: str | Path | None = None,
        **kwargs: Any,
    ) -> ImportResult:
        """
        Import a single OpenAI function definition.

        Args:
            source: OpenAI function definition as a JSON string or dict.
            output_dir: Directory to write the Manifest YAML (optional).
            **kwargs: Additional metadata (publisher, tags, etc.).

        Returns:
            ImportResult with the converted manifest.

        Raises:
            ImportError: If parsing or conversion fails.
        """
        # Parse input
        if isinstance(source, str):
            try:
                source = json.loads(source)
            except json.JSONDecodeError as exc:
                raise ImportError(f"Invalid JSON: {exc}") from exc

        if not isinstance(source, dict):
            raise ImportError("OpenAI function definition must be a JSON object")

        # Convert
        try:
            manifest = openai_to_manifest(source, **kwargs)
        except Exception as exc:
            raise ImportError(f"Conversion failed: {exc}") from exc

        # Register
        if self._registry and self._auto_register:
            try:
                self._registry.register(manifest)
                registered = True
            except Exception as exc:
                raise ImportError(f"Registry registration failed: {exc}") from exc
        else:
            registered = False

        # Write to disk
        output_path = None
        if output_dir:
            output_path = self._write_manifest(manifest, output_dir)

        return ImportResult(
            manifest=manifest,
            source="openai-function",
            output_path=output_path,
            registered=registered,
        )

    def import_openai_tools_file(
        self,
        file_path: str | Path,
        output_dir: str | Path | None = None,
        **kwargs: Any,
    ) -> list[ImportResult]:
        """
        Import multiple OpenAI tools from a JSON file.

        The file should contain a JSON array of tool/function definitions.

        Args:
            file_path: Path to JSON file containing a list of tool definitions.
            output_dir: Directory to write Manifest YAMLs.
            **kwargs: Additional metadata.

        Returns:
            List of ImportResults.
        """
        file_path = Path(file_path)
        if not file_path.exists():
            raise ImportError(f"File not found: {file_path}")

        try:
            data = json.loads(file_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ImportError(f"Invalid JSON in {file_path}: {exc}") from exc

        if isinstance(data, dict):
            data = [data]
        if not isinstance(data, list):
            raise ImportError("JSON must contain a single object or an array of objects")

        results = []
        for item in data:
            result = self.import_openai_function(
                item, output_dir=output_dir, **kwargs,
            )
            results.append(result)

        return results

    # ── MCP Server ──

    def import_mcp_server(
        self,
        server_url: str,
        output_dir: str | Path | None = None,
        **kwargs: Any,
    ) -> list[ImportResult]:
        """
        Connect to an MCP server and import all its tools.

        Args:
            server_url: MCP server URL.
            output_dir: Directory to write Manifest YAMLs.
            **kwargs: Additional metadata.

        Returns:
            List of ImportResults.
        """
        from tools.formats.mcp import discover_mcp_tools

        # Discover tools from the MCP server
        try:
            tools = discover_mcp_tools(
                server_url,
                timeout=kwargs.get("timeout", 30),
            )
        except Exception as exc:
            raise ImportError(f"MCP discovery failed: {exc}") from exc

        if not tools:
            return []

        # Convert each tool
        results = []
        for tool_def in tools:
            try:
                manifest = mcp_tool_to_manifest(tool_def, **kwargs)
            except Exception as exc:
                raise ImportError(f"MCP conversion failed for '{tool_def.get('name', 'unknown')}': {exc}") from exc

            # Register
            registered = False
            if self._registry and self._auto_register:
                try:
                    self._registry.register(manifest)
                    registered = True
                except Exception:
                    pass  # Skip registration errors silently

            # Write to disk
            output_path = None
            if output_dir:
                output_path = self._write_manifest(manifest, output_dir)

            results.append(ImportResult(
                manifest=manifest,
                source=f"mcp-server:{server_url}",
                output_path=output_path,
                registered=registered,
            ))

        return results

    # ── Common ──

    def _write_manifest(
        self,
        manifest: CapabilityManifest,
        output_dir: str | Path,
    ) -> Path:
        """Write a CapabilityManifest to a YAML file."""
        output_dir = Path(output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)

        safe_name = manifest.name.replace("/", "_").replace(" ", "_")
        filename = f"{safe_name}.yaml"
        output_path = output_dir / filename

        # Construct YAML manually to avoid adding PyYAML as import dependency
        # for the tools module
        lines = [
            "kind: Capability",
            "metadata:",
            f"  name: {manifest.name}",
            f"  version: '{manifest.version}'",
        ]
        if manifest.metadata.publisher:
            lines.append(f"  publisher: {manifest.metadata.publisher}")
        if manifest.metadata.description:
            lines.append(f"  description: >")
            lines.append(f"    {manifest.metadata.description}")
        if manifest.metadata.tags:
            lines.append(f"  tags: [{', '.join(manifest.metadata.tags)}]")

        lines.append("")
        lines.append("spec:")
        lines.append("  input:")
        for field_name, field in manifest.input_schema.items():
            lines.append(f"    {field_name}:")
            lines.append(f"      type: {field.type}")
            if field.description:
                lines.append(f"      description: {field.description}")
            if field.optional:
                lines.append(f"      optional: true")

        lines.append("  output:")
        for field_name, field in manifest.output_schema.items():
            lines.append(f"    {field_name}:")
            lines.append(f"      type: {field.type}")
            if field.description:
                lines.append(f"      description: {field.description}")
            if field.optional:
                lines.append(f"      optional: true")

        if manifest.requirements:
            lines.append("  requirements:")
            if manifest.requirements.models:
                lines.append(f"    models: [{', '.join(manifest.requirements.models)}]")
            if manifest.requirements.tools:
                lines.append(f"    tools: [{', '.join(manifest.requirements.tools)}]")

        if manifest.security:
            lines.append("  security:")
            lines.append(f"    risk: {manifest.security.risk.value}")
            lines.append(f"    network: {str(manifest.security.network).lower()}")

        lines.append("")

        content = "\n".join(lines)
        output_path.write_text(content, encoding="utf-8")
        return output_path
