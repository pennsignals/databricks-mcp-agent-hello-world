from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from databricks_tool_agent_template.cli import print_preflight_summary
from databricks_tool_agent_template.models import PreflightReport
from databricks_tool_agent_template.preflight import run_preflight
from tests.conftest import write_workspace_config


def test_preflight_returns_expected_checks_for_local_mode(
    tmp_path: Path,
    monkeypatch,
    capsys,
) -> None:
    config_path = write_workspace_config(tmp_path, agent_events_table=None)

    monkeypatch.setattr(
        "databricks_tool_agent_template.preflight.get_workspace_client",
        lambda settings: SimpleNamespace(config=SimpleNamespace(host="https://example.com")),
    )

    report = run_preflight(str(config_path))
    print_preflight_summary(report)

    assert report.overall_status == "pass"
    assert [check.name for check in report.checks] == [
        "config",
        "databricks_client",
        "llm_endpoint_name",
        "provider_factory",
        "tool_registry_nonempty",
        "persistence_targets",
        "persistence_reachability",
    ]
    assert report.settings_summary == {
        "enabled_tool_sources": ["local_python"],
        "llm_endpoint_name": "endpoint-a",
        "dotenv_path": None,
    }
    out = capsys.readouterr().out
    assert out.startswith("Preflight: pass\n")
    assert "Scope: local configuration sanity check" in out
    assert "does not call the LLM endpoint" in out
    assert "verify serving permissions" in out


def test_preflight_summary_prints_scope(capsys) -> None:
    report = PreflightReport(overall_status="pass", checks=[], settings_summary={})

    print_preflight_summary(report)

    out = capsys.readouterr().out
    assert "Preflight: pass" in out
    assert "Scope: local configuration sanity check" in out
    assert "does not call the LLM endpoint" in out
    assert "verify serving permissions" in out


def test_preflight_reports_local_event_store_targets(tmp_path: Path, monkeypatch) -> None:
    config_path = write_workspace_config(tmp_path, agent_events_table=None)

    monkeypatch.setattr(
        "databricks_tool_agent_template.preflight.get_workspace_client",
        lambda settings: SimpleNamespace(config=SimpleNamespace(host="https://example.com")),
    )

    report = run_preflight(str(config_path))
    persistence_check = next(
        check for check in report.checks if check.name == "persistence_targets"
    )

    assert persistence_check.details == {
        "agent_events_table": None,
        "local_data_dir": "./.local_state",
        "storage_mode": "local_jsonl",
    }


def test_preflight_surfaces_shared_config_validation_failures(tmp_path: Path) -> None:
    config_path = write_workspace_config(tmp_path, llm_endpoint_name="''")

    report = run_preflight(str(config_path))

    assert report.overall_status == "fail"
    assert report.checks[0].name == "config"
    assert "llm_endpoint_name" in report.checks[0].message


def test_preflight_fails_for_stale_keys(tmp_path: Path, monkeypatch) -> None:
    config_path = write_workspace_config(tmp_path, extra_lines=["unknown_section: true"])

    monkeypatch.setattr(
        "databricks_tool_agent_template.preflight.get_workspace_client",
        lambda settings: SimpleNamespace(config=SimpleNamespace(host="https://example.com")),
    )

    report = run_preflight(str(config_path))

    assert report.overall_status == "fail"
    assert report.checks[0].name == "config"
    assert "Unknown config key: unknown_section" in report.checks[0].message


def test_preflight_uses_local_mode_when_agent_events_table_is_missing(
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
                "tools:",
                "  local_python:",
                "    enabled: true",
                "  databricks_mcp:",
                "    enabled: false",
                "storage:",
                "  local_data_dir: ./.local_state",
            ]
        ),
        encoding="utf-8",
    )

    monkeypatch.setattr(
        "databricks_tool_agent_template.preflight.get_workspace_client",
        lambda settings: SimpleNamespace(config=SimpleNamespace(host="https://example.com")),
    )

    report = run_preflight(str(config_path))
    persistence_check = next(
        check for check in report.checks if check.name == "persistence_targets"
    )

    assert report.overall_status == "pass"
    assert persistence_check.status == "pass"
    assert persistence_check.details == {
        "agent_events_table": None,
        "local_data_dir": "./.local_state",
        "storage_mode": "local_jsonl",
    }


def test_preflight_reports_uninitialized_remote_storage_with_next_step(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config_path = write_workspace_config(tmp_path)

    monkeypatch.setattr(
        "databricks_tool_agent_template.preflight.get_workspace_client",
        lambda settings: SimpleNamespace(config=SimpleNamespace(host="https://example.com")),
    )
    monkeypatch.setattr(
        "databricks_tool_agent_template.preflight.require_spark_session",
        lambda: SimpleNamespace(),
    )
    monkeypatch.setattr(
        "databricks_tool_agent_template.preflight.storage_table_exists",
        lambda spark, table_name: False,
    )

    report = run_preflight(str(config_path))
    reachability_check = next(
        check for check in report.checks if check.name == "persistence_reachability"
    )

    assert reachability_check.status == "fail"
    assert reachability_check.details["agent_events_table"] == "main.agent.agent_events"
    assert reachability_check.details["next_step"] == "init_storage_job"


def test_preflight_fails_when_table_configured_but_no_active_spark(
    tmp_path: Path,
    monkeypatch,
) -> None:
    config_path = write_workspace_config(
        tmp_path,
        agent_events_table="main.agent.agent_events",
    )

    monkeypatch.setattr(
        "databricks_tool_agent_template.preflight.get_workspace_client",
        lambda settings: SimpleNamespace(config=SimpleNamespace(host="https://example.com")),
    )
    monkeypatch.setattr(
        "databricks_tool_agent_template.preflight.require_spark_session",
        lambda: (_ for _ in ()).throw(RuntimeError("no active Spark session")),
    )

    report = run_preflight(str(config_path))
    reachability = next(
        check for check in report.checks if check.name == "persistence_reachability"
    )

    assert report.overall_status == "fail"
    assert reachability.status == "fail"
    assert reachability.details == {
        "agent_events_table": "main.agent.agent_events",
        "storage_mode": "spark_table",
    }
    assert "no active Spark session" in reachability.message
