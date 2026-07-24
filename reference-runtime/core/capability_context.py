"""
Intent OS — Capability Context (SPEC-0010 Layer 2)

Aggregates execution records into structured capability profiles with
evidence — not tags, but proven skills with success rates and sample
counts.

Usage::

    from core.capability_context import compute_capability_profile

    profiles = compute_capability_profile("agent_a82f91c3")
    for p in profiles:
        print(f"{p.name}: {p.success_rate:.0%} ({p.total_tasks} tasks)")
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from typing import Any


# Minimum execution count for a capability to appear in the profile
_MIN_SAMPLES = 3


@dataclass
class ProvenPattern:
    """A concrete, evidence-backed capability pattern.

    Each pattern represents one task type this agent has repeatedly
    executed, with measured success rate and cost.
    """
    task_type: str                     # "earnings_analysis" | "dcf_valuation"
    success_rate: float = 0.0          # 0.0–1.0
    sample_count: int = 0
    avg_cost: float = 0.0
    avg_tokens: int = 0
    key_steps: list[str] = field(default_factory=list)


@dataclass
class CapabilityProfile:
    """Complete evidence structure for one of an agent's capabilities.

    Not a tag — every field is backed by execution data.
    """
    name: str                          # "financial_analysis"
    label: str = ""                    # Human-readable label
    level: str = "practitioner"        # practitioner | proficient | expert
    total_tasks: int = 0
    success_rate: float = 0.0
    total_cost_usd: float = 0.0
    total_tokens: int = 0
    preferred_models: list[str] = field(default_factory=list)
    proven_patterns: list[ProvenPattern] = field(default_factory=list)
    limitations: list[str] = field(default_factory=list)


def _level_from_stats(total_tasks: int, success_rate: float) -> str:
    """Derive a proficiency level from measurable stats."""
    if total_tasks >= 1000 and success_rate >= 0.90:
        return "expert"
    if total_tasks >= 100 and success_rate >= 0.80:
        return "proficient"
    return "practitioner"


def compute_capability_profile(agent_id: str,
                               db_path: str | None = None,
                               min_samples: int = _MIN_SAMPLES) -> list[CapabilityProfile]:
    """Aggregate execution records into capability profiles.

    Queries ``execution_records`` grouped by ``manifest_name``.

    Args:
        agent_id: The agent to profile.
        db_path: Optional custom database path (for testing).
        min_samples: Minimum execution count to include a capability
            (default 3). Below this, there isn't enough data for a
            meaningful profile.

    Returns:
        A list of :class:`CapabilityProfile`, sorted by ``total_tasks``
        descending.  Empty list if the agent has no executions.
    """
    from collections import defaultdict

    from core.event_store import EventStore

    event_store = EventStore(db_path)
    conn = event_store.get_connection()

    try:
        # Group by manifest_name — each distinct manifest is a capability
        rows = conn.execute(
            """SELECT manifest_name,
                      COUNT(*)                                          AS total_tasks,
                      SUM(CASE WHEN status = 'success' THEN 1 ELSE 0 END) AS success_count,
                      SUM(CASE WHEN status IN ('failure','partial') THEN 1 ELSE 0 END) AS fail_count,
                      COALESCE(SUM(total_cost_usd), 0)                 AS total_cost,
                      COALESCE(SUM(total_tokens), 0)                   AS total_tokens,
                      AVG(total_latency_ms)                             AS avg_latency
               FROM execution_records
               WHERE agent_id = ?
                 AND manifest_name IS NOT NULL
                 AND manifest_name != ''
               GROUP BY manifest_name
               ORDER BY total_tasks DESC""",
            (agent_id,),
        ).fetchall()

        if not rows:
            return []

        profiles: list[CapabilityProfile] = []

        for row in rows:
            name = row["manifest_name"]
            total = row["total_tasks"] or 0
            if total < min_samples:
                continue

            success_count = row["success_count"] or 0
            success_rate = success_count / max(total, 1)
            total_cost = row["total_cost"] or 0.0
            total_tokens = int(row["total_tokens"] or 0)

            # Build proven patterns: same query but we need per-manifest detail
            # For now, each manifest becomes one pattern itself
            patterns = [
                ProvenPattern(
                    task_type=name,
                    success_rate=success_rate,
                    sample_count=total,
                    avg_cost=total_cost / max(total, 1),
                    avg_tokens=int(total_tokens / max(total, 1)),
                )
            ]

            # Preferred models — query from execution_records
            model_rows = conn.execute(
                """SELECT runtime_id, COUNT(*) AS cnt
                   FROM execution_records
                   WHERE agent_id = ?
                     AND manifest_name = ?
                     AND runtime_id IS NOT NULL
                     AND runtime_id != ''
                   GROUP BY runtime_id
                   ORDER BY cnt DESC
                   LIMIT 3""",
                (agent_id, name),
            ).fetchall()
            models = [r["runtime_id"] for r in model_rows]

            label = name.replace("_", " ").title()

            profile = CapabilityProfile(
                name=name,
                label=label,
                level=_level_from_stats(total, success_rate),
                total_tasks=total,
                success_rate=round(success_rate, 4),
                total_cost_usd=total_cost,
                total_tokens=total_tokens,
                preferred_models=models,
                proven_patterns=patterns,
            )
            profiles.append(profile)

        return profiles

    finally:
        conn.close()
