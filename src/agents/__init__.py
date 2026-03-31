"""src.agents package — AI Workers."""
from src.agents.state import AgenticState


def build_graph():
    from src.agents.graph import build_graph as _build
    return _build()


def compile_graph():
    from src.agents.graph import compile_graph as _compile
    return _compile()


def get_graph():
    from src.agents.graph import get_graph as _get
    return _get()


__all__ = ["AgenticState", "build_graph", "compile_graph", "get_graph"]
