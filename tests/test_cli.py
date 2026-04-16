from pathlib import Path
from types import SimpleNamespace

from databricks_mcp_agent_hello_world.cli import (
    EvalSetupError,
    _print_run_summary,
    build_parser,
    run_named_command,
)
from databricks_mcp_agent_hello_world.models import PreflightReport


def _write_config(tmp_path: Path) -> Path:
    config_path = tmp_path / "workspace-config.yml"
    lines = [
        "llm_endpoint_name: endpoint-a",
        "tool_provider_type: local_python",
        "databricks_config_profile: DEFAULT",
        "storage:",
        "  agent_runs_table: main.agent.agent_runs",
        "  agent_output_table: main.agent.agent_outputs",
    ]
    config_path.write_text("\n".join(lines), encoding="utf-8")
    return config_path


def test_parsers_accept_documented_flags() -> None:
    preflight_args = build_parser("preflight", prog="preflight").parse_args([])
    discover_args = build_parser("discover-tools", prog="discover-tools").parse_args([])
    run_task_args = build_parser("run-agent-task", prog="run-agent-task").parse_args(
        ["--task-input-json", "{}"]
    )
    run_evals_default_args = build_parser("run-evals", prog="run-evals").parse_args([])
    run_evals_args = build_parser("run-evals", prog="run-evals").parse_args(
        ["--scenario-file", "evals/custom.json"]
    )

    assert preflight_args.config_path == "workspace-config.yml"
    assert discover_args.output == "text"
    assert run_task_args.task_input_json == "{}"
    assert run_evals_default_args.scenario_file == "evals/sample_scenarios.json"
    assert run_evals_args.scenario_file == "evals/custom.json"


def test_main_rejects_unknown_command(capsys) -> None:
    from databricks_mcp_agent_hello_world.cli import main

    exit_code = main(["not-a-real-command"])
    output = capsys.readouterr().err

    assert exit_code == 2
    assert "not-a-real-command" in output
    assert "Expected one of" in output


def test_run_agent_task_uses_cli_json_source(monkeypatch, capsys) -> None:
    load_calls = []
    parse_calls = []

    def _load_settings(config_path):
        load_calls.append(config_path)
        return SimpleNamespace()

    def _parse_task_input(task_input_json):
        parse_calls.append(task_input_json)
        return {
            "task_name": "json-task",
            "instructions": "From the CLI JSON payload.",
            "payload": {"source": "json"},
            "run_id": "run-json",
        }

    class StubRunner:
        def __init__(self, settings):
            self.settings = settings

        def run(self, task):
            assert task.task_name == "json-task"
            assert task.instructions == "From the CLI JSON payload."
            assert task.payload == {"source": "json"}
            return SimpleNamespace(
                status="success",
                run_id="run-json",
                task_name=task.task_name,
                tools_called=[{"tool_name": "alpha"}],
                result={"final_response": "Completed"},
            )

    monkeypatch.setattr("databricks_mcp_agent_hello_world.cli.load_settings", _load_settings)
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.cli.parse_task_input", _parse_task_input
    )
    monkeypatch.setattr("databricks_mcp_agent_hello_world.cli.AgentRunner", StubRunner)
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.cli.set_runtime_settings", lambda settings: None
    )

    exit_code = run_named_command(
        "run-agent-task",
        [
            "--config-path",
            "workspace-config.yml",
            "--task-input-json",
            '{"task_name":"json-task"}',
        ],
    )
    output = capsys.readouterr().out

    assert exit_code == 0
    assert load_calls == ["workspace-config.yml"]
    assert parse_calls == ['{"task_name":"json-task"}']
    assert "Run status: success" in output
    assert "Final answer:" in output
    assert "Completed" in output
    assert "Run id: run-json" in output


def test_run_agent_task_uses_cli_file_source(tmp_path: Path, monkeypatch) -> None:
    config_path = _write_config(tmp_path)
    task_file = tmp_path / "task.json"
    task_file.write_text(
        '{"task_name":"file-task","instructions":"From file","payload":{"source":"file"}}',
        encoding="utf-8",
    )
    parse_calls: list[str] = []

    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.cli.load_settings",
        lambda config_path: SimpleNamespace(),
    )
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.cli.parse_task_input_file",
        lambda path: (
            parse_calls.append(path)
            or {
                "task_name": "file-task",
                "instructions": "From the CLI file payload.",
                "payload": {"source": "file"},
            }
        ),
    )

    class StubRunner:
        def __init__(self, settings):
            self.settings = settings

        def run(self, task):
            assert task.task_name == "file-task"
            return SimpleNamespace(
                status="success",
                run_id="run-file",
                task_name=task.task_name,
                tools_called=[],
                result={"final_response": "done"},
            )

    monkeypatch.setattr("databricks_mcp_agent_hello_world.cli.AgentRunner", StubRunner)
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.cli.set_runtime_settings", lambda settings: None
    )

    exit_code = run_named_command(
        "run-agent-task",
        ["--config-path", str(config_path), "--task-input-file", str(task_file)],
    )

    assert exit_code == 0
    assert parse_calls == [str(task_file)]


