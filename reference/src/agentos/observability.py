"""
Agent OS — Observability Layer: Trace Collector & Timeline Renderer.

Collects execution traces from the Event Bus and renders them as
a human-readable timeline with state chains and cost statistics.

No external dependencies — pure Python standard library.
No additional instrumentation — data flows through existing Event Bus.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


# ── TraceCollector ─────────────────────────────────────────────────


class TraceCollector:
    """Subscribe → collect → render.

    Subscribes to Event Bus event type prefixes, aggregates them into
    an ordered timeline, tracks per-task state chains, and computes
    per-capability invocation statistics.

    Data sources (all from existing Event Bus — zero extra instrumentation):
    - Task:Created, Task:Queued, Task:Running, Task:Completed, Task:Failed
    - Execution:Created, Execution:Running, Execution:Completed, Execution:Failed
    - plan.ready, workflow.loaded, Review:Passed, Review:Failed
    - Registry:CapabilityRegistered
    """

    def __init__(self) -> None:
        self._timeline: list[dict] = []
        self._task_chains: dict[str, list[str]] = {}
        self._capability_stats: dict[str, dict] = {}
        self._start_time: datetime | None = None
        self._task_times: dict[str, datetime] = {}
        self._task_running_times: dict[str, datetime] = {}
        self._task_cap_types: dict[str, str] = {}
        self._cap_start_times: dict[str, datetime] = {}
        self._workflow_id: str = "unknown"
        self._total_tasks: int = 0

    # ── Event processing ────────────────────────────────────────────

    def consume(self, event_type: str, payload: dict,
                timestamp: str = "") -> None:
        """Process one event (called from the Event Bus subscriber).

        Args:
            event_type: The Event's ``event_type`` field.
            payload: The Event's ``payload`` dict.
            timestamp: ISO-8601 timestamp string.  If empty, ``now()`` is used.
        """
        ts = timestamp or datetime.now(timezone.utc).isoformat()
        try:
            parsed_ts = datetime.fromisoformat(ts)
        except (ValueError, TypeError):
            parsed_ts = datetime.now(timezone.utc)

        if self._start_time is None:
            self._start_time = parsed_ts

        elapsed = (parsed_ts - self._start_time).total_seconds()

        entry: dict[str, Any] = {
            "timestamp": ts,
            "event_type": event_type,
            "payload": dict(payload),
            "elapsed_sec": round(elapsed, 3),
        }
        self._timeline.append(entry)

        # ── Track task state chains ──────────────────────────────────
        task_id = payload.get("task_id", "")
        if event_type.startswith("Task:"):
            # Normalize suffix to state name
            state = event_type.split(":", 1)[1]
            if task_id not in self._task_chains:
                self._task_chains[task_id] = []
            self._task_chains[task_id].append(state)

            if event_type == "Task:Running":
                self._task_running_times[task_id] = parsed_ts
            elif event_type in ("Task:Completed", "Task:Failed"):
                self._task_times.setdefault(task_id, parsed_ts)

        # ── Track capability-level timing ────────────────────────────
        cap_type = payload.get("type", "")
        if event_type == "Task:Running" and cap_type:
            if cap_type not in self._capability_stats:
                self._capability_stats[cap_type] = {
                    "call_count": 0,
                    "success_count": 0,
                    "fail_count": 0,
                    "total_duration_ms": 0,
                }
            self._capability_stats[cap_type]["call_count"] += 1
            key = f"{task_id}::{cap_type}"
            self._cap_start_times[key] = parsed_ts
            # Remember which capability type this task runs
            self._task_cap_types[task_id] = cap_type

        if event_type == "Task:Completed":
            cap_type = self._task_cap_types.get(task_id, payload.get("type", ""))
            if cap_type and cap_type in self._capability_stats:
                key = f"{task_id}::{cap_type}"
                start = self._cap_start_times.get(key)
                if start:
                    dur_ms = (parsed_ts - start).total_seconds() * 1000
                else:
                    start_r = self._task_running_times.get(task_id, parsed_ts)
                    dur_ms = (parsed_ts - start_r).total_seconds() * 1000
                self._capability_stats[cap_type]["total_duration_ms"] += dur_ms
                self._capability_stats[cap_type]["success_count"] += 1

        if event_type == "Task:Failed":
            cap_type = self._task_cap_types.get(task_id, payload.get("type", ""))
            if cap_type and cap_type in self._capability_stats:
                key = f"{task_id}::{cap_type}"
                start = self._cap_start_times.get(key)
                if start:
                    dur_ms = (parsed_ts - start).total_seconds() * 1000
                else:
                    start_r = self._task_running_times.get(task_id, parsed_ts)
                    dur_ms = (parsed_ts - start_r).total_seconds() * 1000
                self._capability_stats[cap_type]["total_duration_ms"] += dur_ms
                self._capability_stats[cap_type]["fail_count"] += 1

        # ── Track workflow/execution metadata ────────────────────────
        if event_type == "workflow.loaded":
            self._workflow_id = payload.get("workflow_id", self._workflow_id)
        if event_type == "Execution:Created":
            self._workflow_id = payload.get("workflow_ref", self._workflow_id)
            self._total_tasks = payload.get("task_count", 0)

    # ── Rendering ───────────────────────────────────────────────────

    def render_timeline(self) -> str:
        """Render the ordered event timeline with icons and elapsed times."""
        lines: list[str] = []
        lines.append("── Timeline (events) ────────────────────────────────")
        lines.append("")

        if not self._timeline:
            lines.append("  (no events captured)")
            lines.append("")
            return "\n".join(lines)

        for i, entry in enumerate(self._timeline):
            ts_raw = entry["timestamp"]
            # Shorten ISO timestamp to HH:MM:SS.ffffff
            if len(ts_raw) >= 19:
                ts_short = ts_raw[11:26].rstrip("Z")
            else:
                ts_short = ts_raw

            idx = f"[{i + 1:3d}]"
            elapsed = f"+{entry['elapsed_sec']:7.3f}s"
            etype = entry["event_type"]

            icon = self._icon_for(etype)

            # Compact payload summary (skip large objects like execution_result)
            payload_items = [
                f"{k}={v}" for k, v in entry["payload"].items()
                if k != "execution_result"
            ]
            payload_str = ", ".join(payload_items)
            if len(payload_str) > 100:
                payload_str = payload_str[:97] + "..."

            lines.append(f"  {idx} {icon} {elapsed}  {etype}")
            if payload_str:
                lines.append(f"        └─ {payload_str}")
        lines.append("")
        return "\n".join(lines)

    def render_state_chains(self) -> str:
        """Render per-task state transition chains."""
        lines: list[str] = []
        lines.append("── Task State Chains ────────────────────────────────")
        lines.append("")

        if not self._task_chains:
            lines.append("  (no task state history captured)")
            lines.append("")
            return "\n".join(lines)

        for task_id, states in self._task_chains.items():
            chain = " → ".join(states)
            task_icon = "✓" if "Completed" in states else "✗" if "Failed" in states else "⏳"
            lines.append(f"  {task_icon} {task_id:25s}  {chain}")
        lines.append("")
        return "\n".join(lines)

    def render_cost_stats(self) -> str:
        """Render per-capability invocation statistics."""
        lines: list[str] = []
        lines.append("── Capability Statistics ────────────────────────────")
        lines.append("")

        if not self._capability_stats:
            lines.append("  (no capability invocations recorded)")
            lines.append("")
            return "\n".join(lines)

        header = (
            f"  {'Capability':20s}  {'Calls':>6s}  "
            f"{'Succeed':>7s}  {'Failed':>7s}  "
            f"{'Avg ms':>8s}  {'Total ms':>10s}"
        )
        sep = (
            f"  {'─' * 20}  {'─' * 6}  "
            f"{'─' * 7}  {'─' * 7}  "
            f"{'─' * 8}  {'─' * 10}"
        )
        lines.append(header)
        lines.append(sep)

        for cap_type in sorted(self._capability_stats):
            st = self._capability_stats[cap_type]
            avg = (
                round(st["total_duration_ms"] / st["call_count"], 1)
                if st["call_count"]
                else 0.0
            )
            lines.append(
                f"  {cap_type:20s}  {st['call_count']:>6d}  "
                f"{st['success_count']:>7d}  {st['fail_count']:>7d}  "
                f"{avg:>8.1f}  {st['total_duration_ms']:>10.0f}"
            )
        lines.append("")
        return "\n".join(lines)

    def render_all(self) -> str:
        """Render the complete trace banner + timeline + chains + stats."""
        parts: list[str] = [
            self._banner(),
            self.render_timeline(),
            self.render_state_chains(),
            self.render_cost_stats(),
        ]
        return "\n".join(parts)

    # ── Helpers ─────────────────────────────────────────────────────

    @staticmethod
    def _icon_for(event_type: str) -> str:
        t = event_type
        if "Task:Completed" in t:
            return "✓"
        if "Task:Failed" in t:
            return "✗"
        if "Task:Running" in t:
            return "▶"
        if "Task:Queued" in t:
            return "○"
        if "Task:Created" in t:
            return "·"
        if "Execution:Created" in t:
            return "●"
        if "Execution:Running" in t:
            return "►"
        if "Execution:Completed" in t or "Execution:Failed" in t:
            return "■"
        if "plan." in t:
            return "◇"
        if "workflow." in t:
            return "◆"
        if "Review:Passed" in t:
            return "★"
        if "Review:Failed" in t:
            return "☆"
        if "Registry:" in t:
            return "▣"
        return "·"

    @staticmethod
    def _banner() -> str:
        lines = [
            "",
            "╭──────────────────────────────────────────────────────╮",
            "│           Agent OS — Execution Trace (--trace)       │",
            "╰──────────────────────────────────────────────────────╯",
            "",
        ]
        return "\n".join(lines)
