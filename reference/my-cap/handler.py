"""my-cap capability — Agent OS SDK scaffold."""
from __future__ import annotations
from typing import Any


def handler(task, context) -> Any:
    """Execute the my-cap capability.

    Args:
        task: PlannedTask — current task metadata (id, type, params).
        context: dict — outputs from completed tasks, keyed by task_id.

    Returns:
        Any — result injected into downstream task contexts.
    """
    _ = context  # available for cross-task data access

    # ── TODO: implement your capability logic here ──────────────────
    query = task.params.get("query", "")
    result = f"my-cap processed: {{query}}"

    return {"result": result}
