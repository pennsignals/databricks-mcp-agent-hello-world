from __future__ import annotations

from ..config import Settings

_runtime_settings: Settings | None = None


def set_runtime_settings(settings: Settings) -> None:
    global _runtime_settings
    _runtime_settings = settings


def get_runtime_settings() -> Settings | None:
    return _runtime_settings
