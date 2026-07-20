"""Search capability — v1 mock, API interface ready for real integration."""
from ..models import PlannedTask
from typing import Any

def search(task: PlannedTask, context: dict[str, Any]) -> str:
    query = task.params.get("query", "")
    return (
        f"【搜索结果】\n查询: {query}\n\n"
        f"1. {query} 最新动态摘要\n"
        f"2. {query} 行业分析\n"
        f"3. 相关市场数据\n\n"
        "（注: v1 原型使用模拟数据，实际搜索 API 将在后续迭代接入）"
    )
