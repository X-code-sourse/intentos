"""LLM capability — calls OpenAI-compatible API, falls back to mock."""
from ..llm_executor import call_llm
from ..models import PlannedTask
from typing import Any

def llm(task: PlannedTask, context: dict[str, Any]) -> str:
    prompt = task.params.get("prompt", str(context))
    system = task.params.get("system", "You are a helpful financial analyst.")
    try:
        return call_llm(prompt, system_prompt=system)
    except (ConnectionError, ValueError) as e:
        import logging
        logging.warning("LLM API call failed, falling back to mock: %s", e)
        return (
            f"【LLM 分析结果 — API不可用，使用模拟数据】\n\n"
            f"输入提示: {prompt[:100]}...\n\n"
            "## 投资亮点\n"
            "- 行业领先地位\n"
            "- 强劲的营收增长\n\n"
            "## 风险因素\n"
            "- 市场竞争加剧\n"
            "- 监管不确定性\n\n"
            "## 综合评估\n"
            "建议持续关注。（注: v1 模拟数据）"
        )
