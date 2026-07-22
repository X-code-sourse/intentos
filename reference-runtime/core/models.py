"""
Intent OS — Core Data Models

Defines the foundational data structures for the reference runtime:
- CapabilityManifest: parsed representation of SPEC-0001
- Event: immutable execution event (SPEC-0003)
- ExecutionRecord: complete execution bundle
- ValidationResult: manifest validation outcome
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any


# ──────────────────────────────────────────────
# Enums
# ──────────────────────────────────────────────

class SecurityRisk(Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class EventType(Enum):
    # Core execution events
    TASK_STARTED = "TaskStarted"
    CAPABILITY_INVOKED = "CapabilityInvoked"
    TASK_COMPLETED = "TaskCompleted"
    TASK_FAILED = "TaskFailed"
    TASK_RETRIED = "TaskRetried"
    TASK_SKIPPED = "TaskSkipped"
    TASK_CANCELLED = "TaskCancelled"
    WORKFLOW_STARTED = "WorkflowStarted"
    WORKFLOW_COMPLETED = "WorkflowCompleted"
    WORKFLOW_FAILED = "WorkflowFailed"
    COST_ACCUMULATED = "CostAccumulated"
    REVIEW_REQUIRED = "ReviewRequired"
    REVIEW_COMPLETED = "ReviewCompleted"
    # System events
    RUNTIME_REGISTERED = "RuntimeRegistered"
    CAPABILITY_REGISTERED = "CapabilityRegistered"
    POLICY_EVALUATED = "PolicyEvaluated"
    RESOURCE_WARNING = "ResourceWarning"


class ExecutionStatus(Enum):
    SUCCESS = "success"
    FAILURE = "failure"
    PARTIAL = "partial"


# ──────────────────────────────────────────────
# Schema types
# ──────────────────────────────────────────────

@dataclass
class FieldSchema:
    """Describes a single field in an input or output schema."""
    type: str
    description: str | None = None
    optional: bool = False
    default: Any | None = None
    min_length: int | None = None
    max_length: int | None = None
    minimum: float | None = None
    maximum: float | None = None
    enum: list[str] | None = None
    properties: dict[str, FieldSchema] | None = None  # for object type
    items: FieldSchema | None = None  # for array type


@dataclass
class RequirementSpec:
    """Operational requirements for a capability."""
    models: list[str] | None = None
    tools: list[str] | None = None
    min_context: int | None = None


@dataclass
class SecuritySpec:
    """Security constraints for a capability."""
    risk: SecurityRisk = SecurityRisk.LOW
    network: bool = False
    data_access: bool = False
    require_approval: bool = False


@dataclass
class CostSpec:
    """Cost estimation hints."""
    estimated_tokens: str | None = None
    estimated_latency: str | None = None
    pricing_hint: str | None = None


@dataclass
class MetadataSpec:
    """Capability manifest metadata."""
    name: str
    version: str
    publisher: str | None = None
    digest: str | None = None
    description: str | None = None
    tags: list[str] | None = None


@dataclass
class CapabilityManifest:
    """
    Parsed representation of an Intent OS Capability Manifest (SPEC-0001).

    This is the core data structure that represents a single AI capability
    that can be discovered, invoked, and executed across different runtimes.
    """
    metadata: MetadataSpec
    input_schema: dict[str, FieldSchema]
    output_schema: dict[str, FieldSchema]
    requirements: RequirementSpec | None = None
    security: SecuritySpec | None = None
    cost: CostSpec | None = None

    @property
    def id(self) -> str:
        """Unique identifier: name@version."""
        return f"{self.metadata.name}@{self.metadata.version}"

    @property
    def name(self) -> str:
        return self.metadata.name

    @property
    def version(self) -> str:
        return self.metadata.version


# ──────────────────────────────────────────────
# Events (SPEC-0003)
# ──────────────────────────────────────────────

@dataclass
class Event:
    """
    An immutable execution event (SPEC-0003).

    Every state change in the runtime is recorded as an Event.
    Events form the foundation for observability and the learning backbone.
    """
    event_type: EventType
    trace_id: str
    timestamp: datetime
    source: str
    sequence: int
    payload: dict[str, Any] | None = None
    metrics: dict[str, Any] | None = None
    workflow_id: str | None = None
    task_id: str | None = None
    capability: str | None = None
    runtime: str | None = None
    adapter_version: str | None = None
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))

    @classmethod
    def create(
        cls,
        event_type: EventType,
        trace_id: str | None = None,
        source: str = "runtime",
        sequence: int = 0,
        payload: dict | None = None,
        metrics: dict | None = None,
        workflow_id: str | None = None,
        task_id: str | None = None,
        capability: str | None = None,
        runtime: str | None = None,
        adapter_version: str | None = None,
    ) -> Event:
        return cls(
            event_type=event_type,
            trace_id=trace_id or str(uuid.uuid4()),
            timestamp=datetime.now(timezone.utc),
            source=source,
            sequence=sequence,
            payload=payload or {},
            metrics=metrics,
            workflow_id=workflow_id,
            task_id=task_id,
            capability=capability,
            runtime=runtime,
            adapter_version=adapter_version,
        )

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dict (SPEC-0003 compliant)."""
        result = {
            "spec_version": "1.0",
            "event_id": self.event_id,
            "event_type": self.event_type.value,
            "trace_id": self.trace_id,
            "timestamp": self.timestamp.isoformat(),
            "source": self.source,
            "sequence": self.sequence,
            "payload": self.payload or {},
        }
        if self.metrics:
            result["metrics"] = self.metrics
        if self.workflow_id:
            result["workflow_id"] = self.workflow_id
        if self.task_id:
            result["task_id"] = self.task_id
        if self.capability:
            result["capability"] = self.capability
        if self.runtime:
            result["runtime"] = self.runtime
        if self.adapter_version:
            result["adapter_version"] = self.adapter_version
        return result


