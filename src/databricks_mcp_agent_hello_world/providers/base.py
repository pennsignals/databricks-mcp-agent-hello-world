from __future__ import annotations

from abc import ABC, abstractmethod

from ..tools.runtime import RuntimeTool


class ToolProvider(ABC):
    provider_type: str
    provider_id: str

    @abstractmethod
    def list_tools(self) -> list[RuntimeTool]:
        raise NotImplementedError
