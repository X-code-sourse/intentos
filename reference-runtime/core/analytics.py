"""
Intent OS — Execution Analytics (SPEC-0003 Learning Backbone)

Analyzes execution history to produce actionable insights.

The Analytics module is the bridge between raw Event Store data and
system optimization. It provides:

  - Performance summaries by capability, runtime, and time period
  - Failure pattern recognition and trending
  - Cost analysis and anomaly detection
  - Data exports for Planner Cost Model training

This is the foundation of the Evolution Loop (Algorithm 5).
Phase 1 provides basic aggregation and reporting.
Phase 3+ will feed directly into the Probabilistic Query Optimizer.
"""

from __future__ import annotations

import json
import statistics
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from core.event_store import EventStore


class AnalyticsError(Exception):
    """Raised when analytics operations fail."""
    pass


class AnalyticsEngine:
    """
    Execution history analysis engine.

    Aggregates data from the Event Store to produce performance metrics,
    trend analysis, and optimization suggestions.

    Usage:
        store = EventStore("path/to/store.db")
        analytics = AnalyticsEngine(store)

        # Get capability rankings
        rankings = analytics.get_capability_rankings()

        # Get cost optimization suggestions
        suggestions = analytics.get_cost_suggestions()
    """

    def __init__(self, event_store: EventStore) -> None:
        self._store = event_store

    # ── Capability Performance ──

    def get_capability_rankings(self) -> list[dict[str, Any]]:
        """
        Rank capabilities by overall performance score.

        Score combines: success_rate (40%), avg_latency (25%),
        avg_cost (25%), execution_count (10%).

        Returns:
            Ranked list of capability performance summaries.
        """
        raw_stats = self._store.get_capability_stats()
        if not raw_stats:
            return []

        # Normalize metrics for scoring
        max_count = max(s.get("total_runs", 1) for s in raw_stats)
        min_latency = min(
            (s.get("avg_latency_ms", 0) or 0) for s in raw_stats
        )
        max_latency = max(
            (s.get("avg_latency_ms", 0) or 0) for s in raw_stats
        )
        min_cost = min(
            (s.get("avg_cost_usd", 0) or 0) for s in raw_stats
        )
        max_cost = max(
            (s.get("avg_cost_usd", 0) or 0) for s in raw_stats
        )

        ranked: list[dict[str, Any]] = []
        for stat in raw_stats:
            latency_range = max(max_latency - min_latency, 1)
            cost_range = max(max_cost - min_cost, 0.001)

            # Normalized scores (0-100)
            success_score = (stat.get("success_rate", 0) or 0) * 100
            latency_score = (
                100 - ((stat.get("avg_latency_ms", 0) - min_latency)
                       / latency_range * 100)
                if max_latency > min_latency else 100
            )
            cost_score = (
                100 - ((stat.get("avg_cost_usd", 0) - min_cost)
                       / cost_range * 100)
                if max_cost > min_cost else 100
            )
            count_score = (
                stat.get("total_runs", 0) / max_count * 100
                if max_count > 0 else 0
            )

            overall = (
                0.40 * success_score
                + 0.25 * latency_score
                + 0.25 * cost_score
                + 0.10 * count_score
            )

            ranked.append({
                "capability": stat.get("manifest_name", "unknown"),
                "total_runs": stat.get("total_runs", 0),
                "success_rate": round((stat.get("success_rate", 0) or 0), 4),
                "avg_latency_ms": round(stat.get("avg_latency_ms", 0) or 0, 1),
                "avg_cost_usd": round(stat.get("avg_cost_usd", 0) or 0, 4),
                "avg_tokens": round(stat.get("avg_tokens", 0) or 0, 0),
                "performance_score": round(overall, 1),
            })

        ranked.sort(key=lambda x: -x["performance_score"])
        return ranked

    def get_runtime_comparison(self) -> list[dict[str, Any]]:
        """
        Compare performance across different runtimes.

        Returns:
            Runtime comparison data with relative performance scores.
        """
        return self._store.get_runtime_stats()

    # ── Trend Analysis ──

    def get_trend_summary(
        self,
        days: int = 7,
    ) -> dict[str, Any]:
        """
        Get a summary of execution trends over a period.

        Args:
            days: Number of days to analyze.

        Returns:
            Dict with trend metrics.
        """
        since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()

        daily = self._store.get_time_series(interval="day", since=since)
        hourly = self._store.get_time_series(interval="hour", since=since)

        # Recent records
        recent_records = self._store.query_records(limit=20)

        # Failure analysis
        failures = self._store.get_failure_analysis()

        # Capability rankings
        rankings = self.get_capability_rankings()

        return {
            "period_days": days,
            "total_executions": sum(r.get("run_count", 0) for r in daily),
            "daily_breakdown": daily,
            "hourly_breakdown": hourly[:48],  # Last 48 hours
            "recent_executions": recent_records[:10],
            "failure_patterns": failures[:10],
            "top_capabilities": rankings[:10],
            "analysis_timestamp": datetime.now(timezone.utc).isoformat(),
        }

    def get_cost_trend(self, days: int = 30) -> dict[str, Any]:
        """
        Analyze execution cost trends.

        Args:
            days: Analysis period in days.

        Returns:
            Cost trend data with daily totals and projections.
        """
        since = (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()
        daily = self._store.get_time_series(interval="day", since=since)

        total_cost = sum(r.get("avg_cost_usd", 0) * r.get("run_count", 0)
                         for r in daily)
        total_runs = sum(r.get("run_count", 0) for r in daily)

        # Per-runtime cost breakdown
        runtime_stats = self._store.get_runtime_stats()

        return {
            "period_days": days,
            "total_executions": total_runs,
            "total_cost_usd": round(total_cost, 4),
            "avg_cost_per_execution": round(
                total_cost / max(total_runs, 1), 4
            ),
            "daily_cost_trend": [
                {
                    "date": d.get("period", ""),
                    "executions": d.get("run_count", 0),
                    "cost_usd": round(
                        (d.get("avg_cost_usd", 0) or 0) * d.get("run_count", 0),
                        4,
                    ),
                    "avg_latency_ms": round(d.get("avg_latency_ms", 0) or 0, 1),
                }
                for d in daily[-30:]  # Last 30 entries
            ],
            "cost_by_runtime": [
                {
                    "runtime": r.get("runtime_id", "unknown"),
                    "total_runs": r.get("total_runs", 0),
                    "avg_cost": round(r.get("avg_cost_usd", 0) or 0, 4),
                }
                for r in runtime_stats
            ],
        }

    # ── Failure Analysis ──

    def get_failure_report(self) -> dict[str, Any]:
        """
        Comprehensive failure analysis report.

        Returns:
            Dict with failure patterns, most error-prone capabilities,
            and runtime-specific failure rates.
        """
        failures = self._store.get_failure_analysis()
        all_stats = self._store.get_capability_stats()
        runtime_stats = self._store.get_runtime_stats()

        # Calculate overall failure rate
        total_records = self._store.get_record_count()
        total_failures = sum(
            s.get("failure_count", 0) for s in all_stats
        ) if total_records > 0 else 0

        # Most error-prone capabilities
        error_prone: list[dict[str, Any]] = []
        for stat in all_stats:
            failure_count = stat.get("failure_count", 0) or 0
            total = stat.get("total_runs", 1) or 1
            if failure_count > 0:
                error_prone.append({
                    "capability": stat.get("manifest_name", "unknown"),
                    "failure_count": failure_count,
                    "total_runs": total,
                    "failure_rate": round(failure_count / max(total, 1), 4),
                })
        error_prone.sort(key=lambda x: -x["failure_rate"])

        return {
            "total_records": total_records,
            "total_failures": total_failures,
            "overall_failure_rate": round(
                total_failures / max(total_records, 1), 4
            ),
            "failure_patterns": [
                {
                    "capability": f.get("manifest_name", "unknown"),
                    "runtime": f.get("runtime_id", "unknown"),
                    "failure_count": f.get("failure_count", 0),
                    "avg_latency_ms": round(f.get("avg_latency_ms", 0) or 0, 1),
                }
                for f in failures[:20]
            ],
            "most_error_prone": error_prone[:10],
            "runtime_failure_rates": [
                {
                    "runtime": r.get("runtime_id", "unknown"),
                    "total_runs": r.get("total_runs", 0),
                    "success_rate": round(r.get("success_rate", 0) or 0, 4),
                }
                for r in runtime_stats
            ],
        }

    # ── Cost Model Data Export ──

    def export_cost_model_data(
        self,
        limit: int = 1000,
        output_path: str | None = None,
    ) -> list[dict[str, Any]]:
        """
        Export execution data formatted for Planner Cost Model training.

        Produces records optimized for training a probabilistic cost model:
          - Input: capability, runtime, input_size
          - Target: latency, cost, token_count, success

        Args:
            limit: Maximum records to export.
            output_path: Optional JSON file path to write to.

        Returns:
            List of training records.
        """
        records = self._store.query_records(limit=limit)
        training_data: list[dict[str, Any]] = []

        for record in records:
            input_data = json.loads(record.get("input", "{}") or "{}")
            input_size = len(json.dumps(input_data))

            training_data.append({
                "capability": record.get("manifest_name", "unknown"),
                "capability_version": record.get("manifest_version", ""),
                "runtime": record.get("runtime_id", "unknown"),
                "adapter": record.get("adapter", ""),
                "input_size_chars": input_size,
                "latency_ms": record.get("total_latency_ms", 0),
                "cost_usd": record.get("total_cost_usd", 0),
                "tokens": record.get("total_tokens", 0),
                "success": record.get("status") == "success",
                "error": record.get("error"),
                "timestamp": record.get("created_at", ""),
            })

        if output_path:
            output = Path(output_path)
            output.write_text(
                json.dumps(training_data, indent=2, default=str),
                encoding="utf-8",
            )

        return training_data

    # ── Optimization Suggestions ──

    def get_optimization_suggestions(self) -> list[dict[str, Any]]:
        """
        Generate actionable optimization suggestions based on execution history.

        Analyzes patterns and suggests:
          - Runtime switches (cheaper/faster alternatives)
          - Capability upgrades (better versions)
          - Configuration changes (timeout adjustments, retry tuning)

        Returns:
            List of suggestion dicts with rationale and expected impact.
        """
        suggestions: list[dict[str, Any]] = []
        runtime_stats = self._store.get_runtime_stats()
        cap_stats = self._store.get_capability_stats()

        # Suggest cheapest runtime per capability
        if len(runtime_stats) >= 2:
            costs = {
                r["runtime_id"]: r.get("avg_cost_usd", 0) or 0
                for r in runtime_stats
            }
            if costs:
                cheapest = min(costs, key=costs.get)
                most_expensive = max(costs, key=costs.get)
                if cheapest != most_expensive and costs[cheapest] < costs[most_expensive]:
                    savings_pct = (
                        (1 - costs[cheapest] / max(costs[most_expensive], 0.001))
                        * 100
                    )
                    suggestions.append({
                        "type": "runtime_optimization",
                        "suggestion": (
                            f"Consider using '{cheapest}' runtime instead of "
                            f"'{most_expensive}' for non-critical executions"
                        ),
                        "rationale": (
                            f"'{cheapest}' costs {costs[cheapest]:.4f} per "
                            f"execution vs '{most_expensive}' at "
                            f"{costs[most_expensive]:.4f} "
                            f"(saving ~{savings_pct:.0f}%)"
                        ),
                        "expected_impact": f"~{savings_pct:.0f}% cost reduction",
                        "confidence": "medium" if savings_pct > 20 else "low",
                    })

        # Suggest capabilities with high failure rates for review
        for cap in cap_stats[:5]:
            failure_rate = 1 - (cap.get("success_rate", 1) or 1)
            if failure_rate > 0.2:  # >20% failure rate
                suggestions.append({
                    "type": "capability_review",
                    "suggestion": (
                        f"Capability '{cap['manifest_name']}' has a "
                        f"{failure_rate * 100:.0f}% failure rate — review needed"
                    ),
                    "rationale": (
                        f"{cap.get('failure_count', 0)} of "
                        f"{cap.get('total_runs', 0)} executions failed"
                    ),
                    "expected_impact": "Improved reliability",
                    "confidence": "high",
                })

        return suggestions
