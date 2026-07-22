"""
Intent OS — MCP Server Tests

Tests cover the core MCP protocol logic directly, without starting HTTP:
  1. Manifest → MCP tool format conversion
  2. tools/list returns registered capabilities
  3. tools/call invokes a capability via executor
  4. tools/call returns error for unknown capability
  5. Server status includes correct metadata
  6. tools/list with empty registry returns empty list
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path
from typing import Any

# Ensure project root is in path
_project_root = Path(__file__).parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

from core.models import (
    CapabilityManifest, FieldSchema, MetadataSpec,
    RequirementSpec, SecuritySpec,
)
from core.registry import CapabilityRegistry
from mcp_server import MCPServer, _manifest_to_mcp_tool, jsonrpc_result, jsonrpc_error


# ──────────────────────────────────────────────
# Fixtures
# ──────────────────────────────────────────────

def _make_manifest(
    name: str = "web_search",
    version: str = "1.0.0",
    description: str = "Search the web",
    input_fields: dict[str, FieldSchema] | None = None,
    output_fields: dict[str, FieldSchema] | None = None,
) -> CapabilityManifest:
    if input_fields is None:
        input_fields = {
            "query": FieldSchema(type="string", description="The search query"),
            "max_results": FieldSchema(type="integer", description="Max results", optional=True),
        }
    if output_fields is None:
        output_fields = {
            "result": FieldSchema(type="string", description="Result", optional=True),
        }
    return CapabilityManifest(
        metadata=MetadataSpec(
            name=name,
            version=version,
            publisher="test",
            description=description,
        ),
        input_schema=input_fields,
        output_schema=output_fields,
        requirements=RequirementSpec(models=["simulated"]),
        security=SecuritySpec(),
    )


def _setup_server_with_capabilities(
    manifests: list[CapabilityManifest],
) -> MCPServer:
    """Create an MCPServer with pre-populated registry and simulated executor.

    Bypasses _setup_runtime() to avoid adapter loading.
    """
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test_mcp.db"
        server = MCPServer.__new__(MCPServer)
        server.host = "127.0.0.1"
        server.port = 0
        server.adapter = "simulated"
        server._httpd = None
        server._running = False
        server.registry = CapabilityRegistry(db_path=str(db_path))
        for m in manifests:
            server.registry.register(m)

        # Use SimulatedExecutor
        from core.workflow_runner import SimulatedExecutor
        server.executor = SimulatedExecutor()

    return server


# ──────────────────────────────────────────────
# Tests: Manifest → MCP Tool
# ──────────────────────────────────────────────

class TestManifestToMCPTool:
    """Test conversion from CapabilityManifest to MCP tool format."""

    def test_converts_name_and_description(self):
        """MCP tool should preserve name and description."""
        manifest = _make_manifest()
        tool = _manifest_to_mcp_tool(manifest)
        assert tool["name"] == "web_search"
        assert tool["description"] == "Search the web"

    def test_converts_input_schema(self):
        """Input schema fields should map correctly to MCP inputSchema."""
        manifest = _make_manifest()
        tool = _manifest_to_mcp_tool(manifest)
        schema = tool["inputSchema"]
        assert schema["type"] == "object"
        assert "query" in schema["properties"]
        assert "max_results" in schema["properties"]

    def test_required_fields(self):
        """Non-optional fields should appear in required list."""
        manifest = _make_manifest()
        tool = _manifest_to_mcp_tool(manifest)
        assert "query" in tool["inputSchema"].get("required", [])
        assert "max_results" not in tool["inputSchema"].get("required", [])

    def test_field_descriptions_preserved(self):
        """Field descriptions should be preserved."""
        manifest = _make_manifest()
        tool = _manifest_to_mcp_tool(manifest)
        desc = tool["inputSchema"]["properties"]["query"].get("description", "")
        assert "search query" in desc.lower()

    def test_enum_fields(self):
        """Enum constraints should be included."""
        manifest = _make_manifest(
            name="classify",
            input_fields={
                "category": FieldSchema(
                    type="string", description="Category",
                    enum=["tech", "finance", "health"],
                ),
            },
        )
        tool = _manifest_to_mcp_tool(manifest)
        assert tool["inputSchema"]["properties"]["category"].get("enum") == ["tech", "finance", "health"]

    def test_any_type_converts_to_string(self):
        """The 'any' type should map to 'string' as fallback."""
        manifest = _make_manifest(
            name="generic",
            input_fields={"data": FieldSchema(type="any", description="Any data")},
        )
        tool = _manifest_to_mcp_tool(manifest)
        assert tool["inputSchema"]["properties"]["data"]["type"] == "string"


# ──────────────────────────────────────────────
# Tests: tools/list
# ──────────────────────────────────────────────

class TestToolsList:
    """Test MCP tools/list handler."""

    def test_empty_registry_returns_empty_list(self):
        """tools/list with no capabilities should return empty tools array."""
        server = _setup_server_with_capabilities([])
        response = server._handle_tools_list(msg_id=1)
        assert "result" in response
        assert response["result"]["tools"] == []

    def test_single_capability(self):
        """Single registered capability should appear in tools list."""
        manifest = _make_manifest()
        server = _setup_server_with_capabilities([manifest])
        response = server._handle_tools_list(msg_id=1)
        assert len(response["result"]["tools"]) == 1
        assert response["result"]["tools"][0]["name"] == "web_search"

    def test_multiple_capabilities(self):
        """All registered capabilities should appear."""
        manifests = [
            _make_manifest("search"),
            _make_manifest("analyze"),
            _make_manifest("report_generate"),
        ]
        server = _setup_server_with_capabilities(manifests)
        response = server._handle_tools_list(msg_id=1)
        assert len(response["result"]["tools"]) == 3
        names = [t["name"] for t in response["result"]["tools"]]
        assert "search" in names
        assert "analyze" in names
        assert "report_generate" in names

    def test_jsonrpc_id_preserved(self):
        """JSON-RPC id should be preserved in response."""
        server = _setup_server_with_capabilities([_make_manifest()])
        response = server._handle_tools_list(msg_id="test-id")
        assert response["id"] == "test-id"


# ──────────────────────────────────────────────
# Tests: tools/call
# ──────────────────────────────────────────────

class TestToolsCall:
    """Test MCP tools/call handler."""

    def test_calls_known_capability(self):
        """Calling a known capability should succeed."""
        manifest = _make_manifest("web_search", description="Search the web")
        server = _setup_server_with_capabilities([manifest])
        response = server._handle_tools_call(
            params={"name": "web_search", "arguments": {"query": "world"}},
            msg_id=1,
        )
        assert "result" in response
        assert "content" in response["result"]

    def test_unknown_capability_returns_error(self):
        """Calling an unknown capability should return error."""
        server = _setup_server_with_capabilities([])
        response = server._handle_tools_call(
            params={"name": "nonexistent", "arguments": {}},
            msg_id=1,
        )
        assert "error" in response
        assert response["error"]["code"] == -32602

    def test_missing_name_returns_error(self):
        """Calling without a name should return error."""
        server = _setup_server_with_capabilities([])
        response = server._handle_tools_call(
            params={"arguments": {}},
            msg_id=1,
        )
        assert "error" in response

    def test_jsonrpc_id_preserved_in_error(self):
        """JSON-RPC id should be preserved in error responses."""
        server = _setup_server_with_capabilities([])
        response = server._handle_tools_call(
            params={"name": "nonexistent", "arguments": {}},
            msg_id="err-1",
        )
        assert response["id"] == "err-1"

    def test_executor_failure_returns_error(self):
        """Adapter execution failure should return error with code -32603."""
        manifest = _make_manifest("fail_cap", description="Always fails")
        server = _setup_server_with_capabilities([manifest])
        server.executor = None
        # Force error by removing executor
        import threading
        old_executor = server.executor
        server.executor = None
        # Mock executor.execute to raise
        class FaultyExecutor:
            @staticmethod
            def execute(*args, **kwargs):
                raise RuntimeError("execution failed")
        server.executor = FaultyExecutor()
        response = server._handle_tools_call(
            params={"name": "fail_cap", "arguments": {"query": "test"}},
            msg_id=1,
        )
        assert "error" in response
        assert response["error"]["code"] == -32603


# ──────────────────────────────────────────────
# Tests: Server Status
# ──────────────────────────────────────────────

class TestServerStatus:
    """Test MCPServer.status()."""

    def test_status_with_no_capabilities(self):
        """Status should reflect empty registry."""
        server = _setup_server_with_capabilities([])
        info = server.status()
        assert info["capability_count"] == 0
        assert info["capabilities"] == []

    def test_status_with_capabilities(self):
        """Status should list registered capabilities."""
        manifests = [
            _make_manifest("search", description="Search tool"),
            _make_manifest("summarize", description="Summarization tool"),
        ]
        server = _setup_server_with_capabilities(manifests)
        info = server.status()
        assert info["capability_count"] == 2
        names = [c["name"] for c in info["capabilities"]]
        assert "search" in names
        assert "summarize" in names

    def test_status_contains_metadata(self):
        """Status should include server metadata."""
        server = _setup_server_with_capabilities([])
        info = server.status()
        assert info["transport"] == "sse"
        assert "sse_path" in info
        assert "messages_path" in info
        assert info["default_adapter"] == "simulated"

    def test_status_running_flag(self):
        """Status should reflect running state."""
        server = _setup_server_with_capabilities([])
        info = server.status()
        assert info["running"] is False


# ──────────────────────────────────────────────
# Tests: JSON-RPC Helpers
# ──────────────────────────────────────────────

class TestJsonRpcHelpers:
    """Test JSON-RPC response helpers."""

    def test_result_format(self):
        """jsonrpc_result should produce correct structure."""
        resp = jsonrpc_result({"key": "value"}, id=1)
        assert resp["jsonrpc"] == "2.0"
        assert resp["id"] == 1
        assert resp["result"]["key"] == "value"

    def test_error_format(self):
        """jsonrpc_error should produce correct structure."""
        resp = jsonrpc_error(-32602, "Invalid params", id=1)
        assert resp["jsonrpc"] == "2.0"
        assert resp["error"]["code"] == -32602
        assert resp["error"]["message"] == "Invalid params"
