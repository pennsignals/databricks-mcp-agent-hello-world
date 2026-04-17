from pathlib import Path
from types import SimpleNamespace

from databricks_mcp_agent_hello_world.cli import print_json_report, print_preflight_summary
from databricks_mcp_agent_hello_world.preflight import run_preflight


def _write_config(tmp_path: Path, *, include_databricks_profile: bool = True) -> Path:
    lines = [
        "llm_endpoint_name: endpoint-a",
        "tool_provider_type: local_python",
        "databricks_config_profile: DEFAULT" if include_databricks_profile else None,
        "storage:",
        "  agent_events_table: main.agent.agent_events",
        "  local_data_dir: ./.local_state",
    ]
    config_path = tmp_path / "workspace-config.yml"
    config_path.write_text("\n".join(line for line in lines if line is not None), encoding="utf-8")
    return config_path


def test_preflight_returns_pass_without_profile_checks(tmp_path: Path, monkeypatch, capsys) -> None:
    config_path = _write_config(tmp_path)

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
    output = capsys.readouterr().out

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
    assert output.startswith("Preflight: pass\n")


def test_preflight_persistence_checks_cover_event_store_runtime_shape(
    tmp_path: Path, monkeypatch
) -> None:
    config_path = _write_config(tmp_path)

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
    assert set(persistence_check.details) == {
        "agent_events_table",
        "local_data_dir",
        "spark_available",
    }


def test_preflight_local_mode_still_reports_local_jsonl_fallback(
    tmp_path: Path, monkeypatch
) -> None:
    config_path = _write_config(tmp_path)

    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.preflight.get_workspace_client",
        lambda settings: SimpleNamespace(config=SimpleNamespace(host="https://example.com")),
    )
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.preflight.get_spark_session",
        lambda: None,
    )

    report = run_preflight(str(config_path))
    reachability_check = next(
        check for check in report.checks if check.name == "persistence_reachability"
    )

    assert reachability_check.status == "pass"
    assert "local JSONL" in reachability_check.message


def test_preflight_requires_agent_events_table_when_spark_is_available(
    tmp_path: Path, monkeypatch
) -> None:
    config_path = tmp_path / "workspace-config.yml"
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
    assert persistence_check.message == "agent_events_table is required when Spark is available."
    assert persistence_check.details == {
        "missing": ["agent_events_table"],
        "local_data_dir": "./.local_state",
    }


def test_preflight_checks_event_store_reachability_with_spark(
    tmp_path: Path, monkeypatch
) -> None:
    config_path = _write_config(tmp_path)
    spark_calls = []

    class StubSpark:
        def table(self, table_name):
            spark_calls.append(table_name)

            class StubTable:
                def limit(self, value):
                    assert value == 0
                    return self

                def collect(self):
                    return []

            return StubTable()

    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.preflight.get_workspace_client",
        lambda settings: SimpleNamespace(config=SimpleNamespace(host="https://example.com")),
    )
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.preflight.get_spark_session",
        lambda: StubSpark(),
    )
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.preflight.storage_table_exists",
        lambda spark, table_name: True,
    )

    report = run_preflight(str(config_path))
    reachability_check = next(
        check for check in report.checks if check.name == "persistence_reachability"
    )

    assert reachability_check.status == "pass"
    assert reachability_check.details == {"agent_events_table": "main.agent.agent_events"}
    assert spark_calls == ["main.agent.agent_events"]


def test_preflight_reports_uninitialized_delta_storage_with_init_storage_job_next_step(
    tmp_path: Path, monkeypatch
) -> None:
    config_path = _write_config(tmp_path)
    spark = SimpleNamespace()

    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.preflight.get_workspace_client",
        lambda settings: SimpleNamespace(config=SimpleNamespace(host="https://example.com")),
    )
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.preflight.get_spark_session",
        lambda: spark,
    )
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.preflight.storage_table_exists",
        lambda actual_spark, table_name: False,
    )

    report = run_preflight(str(config_path))
    reachability_check = next(
        check for check in report.checks if check.name == "persistence_reachability"
    )

    assert reachability_check.status == "fail"
    assert (
        reachability_check.message
        == "Configured Delta event store is not initialized yet. "
        "Run init_storage_job before the first Spark-backed workload run."
    )
    assert reachability_check.details["agent_events_table"] == "main.agent.agent_events"
    assert reachability_check.details["next_step"] == "init_storage_job"
    assert report.overall_status == "fail"


