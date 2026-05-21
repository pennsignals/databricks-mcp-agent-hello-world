from __future__ import annotations

import logging

from databricks_mcp_agent_hello_world import logging_utils


def test_configure_logging_sets_existing_root_handler_level(isolated_root_logger) -> None:
    isolated_root_logger.handlers = [logging.StreamHandler()]

    logging_utils.configure_logging("debug")

    assert isolated_root_logger.level == logging.DEBUG


def test_configure_logging_uses_basic_config_when_handlers_are_absent(
    monkeypatch,
    isolated_root_logger,
) -> None:
    isolated_root_logger.handlers = []
    basic_config_calls: list[dict[str, object]] = []
    monkeypatch.setattr(
        logging,
        "basicConfig",
        lambda **kwargs: basic_config_calls.append(kwargs),
    )
    monkeypatch.setenv("LOG_LEVEL", "warning")

    logging_utils.configure_logging()

    assert basic_config_calls[0]["level"] == logging.WARNING
