from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

ToolSourceType = Literal["local_python", "databricks_mcp"]


@dataclass(frozen=True, slots=True)
class ToolSource:
    type: ToolSourceType
    id: str


@dataclass(frozen=True, slots=True)
class RuntimeTool:
    name: str
    spec: dict[str, Any]
    execute: Callable[..., Any]
    source: ToolSource


def inventory_hash(tools: list[RuntimeTool]) -> str:
    payload = json.dumps(
        [
            {
                "name": tool.name,
                "spec": tool.spec,
                "source": {
                    "type": tool.source.type,
                    "id": tool.source.id,
                },
            }
            for tool in sorted(tools, key=lambda item: item.name)
        ],
        sort_keys=True,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
