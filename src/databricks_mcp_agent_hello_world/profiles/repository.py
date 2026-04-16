from __future__ import annotations


class ToolProfileRepository:
    """Legacy stub retained only so old docs/paths resolve during migration."""

    def __init__(self, *args, **kwargs) -> None:
        raise RuntimeError(
            "Tool profiles are no longer used by the runtime. "
            "Run discovery at task start and execute tools directly."
        )
