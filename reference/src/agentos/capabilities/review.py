"""Review capability — aggregates previous task outputs."""
from ..models import PlannedTask
from typing import Any

def review(task: PlannedTask, context: dict[str, Any]) -> dict:
    checks = task.params.get("checks", ["non_empty"])
    outputs = {k: v for k, v in context.items() if isinstance(v, str)}
    return {
        "checks": checks,
        "non_empty_count": sum(1 for v in outputs.values() if v.strip()),
        "text": "\n\n".join(outputs.values()),
    }
