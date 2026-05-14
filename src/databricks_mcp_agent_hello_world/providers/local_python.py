from __future__ import annotations

import logging

from ..app.registry import list_local_tools
from ..config import Settings
from ..tools.local import local_definition_to_runtime_tool
from ..tools.runtime import RuntimeTool
from .base import ToolProvider

logger = logging.getLogger(__name__)


class LocalPythonToolProvider(ToolProvider):
    provider_type = "local_python"
    provider_id = "builtin_tools"

    def __init__(self, settings: Settings | None = None):
        self.settings = settings

    def list_tools(self) -> list[RuntimeTool]:
        return [local_definition_to_runtime_tool(tool) for tool in list_local_tools()]