def test_preflight_reports_generic_read_failure_when_table_exists_but_probe_fails(
    tmp_path: Path, monkeypatch
) -> None:
    config_path = _write_config(tmp_path)

    class StubTable:
        def limit(self, value):
            assert value == 0
            return self

        def collect(self):
            raise RuntimeError("permission denied")

    class StubSpark:
        def table(self, table_name):
            assert table_name == "main.agent.agent_events"
            return StubTable()

    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.preflight.get_workspace_client",
        lambda settings: SimpleNamespace(config=SimpleNamespace(host="https://example.com")),
    )
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.preflight.get_spark_session",
        lambda: StubSpark(),
    )
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.preflight.storage_table_exists",
        lambda spark, table_name: True,
    )

    report = run_preflight(str(config_path))
    reachability_check = next(
        check for check in report.checks if check.name == "persistence_reachability"
    )

    assert reachability_check.status == "fail"
    assert reachability_check.message.startswith(
        "Unable to read the configured Delta event store."
    )
    assert "permission denied" in reachability_check.message
    assert "not initialized yet" not in reachability_check.message
    assert "init_storage_job" not in reachability_check.message


def test_preflight_managed_mcp_fails_with_placeholder_status_and_skips_unrelated_checks(
    tmp_path: Path, monkeypatch
) -> None:
    config_path = tmp_path / "workspace-config.yml"
    config_path.write_text(
        "\n".join(
            [
                "llm_endpoint_name: endpoint-a",
                "tool_provider_type: managed_mcp",
                "storage:",
                "  agent_events_table: main.agent.agent_events",
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
        lambda: None,
    )

    report = run_preflight(str(config_path))
    runtime_status_check = next(
        check for check in report.checks if check.name == "provider_runtime_status"
    )

    assert runtime_status_check.status == "fail"
    assert (
        runtime_status_check.message
        == "Configured provider 'managed_mcp' is a placeholder and is not implemented yet."
    )
    assert not any(check.name == "tool_registry_nonempty" for check in report.checks)
    assert not any(check.name == "persistence_targets" for check in report.checks)
    assert not any(check.name == "persistence_reachability" for check in report.checks)
    assert report.overall_status == "fail"


def test_preflight_json_output_omits_deprecated_profile_fields(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    config_path = _write_config(tmp_path)

    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.preflight.get_workspace_client",
        lambda settings: SimpleNamespace(config=SimpleNamespace(host="https://example.com")),
    )
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.preflight.get_spark_session",
        lambda: None,
    )

    report = run_preflight(str(config_path))
    print_json_report(report)
    output = capsys.readouterr().out

    assert '"overall_status": "pass"' in output
    assert '"databricks_config_profile"' not in output


def test_preflight_includes_single_config_warnings_check(
    tmp_path: Path, monkeypatch
) -> None:
    config_path = tmp_path / "workspace-config.yml"
    config_path.write_text(
        "\n".join(
            [
                "llm_endpoint_name: endpoint-a",
                "tool_provider_type: local_python",
                "auth_mode: local-dev",
                "storage:",
                "  agent_events_table: main.agent.agent_events",
                "  agent_runs_table: main.agent.agent_runs",
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
        lambda: None,
    )

    report = run_preflight(str(config_path))
    warning_checks = [check for check in report.checks if check.name == "config_warnings"]

    assert len(warning_checks) == 1
    assert warning_checks[0].status == "warn"
    assert warning_checks[0].message == "Config contains deprecated or unused keys."
    assert warning_checks[0].details == {
        "warnings": [
            "Unused config key 'auth_mode' is ignored by the current runtime.",
            "Unused config key 'storage.agent_runs_table' is ignored by the current runtime.",
        ]
    }


def test_preflight_warning_strings_match_config_warning_strings(
    tmp_path: Path, monkeypatch
) -> None:
    config_path = tmp_path / "workspace-config.yml"
    config_path.write_text(
        "\n".join(
            [
                "llm_endpoint_name: endpoint-a",
                "provider_type: managed_mcp",
                "storage:",
                "  agent_events_table: main.agent.agent_events",
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
        lambda: None,
    )

    report = run_preflight(str(config_path))
    warning_check = next(check for check in report.checks if check.name == "config_warnings")

    assert warning_check.details["warnings"] == [
        "Deprecated config key 'provider_type' used; use 'tool_provider_type' instead."
    ]


def test_preflight_omits_config_warnings_check_when_none_present(
    tmp_path: Path, monkeypatch
) -> None:
    config_path = _write_config(tmp_path)

    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.preflight.get_workspace_client",
        lambda settings: SimpleNamespace(config=SimpleNamespace(host="https://example.com")),
    )
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.preflight.get_spark_session",
        lambda: None,
    )

    report = run_preflight(str(config_path))

    assert all(check.name != "config_warnings" for check in report.checks)


def test_preflight_databricks_client_failure_points_to_cli_auth_setup(
    tmp_path: Path, monkeypatch
) -> None:
    config_path = _write_config(tmp_path)

    def _raise(_settings):
        raise RuntimeError("auth not configured")

    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.preflight.get_workspace_client",
        _raise,
    )
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.preflight.get_spark_session",
        lambda: None,
    )

    report = run_preflight(str(config_path))
    databricks_check = next(check for check in report.checks if check.name == "databricks_client")

    assert databricks_check.status == "fail"
    assert "Unable to initialize Databricks client" in databricks_check.message
    assert "Databricks CLI auth" in databricks_check.message
    assert databricks_check.details == {"error": "auth not configured"}
