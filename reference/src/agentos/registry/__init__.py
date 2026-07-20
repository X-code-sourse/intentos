"""Capability + Workflow Registry — RFC-0300."""
from __future__ import annotations
import logging
from pathlib import Path
from typing import Any, Callable
from ..backbone.bus import EventBus

from .manifest import CapabilityManifest, load_manifest_from_yaml
from .workflows import WorkflowIndex

logger = logging.getLogger(__name__)


class Registry:
    """In-memory capability registry.

    API: register / list / get / find_by_type
    """

    def __init__(self, bus: EventBus | None = None) -> None:
        self._bus = bus
        self._capabilities: dict[str, CapabilityManifest] = {}
        self.workflows = WorkflowIndex()

    # ── Capability registration ────────────────────────────────────

    def register_manifest(
        self,
        task_type: str,
        manifest: CapabilityManifest,
    ) -> None:
        """Register a capability manifest under *task_type*."""
        self._capabilities[task_type] = manifest
        manifest.task_type = task_type
        logger.debug("Registry: capability %s v%s registered", task_type, manifest.version)

    def register(
        self,
        task_type: str,
        fn: Callable,
        *,
        display_name: str = "",
        version: str = "0.1.0",
        tags: list[str] | None = None,
    ) -> None:
        """Convenience: create manifest and register in one call."""
        m = CapabilityManifest(
            task_type=task_type, fn=fn,
            display_name=display_name or task_type,
            version=version, tags=tags or [],
        )
        self.register_manifest(task_type, m)

    # ── Capability query ───────────────────────────────────────────

    def resolve(self, task_type: str) -> CapabilityManifest | None:
        """Get manifest by task_type. Alias: get()."""
        return self._capabilities.get(task_type)

    get = resolve

    def find_by_type(self, task_type: str) -> CapabilityManifest | None:
        """Query alias for Planner compatibility."""
        return self._capabilities.get(task_type)

    def list(self) -> list[CapabilityManifest]:
        return list(self._capabilities.values())

    def list_enabled(self) -> list[CapabilityManifest]:
        return [m for m in self._capabilities.values() if m.enabled]

    @property
    def count(self) -> int:
        return len(self._capabilities)

    # ── Batch load ─────────────────────────────────────────────────

    def load_builtins(self) -> None:
        """Register all built-in capabilities from the capabilities module."""
        from ..capabilities import CAPABILITY_MANIFESTS
        for m in CAPABILITY_MANIFESTS:
            self.register_manifest(m.task_type, m)

    # ── Snapshot ───────────────────────────────────────────────────

    def snapshot(self) -> dict:
        return {
            "capabilities": [
                {"task_type": m.task_type, "version": m.version,
                 "source": m.source, "enabled": m.enabled}
                for m in self._capabilities.values()
            ],
        }
