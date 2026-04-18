from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from databricks_mcp_agent_hello_world.cli import print_preflight_summary
from databricks_mcp_agent_hello_world.preflight import run_preflight
from tests.conftest import write_workspace_config


def test_preflight_returns_expected_checks_for_local_mode(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    config_path = write_workspace_config(tmp_path)

    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.preflight.get_workspace_client",
        lambda settings: SimpleNamespace(config=SimpleNamespace(host="https://example.com")),
    )
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.preflight.get_spark_session",
        lambda: None,
    )

    report = run_preflight(str(config_path))
    print_preflight_summary(report)

    assert report.overall_status == "pass"
    assert [check.name for check in report.checks] == [
        "config_file",
        "dotenv",
        "databricks_client",
        "llm_endpoint_name",
        "provider_factory",
        "tool_registry_nonempty",
        "persistence_targets",
        "persistence_reachability",
    ]
    assert report.settings_summary == {
        "tool_provider_type": "local_python",
        "llm_endpoint_name": "endpoint-a",
        "dotenv_path": None,
    }
    assert capsys.readouterr().out.startswith("Preflight: pass\n")


def test_preflight_reports_local_event_store_targets(tmp_path: Path, monkeypatch) -> None:
    config_path = write_workspace_config(tmp_path)

    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.preflight.get_workspace_client",
        lambda settings: SimpleNamespace(config=SimpleNamespace(host="https://example.com")),
    )
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.preflight.get_spark_session",
        lambda: None,
    )

    report = run_preflight(str(config_path))
    persistence_check = next(
        check for check in report.checks if check.name == "persistence_targets"
    )

    assert persistence_check.details == {
        "agent_events_table": "main.agent.agent_events",
        "local_data_dir": "./.local_state",
        "spark_available": False,
    }


def test_preflight_requires_agent_events_table_when_spark_is_available(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config_path = write_workspace_config(
        tmp_path,
        include_databricks_profile=False,
        extra_lines=None,
    )
    config_path.write_text(
        "\n".join(
            [
                "llm_endpoint_name: endpoint-a",
                "tool_provider_type: local_python",
                "storage:",
                "  local_data_dir: ./.local_state",
            ]
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.preflight.get_workspace_client",
        lambda settings: SimpleNamespace(config=SimpleNamespace(host="https://example.com")),
    )
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.preflight.get_spark_session",
        lambda: SimpleNamespace(),
    )

    report = run_preflight(str(config_path))
    persistence_check = next(
        check for check in report.checks if check.name == "persistence_targets"
    )

    assert report.overall_status == "fail"
    assert persistence_check.status == "fail"
    assert persistence_check.details == {
        "missing": ["agent_events_table"],
        "local_data_dir": "./.local_state",
    }


def test_preflight_reports_uninitialized_remote_storage_with_next_step(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config_path = write_workspace_config(tmp_path)

    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.preflight.get_workspace_client",
        lambda settings: SimpleNamespace(config=SimpleNamespace(host="https://example.com")),
    )
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.preflight.get_spark_session",
        lambda: SimpleNamespace(),
    )
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.preflight.storage_table_exists",
        lambda spark, table_name: False,
    )

    report = run_preflight(str(config_path))
    reachability_check = next(
        check for check in report.checks if check.name == "persistence_reachability"
    )

    assert reachability_check.status == "fail"
    assert reachability_check.details["agent_events_table"] == "main.agent.agent_events"
    assert reachability_check.details["next_step"] == "init_storage_job"
