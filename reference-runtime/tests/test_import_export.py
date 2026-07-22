"""
Intent OS — Import/Export Toolchain Tests

Tests cover:
  1. OpenAI Function Calling → Manifest conversion
  2. Manifest → OpenAI Function Calling export
  3. Round-trip preservation
  4. MCP tool → Manifest conversion
  5. Bulk import from OpenAI tool list
  6. CLI integration
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path
from typing import Any

# Ensure project root is in path
_project_root = Path(__file__).parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from core.models import CapabilityManifest, FieldSchema
from core.registry import CapabilityRegistry
from tools.formats.openai import (
    openai_to_manifest,
    manifest_to_openai,
    openai_tool_collection_to_manifests,
    check_round_trip,
)
from tools.formats.mcp import (
    mcp_tool_to_manifest,
    mcp_server_to_manifests,
    manifest_to_mcp_tool,
    manifests_to_mcp_server_config,
)
from tools.importer import Importer, ImportResult
from tools.exporter import Exporter


# ──────────────────────────────────────────────
# Sample Data
# ──────────────────────────────────────────────

SAMPLE_OPENAI_FUNCTION = {
    "name": "search_web",
    "description": "Search the web for information",
    "parameters": {
        "type": "object",
        "properties": {
            "query": {
                "type": "string",
                "description": "The search query",
            },
            "max_results": {
                "type": "integer",
                "description": "Maximum number of results",
            },
            "include_summaries": {
                "type": "boolean",
                "description": "Whether to include summaries",
                "default": True,
            },
        },
        "required": ["query"],
    },
}

SAMPLE_TOOL_WRAPPER = {
    "type": "function",
    "function": SAMPLE_OPENAI_FUNCTION.copy(),
}

SAMPLE_MCP_TOOL = {
    "name": "search_web",
    "description": "Search the web for information",
    "inputSchema": {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "The search query"},
            "count": {"type": "integer", "description": "Results count"},
        },
        "required": ["query"],
    },
}


# ──────────────────────────────────────────────
# Tests: OpenAI → Manifest
# ──────────────────────────────────────────────

class TestOpenAIToManifest:
    """Test converting OpenAI Function Calling format to CapabilityManifest."""

    def test_basic_conversion(self):
        """Basic function should convert to valid manifest."""
        manifest = openai_to_manifest(SAMPLE_OPENAI_FUNCTION)
        assert manifest.name == "search_web"
        assert manifest.metadata.description == "Search the web for information"
        assert "query" in manifest.input_schema
        assert manifest.metadata.tags is not None
        assert "imported" in manifest.metadata.tags

    def test_input_schema_preserved(self):
        """Input schema fields should be correctly mapped."""
        manifest = openai_to_manifest(SAMPLE_OPENAI_FUNCTION)
        schema = manifest.input_schema

        assert schema["query"].type == "string"
        assert schema["query"].optional is False  # In required list

        assert schema["max_results"].type == "integer"
        assert schema["max_results"].optional is True  # Not in required

        assert schema["include_summaries"].type == "boolean"

    def test_description_preserved(self):
        """Field descriptions should be preserved."""
        manifest = openai_to_manifest(SAMPLE_OPENAI_FUNCTION)
        assert manifest.input_schema["query"].description == "The search query"
        assert manifest.input_schema["max_results"].description == "Maximum number of results"

    def test_tool_wrapper_handling(self):
        """Tool wrapper format {type: function, function: {...}} should be handled."""
        manifest = openai_to_manifest(SAMPLE_TOOL_WRAPPER)
        assert manifest.name == "search_web"

    def test_custom_metadata(self):
        """Custom metadata should be applied."""
        manifest = openai_to_manifest(
            SAMPLE_OPENAI_FUNCTION,
            publisher="example.com",
            tags=["custom", "test"],
        )
        assert manifest.metadata.publisher == "example.com"
        assert "custom" in (manifest.metadata.tags or [])

    def test_empty_function(self):
        """Minimal function with just a name should still produce a manifest."""
        fn = {"name": "minimal", "description": "A minimal function"}
        manifest = openai_to_manifest(fn)
        assert manifest.name == "minimal"


# ──────────────────────────────────────────────
# Tests: Manifest → OpenAI
# ──────────────────────────────────────────────

class TestManifestToOpenAI:
    """Test converting CapabilityManifest to OpenAI Function Calling format."""

    def test_basic_export(self):
        """Manifest should produce valid OpenAI function definition."""
        manifest = openai_to_manifest(SAMPLE_OPENAI_FUNCTION)
        openai_fn = manifest_to_openai(manifest)

        assert openai_fn["name"] == "search_web"
        assert "description" in openai_fn
        assert "parameters" in openai_fn
        assert openai_fn["parameters"]["type"] == "object"
        assert "properties" in openai_fn["parameters"]

    def test_required_fields(self):
        """Required fields should be preserved in export."""
        manifest = openai_to_manifest(SAMPLE_OPENAI_FUNCTION)
        openai_fn = manifest_to_openai(manifest)

        required = openai_fn["parameters"].get("required", [])
        assert "query" in required
        assert "max_results" not in required

    def test_tool_format(self):
        """as_tool=True should wrap in tool envelope."""
        manifest = openai_to_manifest(SAMPLE_OPENAI_FUNCTION)
        tool = manifest_to_openai(manifest, as_tool=True)

        assert tool["type"] == "function"
        assert "function" in tool
        assert tool["function"]["name"] == "search_web"

    def test_enum_fields(self):
        """Enum constraints should be preserved."""
        fn = {
            "name": "classify",
            "description": "Classify text",
            "parameters": {
                "type": "object",
                "properties": {
                    "category": {
                        "type": "string",
                        "enum": ["tech", "finance", "health"],
                    },
                },
                "required": ["category"],
            },
        }
        manifest = openai_to_manifest(fn)
        exported = manifest_to_openai(manifest)

        params = exported["parameters"]["properties"]["category"]
        assert params["enum"] == ["tech", "finance", "health"]


# ──────────────────────────────────────────────
# Tests: Round-trip
# ──────────────────────────────────────────────

class TestRoundTrip:
    """Test that OpenAI → Manifest → OpenAI preserves structure."""

    def test_name_preserved(self):
        """Name should survive round-trip."""
        result = check_round_trip(SAMPLE_OPENAI_FUNCTION)
        assert result["preserved"]["name_preserved"] is True

    def test_multiple_fields(self):
        """Multiple fields should survive round-trip."""
        manifest = openai_to_manifest(SAMPLE_OPENAI_FUNCTION)
        exported = manifest_to_openai(manifest)

        original_props = SAMPLE_OPENAI_FUNCTION["parameters"]["properties"]
        exported_props = exported["parameters"]["properties"]

        # Same number of properties
        assert len(exported_props) == len(original_props)
        # Same field names
        for field_name in original_props:
            assert field_name in exported_props


# ──────────────────────────────────────────────
# Tests: MCP → Manifest
# ──────────────────────────────────────────────

class TestMCPToManifest:
    """Test converting MCP tool definitions to CapabilityManifest."""

    def test_basic_mcp_conversion(self):
        """MCP tool should convert to valid manifest."""
        manifest = mcp_tool_to_manifest(SAMPLE_MCP_TOOL)
        assert manifest.name == "search_web"
        assert "query" in manifest.input_schema
        assert manifest.metadata.tags is not None
        assert "mcp" in manifest.metadata.tags

    def test_mcp_input_schema(self):
        """MCP inputSchema fields should be correctly mapped."""
        manifest = mcp_tool_to_manifest(SAMPLE_MCP_TOOL)
        assert manifest.input_schema["query"].type == "string"
        assert manifest.input_schema["count"].type == "integer"
        assert manifest.input_schema["query"].optional is False

    def test_network_detection(self):
        """Network dependency should be auto-detected for search tools."""
        manifest = mcp_tool_to_manifest(SAMPLE_MCP_TOOL)
        assert manifest.security is not None
        assert manifest.security.network is True

    def test_manifest_to_mcp(self):
        """CapabilityManifest → MCP tool should produce valid format."""
        manifest = mcp_tool_to_manifest(SAMPLE_MCP_TOOL)
        mcp_tool = manifest_to_mcp_tool(manifest)

        assert mcp_tool["name"] == "search_web"
        assert "inputSchema" in mcp_tool
        assert "properties" in mcp_tool["inputSchema"]
        assert "query" in mcp_tool["inputSchema"]["properties"]

    def test_mcp_server_config(self):
        """Multiple manifests should produce valid MCP server config."""
        manifests = [
            mcp_tool_to_manifest(SAMPLE_MCP_TOOL),
            mcp_tool_to_manifest({
                "name": "analyze",
                "description": "Analyze data",
                "inputSchema": {"type": "object", "properties": {}},
            }),
        ]
        config = manifests_to_mcp_server_config(manifests, server_name="test-server")
        assert config["name"] == "test-server"
        assert len(config["tools"]) == 2


# ──────────────────────────────────────────────
# Tests: Importer
# ──────────────────────────────────────────────

class TestImporter:
    """Test the Importer orchestration layer."""

    def test_import_openai_function(self):
        """Import OpenAI function and register it."""
        registry = CapabilityRegistry()
        importer = Importer(registry=registry)

        result = importer.import_openai_function(
            SAMPLE_OPENAI_FUNCTION,
            publisher="test",
        )
        assert isinstance(result, ImportResult)
        assert result.manifest.name == "search_web"
        assert result.registered is True

        # Check registry
        cap = registry.get("search_web", "1.0.0")
        assert cap is not None
        assert cap.metadata.publisher == "test"

    def test_import_from_json_string(self):
        """Import from a JSON string should work."""
        registry = CapabilityRegistry()
        importer = Importer(registry=registry)

        json_str = json.dumps(SAMPLE_OPENAI_FUNCTION)
        result = importer.import_openai_function(json_str)
        assert result.manifest.name == "search_web"

    def test_bulk_import(self):
        """Bulk import from a list of tools should work."""
        registry = CapabilityRegistry()
        importer = Importer(registry=registry)

        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".json", delete=False,
        ) as f:
            json.dump([SAMPLE_OPENAI_FUNCTION], f)
            temp_path = f.name

        try:
            results = importer.import_openai_tools_file(temp_path)
            assert len(results) == 1
            assert results[0].manifest.name == "search_web"
        finally:
            Path(temp_path).unlink(missing_ok=True)

    def test_import_with_output(self):
        """Import with output_dir should write file."""
        registry = CapabilityRegistry()
        importer = Importer(registry=registry)

        with tempfile.TemporaryDirectory() as tmpdir:
            result = importer.import_openai_function(
                SAMPLE_OPENAI_FUNCTION,
                output_dir=tmpdir,
            )
            assert result.output_path is not None
            assert result.output_path.exists()
            content = result.output_path.read_text()
            assert "search_web" in content

    def test_import_no_registry(self):
        """Import without registry should still convert."""
        importer = Importer(registry=None)
        result = importer.import_openai_function(SAMPLE_OPENAI_FUNCTION)
        assert result.manifest.name == "search_web"
        assert result.registered is False


# ──────────────────────────────────────────────
# Tests: Exporter
# ──────────────────────────────────────────────

class TestExporter:
    """Test the Exporter orchestration layer."""

    def test_export_to_openai(self):
        """Export manifest to OpenAI format."""
        registry = CapabilityRegistry()
        exporter = Exporter(registry=registry)

        # First register a capability
        importer = Importer(registry=registry)
        importer.import_openai_function(SAMPLE_OPENAI_FUNCTION)

        # Export it
        exported = exporter.export_openai("search_web")
        assert isinstance(exported, str)
        data = json.loads(exported)
        assert data["name"] == "search_web"

    def test_export_from_yaml(self):
        """Export from a YAML file should work."""
        exporter = Exporter()

        # Use the example manifest
        yaml_path = Path(_project_root) / "examples" / "text_summarize.yaml"
        if yaml_path.exists():
            exported = exporter.export_openai(str(yaml_path))
            data = json.loads(exported)
            assert "name" in data

    def test_export_as_tool(self):
        """Export in tool format should have tool envelope."""
        exporter = Exporter()
        manifest = openai_to_manifest(SAMPLE_OPENAI_FUNCTION)
        exported = exporter.export_openai(manifest, as_tool=True)
        data = json.loads(exported)
        assert data["type"] == "function"

    def test_export_to_mcp(self):
        """Export to MCP format should have MCP structure."""
        exporter = Exporter()
        manifest = openai_to_manifest(SAMPLE_OPENAI_FUNCTION)
        exported = exporter.export_mcp_tool(manifest)
        data = json.loads(exported)
        assert "inputSchema" in data
