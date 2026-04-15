from __future__ import annotations

import hashlib
import json
import logging

from ..config import Settings
from ..models import ToolCall, ToolResult, ToolSpec
from ..tooling.runtime import set_runtime_settings
from ..tools.registry import get_tool_function, list_tool_specs
from .base import ToolExecutor, ToolProvider

logger = logging.getLogger(__name__)


class LocalPythonToolProvider(ToolProvider):
    provider_type = "local_python"
    provider_id = "builtin_tools"

    def list_tools(self) -> list[ToolSpec]:
        return list_tool_specs()

    def inventory_hash(self) -> str:
        payload = json.dumps(
            [
                {
                    "tool_name": tool.tool_name,
                    "description": tool.description,
                    "input_schema": tool.input_schema,
                    "version": tool.version,
                    "provider_type": tool.provider_type,
                    "provider_id": tool.provider_id,
                    "capability_tags": tool.capability_tags,
                    "side_effect_level": tool.side_effect_level,
                    "data_domains": tool.data_domains,
                    "example_uses": tool.example_uses,
                }
                for tool in sorted(self.list_tools(), key=lambda item: item.tool_name)
            ],
            sort_keys=True,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


class LocalPythonToolExecutor(ToolExecutor):
    def __init__(self, settings: Settings | None = None):
        self.settings = settings
        if settings:
            set_runtime_settings(settings)

    def call_tool(self, tool_call: ToolCall) -> ToolResult:
        try:
            fn = get_tool_function(tool_call.tool_name)
            content = fn(**tool_call.arguments)
            backend_mode = (
                getattr(self.settings, "local_tool_backend_mode", "auto")
                if self.settings
                else "unknown"
            )
            logger.info("Executed local tool %s", tool_call.tool_name)
            return ToolResult(
                tool_name=tool_call.tool_name,
                status="ok",
                content=content,
                metadata={
                    "provider_type": "local_python",
                    "backend_mode": backend_mode,
                    "request_id": tool_call.request_id,
                    "profile_name": tool_call.profile_name,
                    "profile_version": tool_call.profile_version,
                },
            )
        except Exception as exc:  # noqa: BLE001
            backend_mode = (
                getattr(self.settings, "local_tool_backend_mode", "auto")
                if self.settings
                else "unknown"
            )
            logger.exception("Local tool execution failed for %s", tool_call.tool_name)
            return ToolResult(
                tool_name=tool_call.tool_name,
                status="error",
                content={},
                metadata={
                    "provider_type": "local_python",
                    "backend_mode": backend_mode,
                    "request_id": tool_call.request_id,
                    "profile_name": tool_call.profile_name,
                    "profile_version": tool_call.profile_version,
                },
                error=str(exc),
            )
