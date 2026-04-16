from __future__ import annotations


class ToolProfileCompiler:
    """Legacy stub retained only so old docs/paths resolve during migration."""

    def __init__(self, *args, **kwargs) -> None:
        raise RuntimeError(
            "Tool profiles are no longer part of the runtime path. "
            "Use discover-tools and run-agent-task directly."
        )
