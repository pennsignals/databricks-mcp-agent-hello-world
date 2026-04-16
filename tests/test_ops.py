from pathlib import Path
from types import SimpleNamespace

from databricks_mcp_agent_hello_world.config import load_settings
from databricks_mcp_agent_hello_world.ops import (
    discover_tools,
    print_discovery_report,
    print_json_report,
    print_preflight_summary,
    run_example_task,
    run_preflight,
)


def _write_config(tmp_path: Path, *, include_databricks_profile: bool = True) -> Path:
    lines = [
        "llm_endpoint_name: endpoint-a",
        "tool_provider_type: local_python",
        "databricks_config_profile: DEFAULT" if include_databricks_profile else None,
        "storage:",
        "  agent_runs_table: main.agent.agent_runs",
        "  agent_output_table: main.agent.agent_outputs",
    ]
    config_path = tmp_path / "workspace-config.yml"
    config_path.write_text("\n".join(line for line in lines if line is not None), encoding="utf-8")
    return config_path


def test_preflight_returns_pass_without_profile_checks(tmp_path: Path, monkeypatch, capsys) -> None:
    config_path = _write_config(tmp_path)

    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.ops.get_workspace_client",
        lambda settings: SimpleNamespace(config=SimpleNamespace(host="https://example.com")),
    )
    monkeypatch.setattr("databricks_mcp_agent_hello_world.ops.get_spark_session", lambda: None)

    report = run_preflight(str(config_path))
    print_preflight_summary(report)
    output = capsys.readouterr().out

    assert report.overall_status == "pass"
    assert [check.name for check in report.checks] == [
        "config_file",
        "dotenv",
        "databricks_client",
        "llm_endpoint_name",
        "provider_factory",
        "tool_registry_nonempty",
        "sql_config",
        "persistence_targets",
        "persistence_reachability",
    ]
    assert report.settings_summary == {
        "tool_provider_type": "local_python",
        "llm_endpoint_name": "endpoint-a",
        "dotenv_path": None,
    }
    assert output.startswith("Preflight: pass\n")


def test_preflight_persistence_checks_cover_runtime_tables_only(
    tmp_path: Path, monkeypatch
) -> None:
    config_path = _write_config(tmp_path)

    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.ops.get_workspace_client",
        lambda settings: SimpleNamespace(config=SimpleNamespace(host="https://example.com")),
    )
    monkeypatch.setattr("databricks_mcp_agent_hello_world.ops.get_spark_session", lambda: None)

    report = run_preflight(str(config_path))
    persistence_check = next(
        check for check in report.checks if check.name == "persistence_targets"
    )

    assert persistence_check.details == {
        "agent_runs_table": "main.agent.agent_runs",
        "agent_output_table": "main.agent.agent_outputs",
    }
    assert set(persistence_check.details) == {"agent_runs_table", "agent_output_table"}


def test_preflight_json_output_omits_deprecated_profile_fields(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    config_path = _write_config(tmp_path)

    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.ops.get_workspace_client",
        lambda settings: SimpleNamespace(config=SimpleNamespace(host="https://example.com")),
    )
    monkeypatch.setattr("databricks_mcp_agent_hello_world.ops.get_spark_session", lambda: None)

    report = run_preflight(str(config_path))
    print_json_report(report)
    output = capsys.readouterr().out

    assert '"overall_status": "pass"' in output
    assert '"databricks_config_profile"' not in output


def test_preflight_databricks_client_failure_points_to_cli_auth_setup(
    tmp_path: Path, monkeypatch
) -> None:
    config_path = _write_config(tmp_path)

    def _raise(_settings):
        raise RuntimeError("auth not configured")

    monkeypatch.setattr("databricks_mcp_agent_hello_world.ops.get_workspace_client", _raise)
    monkeypatch.setattr("databricks_mcp_agent_hello_world.ops.get_spark_session", lambda: None)

    report = run_preflight(str(config_path))
    databricks_check = next(check for check in report.checks if check.name == "databricks_client")

    assert databricks_check.status == "fail"
    assert databricks_check.message == (
        "Unable to initialize Databricks client. For local development, the "
        "recommended path is Databricks CLI auth with "
        "`DATABRICKS_CONFIG_PROFILE` pointing to a valid profile in "
        "`~/.databrickscfg`."
    )
    assert databricks_check.details == {"error": "auth not configured"}