# ──────────────────────────────────────────────
# Execution Record (SPEC-0003)
# ──────────────────────────────────────────────

@dataclass
class ExecutionRecord:
    """
    Complete record of a single execution (SPEC-0003 Section 7.1).

    Bundles the event stream with metadata for compatibility verification.
    This is the primary output of Phase 0 — proving that two runtimes
    produce the same record structure for the same Manifest.
    """
    spec_version: str = "1.0"
    trace_id: str = ""
    manifest_name: str = ""
    manifest_version: str = ""
    runtime_id: str = ""
    adapter: str = ""
    adapter_version: str = ""
    input: Any = None
    output: Any = None
    events: list[Event] = field(default_factory=list)
    status: ExecutionStatus = ExecutionStatus.SUCCESS
    error: str | None = None
    total_latency_ms: float = 0.0
    total_cost_usd: float = 0.0
    total_tokens: int = 0

    def compute_latency_from_events(self) -> float:
        """Calculate total elapsed time from events.

        This is an alternative to the stored total_latency_ms field,
        computed dynamically from event timestamps.
        """
        if not self.events:
            return 0.0
        start = None
        end = None
        for evt in self.events:
            if evt.event_type == EventType.TASK_STARTED:
                start = evt.timestamp
            elif evt.event_type in (EventType.TASK_COMPLETED, EventType.TASK_FAILED):
                end = evt.timestamp
        if start and end:
            return (end - start).total_seconds() * 1000
        return 0.0

    def compute_cost_from_events(self) -> float:
        """Sum cost from all events with cost metrics."""
        total = 0.0
        for evt in self.events:
            if evt.metrics and "cost_usd" in evt.metrics:
                total += evt.metrics["cost_usd"]
        return total

    def compute_tokens_from_events(self) -> int:
        """Sum tokens from all events with token metrics."""
        total = 0
        for evt in self.events:
            if evt.metrics and "token_count" in evt.metrics:
                total += evt.metrics["token_count"]
        return total

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a JSON-compatible dict."""
        return {
            "spec_version": self.spec_version,
            "trace_id": self.trace_id,
            "manifest": {
                "name": self.manifest_name,
                "version": self.manifest_version,
            },
            "runtime": {
                "id": self.runtime_id,
                "adapter": self.adapter,
                "adapter_version": self.adapter_version,
            },
            "input": self.input,
            "output": self.output,
            "status": self.status.value,
            "error": self.error,
            "metrics": {
                "total_latency_ms": self.total_latency_ms,
                "total_cost_usd": self.total_cost_usd,
                "total_tokens": self.total_tokens,
            },
            "events": [e.to_dict() for e in self.events],
        }


# ──────────────────────────────────────────────
# Validation
# ──────────────────────────────────────────────

@dataclass
class ValidationError:
    """A single validation error found during manifest parsing."""
    field: str
    message: str
    severity: str = "error"  # error | warning


@dataclass
class ValidationResult:
    """Result of validating a Capability Manifest."""
    valid: bool
    errors: list[ValidationError] = field(default_factory=list)
    warnings: list[ValidationError] = field(default_factory=list)