def test_run_agent_task_fails_when_required_task_fields_are_missing(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.cli.load_settings",
        lambda config_path: SimpleNamespace(),
    )
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.cli.set_runtime_settings",
        lambda settings: None,
    )

    exit_code = run_named_command(
        "run-agent-task",
        ["--task-input-json", '{"task_name":"run-task","payload":{"source":"json"}}'],
    )
    output = capsys.readouterr().err

    assert exit_code == 1
    assert "run-agent-task requires task fields: instructions." in output


def test_print_run_summary_includes_final_response_without_profile_vocabulary(capsys) -> None:
    record = SimpleNamespace(
        status="success",
        run_id="run-123",
        task_name="task-a",
        tools_called=[{"tool_name": "alpha"}],
        result={"final_response": "All set"},
    )

    _print_run_summary(record)
    output = capsys.readouterr().out

    assert "Run status: success" in output
    assert "Final answer:" in output
    assert "All set" in output
    assert "Tools called: 1" in output


def test_preflight_json_output_returns_expected_shape(tmp_path: Path, monkeypatch, capsys) -> None:
    config_path = _write_config(tmp_path)
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.cli.run_preflight",
        lambda config_path: PreflightReport(
            overall_status="pass",
            checks=[],
            settings_summary={"config_path": config_path},
        ),
    )

    exit_code = run_named_command(
        "preflight",
        ["--config-path", str(config_path), "--output", "json"],
    )
    output = capsys.readouterr().out

    assert exit_code == 0
    assert '"overall_status": "pass"' in output
    assert '"checks": []' in output
    assert '"settings_summary"' in output
    assert '"config_path"' in output


def test_run_evals_returns_setup_failure_exit_code_without_running_scenarios(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    config_path = _write_config(tmp_path)
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.cli.run_evals",
        lambda settings, scenario_file: (_ for _ in ()).throw(EvalSetupError("auth failed")),
    )

    exit_code = run_named_command(
        "run-evals",
        ["--config-path", str(config_path)],
    )
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "auth failed" in captured.err


def test_run_evals_returns_failure_exit_code_when_a_scenario_fails(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    config_path = _write_config(tmp_path)
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.cli.run_evals",
        lambda settings, scenario_file: SimpleNamespace(
            total_scenarios=1,
            passed_scenarios=0,
            failed_scenarios=1,
            all_passed=False,
            results=[
                SimpleNamespace(
                    scenario_id="demo",
                    passed=False,
                    failed_checks=["missing_required_available_tools", "below_min_tool_calls"],
                )
            ],
        ),
    )

    exit_code = run_named_command(
        "run-evals",
        ["--config-path", str(config_path)],
    )
    output = capsys.readouterr().out

    assert exit_code == 1
    assert "FAIL demo: missing_required_available_tools; below_min_tool_calls" in output
    assert "Passed 0/1 scenarios" in output


def test_run_evals_returns_success_exit_code_when_all_scenarios_pass(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    config_path = _write_config(tmp_path)
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.cli.run_evals",
        lambda settings, scenario_file: SimpleNamespace(
            total_scenarios=1,
            passed_scenarios=1,
            failed_scenarios=0,
            all_passed=True,
            results=[SimpleNamespace(scenario_id="demo", passed=True, failed_checks=[])],
        ),
    )

    exit_code = run_named_command(
        "run-evals",
        ["--config-path", str(config_path)],
    )
    output = capsys.readouterr().out

    assert exit_code == 0
    assert "PASS demo" in output
    assert "Passed 1/1 scenarios" in output


def test_run_evals_reports_missing_scenario_file_concisely(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    config_path = _write_config(tmp_path)
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.cli.run_evals",
        lambda settings, scenario_file: (_ for _ in ()).throw(
            EvalSetupError(f"Scenario file not found: {scenario_file}")
        ),
    )

    exit_code = run_named_command(
        "run-evals",
        ["--config-path", str(config_path), "--scenario-file", "evals/missing.json"],
    )
    output = capsys.readouterr().err

    assert exit_code == 1
    assert "Scenario file not found: evals/missing.json" in output


def test_run_evals_reports_invalid_json_concisely(tmp_path: Path, monkeypatch, capsys) -> None:
    config_path = _write_config(tmp_path)
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.cli.run_evals",
        lambda settings, scenario_file: (_ for _ in ()).throw(
            EvalSetupError(f"Invalid scenario JSON: {scenario_file}")
        ),
    )

    exit_code = run_named_command(
        "run-evals",
        ["--config-path", str(config_path), "--scenario-file", "evals/invalid.json"],
    )
    output = capsys.readouterr().err

    assert exit_code == 1
    assert "Invalid scenario JSON: evals/invalid.json" in output
