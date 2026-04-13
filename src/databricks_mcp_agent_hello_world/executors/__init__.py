"""Execution backends for agent tool calls."""

from .factory import get_tool_executor

__all__ = ["get_tool_executor"]
