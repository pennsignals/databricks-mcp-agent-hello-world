from pathlib import Path
from types import SimpleNamespace

from databricks_mcp_agent_hello_world.config import load_settings
from databricks_mcp_agent_hello_world.ops import (
    discover_tools,
    print_discovery_report,
    run_example_task,
    run_preflight,
)


def _write_config(tmp_path: Path, *, include_profile: bool = True) -> Path:
    lines = [
        "llm_endpoint_name: endpoint-a",
        "tool_provider_type: local_python",
        "active_profile_name: default",
        "storage:",
        "  tool_profile_table: main.agent.tool_profiles",
        "  agent_runs_table: main.agent.agent_runs",
        "  agent_output_table: main.agent.agent_outputs",
    ]
    if include_profile:
        lines.insert(3, "databricks_config_profile: DEFAULT")
    config_path = tmp_path / "workspace-config.yml"
    config_path.write_text("\n".join(lines), encoding="utf-8")
    return config_path


def test_preflight_returns_pass_with_stubbed_client(tmp_path: Path, monkeypatch) -> None:
    config_path = _write_config(tmp_path)

    class StubRepo:
        def __init__(self, settings):
            self.settings = settings

        def load_active(self, profile_name):
            return None

    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.ops.get_workspace_client",
        lambda settings: SimpleNamespace(config=SimpleNamespace(host="https://example.com")),
    )
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.ops.get_spark_session",
        lambda: None,
    )
    monkeypatch.setattr("databricks_mcp_agent_hello_world.ops.ToolProfileRepository", StubRepo)

    report = run_preflight(str(config_path))

    assert report.overall_status == "pass"
    assert report.has_active_profile is False
    assert report.can_compile_profile is True
    assert [check.name for check in report.checks] == [
        "config_file",
        "dotenv",
        "databricks_profile",
        "databricks_client",
        "llm_endpoint_name",
        "provider_factory",
        "tool_registry_nonempty",
        "sql_config",
        "persistence_targets",
        "persistence_reachability",
        "active_profile",
        "compile_capability",
    ]


def test_preflight_does_not_fail_solely_for_missing_active_profile(
    tmp_path: Path, monkeypatch
) -> None:
    config_path = _write_config(tmp_path)

    class StubRepo:
        def __init__(self, settings):
            self.settings = settings

        def load_active(self, profile_name):
            return None

    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.ops.get_workspace_client",
        lambda settings: SimpleNamespace(config=SimpleNamespace(host="https://example.com")),
    )
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.ops.get_spark_session",
        lambda: None,
    )
    monkeypatch.setattr("databricks_mcp_agent_hello_world.ops.ToolProfileRepository", StubRepo)

    report = run_preflight(str(config_path))

    assert report.overall_status == "pass"
    assert any(
        check.name == "active_profile"
        and check.details.get("has_active_profile") is False
        for check in report.checks
    )


def test_preflight_skips_sql_config_validation_for_local_python(
    tmp_path: Path, monkeypatch
) -> None:
    config_path = _write_config(tmp_path)

    class StubRepo:
        def __init__(self, settings):
            self.settings = settings

        def load_active(self, profile_name):
            return None

    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.ops.get_workspace_client",
        lambda settings: SimpleNamespace(config=SimpleNamespace(host="https://example.com")),
    )
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.ops.get_spark_session",
        lambda: None,
    )
    monkeypatch.setattr("databricks_mcp_agent_hello_world.ops.ToolProfileRepository", StubRepo)

    report = run_preflight(str(config_path))

    sql_check = next(check for check in report.checks if check.name == "sql_config")
    assert sql_check.status == "pass"
    assert "Skipped" in sql_check.message


def test_preflight_fails_when_profile_is_invalid(tmp_path: Path, monkeypatch) -> None:
    config_path = _write_config(tmp_path)

    def _raise_invalid_profile(settings):
        raise ValueError("profile DEFAULT is not configured")

    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.ops.get_workspace_client",
        _raise_invalid_profile,
    )

    report = run_preflight(str(config_path))

    assert report.overall_status == "fail"
    assert any(
        check.name == "databricks_client" and check.status == "fail" for check in report.checks
    )


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


def test_discover_tools_json_includes_metadata_fields(tmp_path: Path) -> None:
    settings = load_settings(str(_write_config(tmp_path)))

    report = discover_tools(settings)
    payload = report.model_dump(mode="json")

    first_tool = payload["tools"][0]
    assert "capability_tags" in first_tool
    assert "side_effect_level" in first_tool
    assert "data_domains" in first_tool
    assert "example_uses" in first_tool


def test_print_discovery_report_shows_metadata(tmp_path: Path, capsys) -> None:
    settings = load_settings(str(_write_config(tmp_path)))
    report = discover_tools(settings)

    print_discovery_report(report)
    output = capsys.readouterr().out

    assert "Side effect level: read_only" in output
    assert "Tags: identity, profile" in output
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

    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.ops.discover_tools",
        lambda passed_settings: calls.append(("discover", passed_settings)) or SimpleNamespace(),
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
        ("discover", settings),
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
        '{"task_name":"workspace_onboarding_brief","instructions":"Write the report.","payload":{"user_id":"usr_ada_01"}}',
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

    monkeypatch.setattr("databricks_mcp_agent_hello_world.ops.discover_tools", _discover)

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
    assert observed_sql_fields == {
        "warehouse_id": None,
        "catalog": None,
        "schema": None,
    }
