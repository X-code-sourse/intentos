"""Built-in capabilities registry."""
from .search import search
from .llm import llm
from .review import review
from .report import report

CAPABILITIES = {
    "search": search,
    "llm": llm,
    "gather": review,
    "review": review,
    "report": report,
}

__all__ = ["search", "llm", "review", "report", "CAPABILITIES"]