def test_discover_tools_returns_demo_registry_tools(tmp_path: Path) -> None:
    settings = load_settings(str(_write_config(tmp_path)))

    report = discover_tools(settings)

    assert report.tool_count == 5
    assert [tool.tool_name for tool in report.tools] == [
        "get_user_profile",
        "search_onboarding_docs",
        "get_workspace_setting",
        "list_recent_job_runs",
        "create_support_ticket",
    ]
    assert report.tools[0].capability_tags
    assert report.tools[0].data_domains
    assert report.tools[0].side_effect_level == "read_only"


def test_discover_tools_json_output_matches_runtime_shape(tmp_path: Path, capsys) -> None:
    settings = load_settings(str(_write_config(tmp_path)))

    report = discover_tools(settings)
    print_json_report(report)
    output = capsys.readouterr().out

    assert '"provider_type": "local_python"' in output
    assert '"tool_count": 5' in output


def test_print_discovery_report_shows_metadata(tmp_path: Path, capsys) -> None:
    settings = load_settings(str(_write_config(tmp_path)))
    report = discover_tools(settings)

    print_discovery_report(report)
    output = capsys.readouterr().out

    assert "Side effect level: read_only" in output
    assert "Tags: identity, user_lookup" in output
    assert "Domains: user" in output


def test_run_example_task_orchestrates_discover_and_run(tmp_path: Path, monkeypatch) -> None:
    settings = load_settings(str(_write_config(tmp_path)))
    calls = []
    task_file = tmp_path / "task.json"
    task_file.write_text(
        (
            '{"task_name":"workspace_onboarding_brief","instructions":"Write the report.",'
            '"payload":{"user_id":"usr_ada_01","onboarding_topic":"local development"}}'
        ),
        encoding="utf-8",
    )

    class StubRunner:
        def __init__(self, passed_settings):
            assert passed_settings == settings

        def run(self, task):
            calls.append(("run", task.task_name, task.payload))
            return {"task_name": task.task_name, "payload": task.payload}

    monkeypatch.setattr("databricks_mcp_agent_hello_world.ops.AgentRunner", StubRunner)

    result = run_example_task(settings, str(task_file))

    assert result["task_name"] == "workspace_onboarding_brief"
    assert result["payload"] == {
        "user_id": "usr_ada_01",
        "onboarding_topic": "local development",
    }
    assert calls == [
        (
            "run",
            "workspace_onboarding_brief",
            {
                "user_id": "usr_ada_01",
                "onboarding_topic": "local development",
            },
        ),
    ]


def test_run_example_task_keeps_sql_fields_optional(tmp_path: Path, monkeypatch) -> None:
    settings = load_settings(str(_write_config(tmp_path)))
    observed_sql_fields = {}
    task_file = tmp_path / "task.json"
    task_file.write_text(
        (
            '{"task_name":"workspace_onboarding_brief",'
            '"instructions":"Write the report.",'
            '"payload":{"user_id":"usr_ada_01"}}'
        ),
        encoding="utf-8",
    )

    def _discover(passed_settings):
        observed_sql_fields.update(
            {
                "warehouse_id": passed_settings.sql.warehouse_id,
                "catalog": passed_settings.sql.catalog,
                "schema": passed_settings.sql.schema,
            }
        )
        return SimpleNamespace()

    class StubRunner:
        def __init__(self, passed_settings):
            assert passed_settings.sql.warehouse_id is None
            assert passed_settings.sql.catalog is None
            assert passed_settings.sql.schema is None

        def run(self, task):
            return {"task_name": task.task_name, "payload": task.payload}

    monkeypatch.setattr("databricks_mcp_agent_hello_world.ops.AgentRunner", StubRunner)

    result = run_example_task(settings, str(task_file))

    assert result["task_name"] == "workspace_onboarding_brief"
    assert observed_sql_fields == {}
