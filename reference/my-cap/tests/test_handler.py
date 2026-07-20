"""Tests for the my-cap capability."""
from my_cap.handler import handler
from unittest.mock import MagicMock


def test_handler_returns_result():
    task = MagicMock()
    task.id = "t1"
    task.type = "my-cap"
    task.params = {"query": "test"}
    context = {}

    result = handler(task, context)
    assert result is not None
    assert "result" in result


def test_handler_receives_params():
    task = MagicMock()
    task.id = "t1"
    task.type = "my-cap"
    task.params = {"query": "hello world"}
    context = {}

    result = handler(task, context)
    assert "hello world" in result["result"]
