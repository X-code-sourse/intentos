"""Workflow index — references existing workflow_loader.

Lightweight wrapper that caches workflow scan results and provides
reverse index (which capability types are used by which workflows).
"""

from __future__ import annotations

import logging
from pathlib import Path
from collections import defaultdict

logger = logging.getLogger(__name__)


class WorkflowIndex:
    """Cached index of discovered workflows with reverse capability index."""

    def __init__(self) -> None:
        self._by_id: dict[str, dict] = {}
        self._by_capability: dict[str, set[str]] = defaultdict(set)
        self._scanned_dirs: set[str] = set()

    def track(self, wf_id: str, *, name: str = "", path: str = "",
              task_count: int = 0, capability_types: set[str] | None = None) -> None:
        """Register or update a workflow."""
        old_caps = set()
        if wf_id in self._by_id:
            old_caps = self._by_id[wf_id].get("capability_types", set())
        for ct in old_caps - (capability_types or set()):
            self._by_capability[ct].discard(wf_id)

        self._by_id[wf_id] = {
            "id": wf_id, "name": name or wf_id, "path": str(path),
            "task_count": task_count,
            "capability_types": set(capability_types or set()),
        }
        for ct in (capability_types or set()):
            self._by_capability[ct].add(wf_id)

    def scan(self, extra_dirs: list[Path] | None = None) -> int:
        """Scan workflow directories; returns count of new workflows found."""
        from ..workflow_loader import WORKFLOW_DIRS
        dirs = list(WORKFLOW_DIRS)
        if extra_dirs:
            dirs.extend(extra_dirs)

        found = 0
        for d in dirs:
            resolved = Path(d).resolve()
            rs = str(resolved)
            if rs in self._scanned_dirs:
                continue
            self._scanned_dirs.add(rs)
            if not resolved.is_dir():
                continue
            for f in resolved.glob("*.yaml"):
                try:
                    import yaml
                    with open(f) as fh:
                        raw = yaml.safe_load(fh)
                    tasks = raw.get("tasks", [])
                    caps = {t["type"] for t in tasks if isinstance(t, dict) and "type" in t}
                    self.track(
                        raw.get("id", f.stem),
                        name=raw.get("name", f.stem),
                        path=str(f), task_count=len(tasks),
                        capability_types=caps,
                    )
                    found += 1
                except Exception as exc:
                    logger.warning("Index: skip %s: %s", f, exc)
        return found

    def resolve(self, wf_id: str) -> dict | None:
        return self._by_id.get(wf_id)

    def list(self) -> list[dict]:
        return list(self._by_id.values())

    def workflows_using(self, task_type: str) -> list[dict]:
        return [self._by_id[wid] for wid in self._by_capability.get(task_type, set())
                if wid in self._by_id]

    @property
    def count(self) -> int:
        return len(self._by_id)
