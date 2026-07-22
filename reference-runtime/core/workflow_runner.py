"""
Intent OS — Simulated Workflow Task Runner (Integration Testing)

Provides a simulated execution environment for testing multi-step workflows
without requiring real AI model API keys.

The SimulatedTaskRunner:
  - Registers mock capabilities that produce deterministic outputs
  - Executes tasks in DAG order with proper dependency resolution
  - Simulates configurable latency, success/failure, and output shapes
  - Records execution events for verification

This is the bridge between unit tests (isolated component tests) and
end-to-end validation (Planner → DAG → Scheduler → Execution → Events).
"""

from __future__ import annotations

import random
import threading
import time
import uuid
from typing import Any

from core.executor import Executor
from core.models import (
    CapabilityManifest,
    CostSpec,
    EventType,
    ExecutionRecord,
    ExecutionStatus,
    FieldSchema,
    MetadataSpec,
    RequirementSpec,
    SecuritySpec,
)
from core.recorder import ExecutionRecorder
from core.workflow import (
    ExecutionSemantics,
    TaskStatus,
    WorkflowDAG,
    WorkflowSpec,
    WorkflowStatus,
)


class SimulatedAdapter:
    """
    A simulated runtime adapter for integration testing.

    Produces deterministic outputs based on capability name and input.
    Can be configured to simulate failures for testing error handling.
    """

    def __init__(
        self,
        name: str = "simulated",
        fail_capabilities: list[str] | None = None,
        latency_range: tuple[float, float] = (0.01, 0.05),
    ) -> None:
        self._name = name
        self._fail_capabilities = set(fail_capabilities or [])
        self._latency_range = latency_range

    @property
    def name(self) -> str:
        return self._name

    @property
    def version(self) -> str:
        return "0.1.0"

    @property
    def default_model(self) -> str:
        return "simulated-model"

    def execute(
        self,
        manifest: CapabilityManifest,
        input_data: dict[str, Any],
        **kwargs: Any,
    ) -> dict[str, Any]:
        """
        Simulate capability execution.

        Produces a deterministic output based on the capability name.
        Can be configured to fail for specific capabilities.
        """
        cap_name = manifest.name

        # Check if this capability should fail
        if cap_name in self._fail_capabilities:
            raise RuntimeError(f"server_error: simulated failure for capability '{cap_name}'")

        # Simulate latency
        latency = random.uniform(*self._latency_range)
        time.sleep(latency)

        # Deterministic output based on capability name
        result = {
            "_token_usage": {"input": 100, "output": 50, "total": 150},
            "_cost": 0.001,
        }

        if "search" in cap_name.lower():
            input_text = input_data.get("query", input_data.get("input", ""))
            result["results"] = [
                {"title": f"Result 1 for {input_text}", "url": "https://example.com/1"},
                {"title": f"Result 2 for {input_text}", "url": "https://example.com/2"},
            ]
            result["total_results"] = 2

        elif "analyze" in cap_name.lower():
            input_text = str(input_data.get("text", input_data.get("input", "")))
            result["result"] = f"Analysis of: {input_text[:50]}..."
            result["confidence"] = 0.85

        elif "report" in cap_name.lower() or "generate" in cap_name.lower():
            result["report"] = f"Generated report based on provided analysis"
            result["format"] = "markdown"

        elif "fetch" in cap_name.lower():
            result["content"] = f"Fetched content for: {input_data.get('url', 'unknown')}"

        elif "summarize" in cap_name.lower():
            result["summary"] = f"Summary of provided input"
            result["key_points"] = ["Point 1", "Point 2"]

        else:
            result["output"] = f"Executed: {cap_name}"

        return result

    def can_execute(self, manifest: CapabilityManifest) -> bool:
        return True


class SimulatedExecutor(Executor):
    """
    An Executor pre-configured with simulated adapters for testing.

    Provides realistic multi-step workflow execution without API keys.
    """

    def __init__(self, fail_capabilities: list[str] | None = None) -> None:
        super().__init__()
        self.register_adapter("simulated", SimulatedAdapter(
            name="simulated",
            fail_capabilities=fail_capabilities,
        ))
        self.set_default_adapter("simulated")

    def set_default_adapter(self, name: str) -> None:
        """Set the default adapter name for routing."""
        self._default_adapter = name

    def _select_adapter(self, manifest: CapabilityManifest, preferred: str | None = None) -> Any:
        """Override to use simulated adapter by default."""
        if preferred and preferred in self._adapters:
            return self._adapters[preferred]
        if "simulated" in self._adapters:
            return self._adapters["simulated"]
        return super()._select_adapter(manifest, preferred)


def register_mock_capabilities(
    executor: Executor,
    capability_list: list[dict[str, Any]] | None = None,
) -> dict[str, CapabilityManifest]:
    """
    Register mock capabilities that match the SimulatedAdapter's behaviors.

    Args:
        executor: The executor to register with.
        capability_list: Optional list of capability descriptors.
            Each dict: {"name": str, "input": dict, "output": dict}

    Returns:
        Dict mapping capability names to CapabilityManifests.
    """
    if capability_list is None:
        capability_list = [
            {
                "name": "web_search",
                "description": "Search the web for information",
                "input": {"query": FieldSchema(type="string", description="Search query")},
                "output": {"results": FieldSchema(type="array", description="Search results")},
            },
            {
                "name": "financial_data_query",
                "description": "Query financial data",
                "input": {"ticker": FieldSchema(type="string", description="Stock ticker")},
                "output": {"statements": FieldSchema(type="object", description="Financial data")},
            },
            {
                "name": "financial_analyze",
                "description": "Analyze financial data",
                "input": {"data": FieldSchema(type="object", description="Data to analyze")},
                "output": {"analysis": FieldSchema(type="object", description="Analysis result")},
            },
            {
                "name": "report_generate",
                "description": "Generate a report",
                "input": {"content": FieldSchema(type="string", description="Report content")},
                "output": {"report": FieldSchema(type="string", description="Generated report")},
            },
            {
                "name": "text_analyze",
                "description": "Analyze text content",
                "input": {"text": FieldSchema(type="string", description="Text to analyze")},
                "output": {"result": FieldSchema(type="string", description="Analysis result")},
            },
            {
                "name": "text_summarize",
                "description": "Summarize text",
                "input": {"text": FieldSchema(type="string", description="Text to summarize")},
                "output": {"summary": FieldSchema(type="string", description="Summary")},
            },
            {
                "name": "web_fetch",
                "description": "Fetch web content",
                "input": {"url": FieldSchema(type="string", description="URL to fetch")},
                "output": {"content": FieldSchema(type="string", description="Fetched content")},
            },
        ]

    from core.models import CapabilityManifest, MetadataSpec, RequirementSpec, SecuritySpec

    manifests = {}
    for cap_def in capability_list:
        manifest = CapabilityManifest(
            metadata=MetadataSpec(
                name=cap_def["name"],
                version="1.0.0",
                description=cap_def.get("description", ""),
            ),
            input_schema=cap_def.get("input", {}),
            output_schema=cap_def.get("output", {}),
            requirements=RequirementSpec(models=["simulated"]),
            security=SecuritySpec(),
        )
        manifests[cap_def["name"]] = manifest

    return manifests
