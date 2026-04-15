import json
from pathlib import Path
from types import SimpleNamespace

from databricks_mcp_agent_hello_world.cli import (
    EvalSetupError,
    _print_compilation_summary,
    build_parser,
    run_named_command,
)


def _write_config(tmp_path: Path, *, default_compile_task_file: str | None = None) -> Path:
    config_path = tmp_path / "workspace-config.yml"
    lines = [
        "llm_endpoint_name: endpoint-a",
        "tool_provider_type: local_python",
        "active_profile_name: default",
        "databricks_config_profile: DEFAULT",
        "storage:",
        "  tool_profile_table: main.agent.tool_profiles",
        "  agent_runs_table: main.agent.agent_runs",
        "  agent_output_table: main.agent.agent_outputs",
    ]
    if default_compile_task_file is not None:
        lines.append(f"default_compile_task_file: {default_compile_task_file}")
    config_path.write_text("\n".join(lines), encoding="utf-8")
    return config_path


def _compile_settings(*, default_compile_task_file: str | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        llm_endpoint_name="endpoint-a",
        tool_provider_type="local_python",
        active_profile_name="default",
        default_compile_task_file=default_compile_task_file,
        storage=SimpleNamespace(
            tool_profile_table="main.agent.tool_profiles",
            agent_runs_table="main.agent.agent_runs",
            agent_output_table="main.agent.agent_outputs",
        ),
        prompts=SimpleNamespace(filter_prompt="filter prompt", audit_prompt="audit prompt"),
    )


class StubCompiler:
    instances: list["StubCompiler"] = []

    def __init__(self, settings):
        self.settings = settings
        self.calls: list[tuple[object, bool]] = []
        StubCompiler.instances.append(self)

    def compile(self, task, force_refresh=False):
        self.calls.append((task, force_refresh))
        profile = SimpleNamespace(
            profile_name="default",
            profile_version="v1",
            compile_task_name=task.task_name,
            compile_task_hash="compile-task-hash",
            compile_task_summary=f"{task.task_name}: {task.instructions}"[:240],
            allowed_tools=["alpha"],
            inventory_hash="inventory-hash",
        )
        return SimpleNamespace(profile=profile, reused_existing=False)

def test_parsers_accept_documented_flags() -> None:
    preflight_args = build_parser("preflight", prog="preflight").parse_args([])
    discover_args = build_parser("discover-tools", prog="discover-tools").parse_args([])
    compile_args = build_parser("compile-tool-profile", prog="compile-tool-profile").parse_args([])
    compile_json_args = build_parser("compile-tool-profile", prog="compile-tool-profile").parse_args(
        ["--task-input-json", "{}"]
    )
    compile_file_args = build_parser("compile-tool-profile", prog="compile-tool-profile").parse_args(
        ["--task-input-file", "task.json"]
    )
    run_task_args = build_parser("run-agent-task", prog="run-agent-task").parse_args(
        ["--task-input-json", "{}"]
    )
    run_evals_default_args = build_parser("run-evals", prog="run-evals").parse_args([])
    run_evals_args = build_parser("run-evals", prog="run-evals").parse_args(
        ["--scenario-file", "evals/custom.json"]
    )

    assert preflight_args.config_path == "workspace-config.yml"
    assert discover_args.output == "text"
    assert compile_args.force_refresh is False
    assert compile_args.task_input_json is None
    assert compile_args.task_input_file is None
    assert compile_json_args.task_input_json == "{}"
    assert compile_file_args.task_input_file == "task.json"
    assert run_task_args.task_input_json == "{}"
    assert run_evals_default_args.scenario_file == "evals/sample_scenarios.json"
    assert run_evals_args.scenario_file == "evals/custom.json"


def test_compile_tool_profile_uses_cli_json_source(
    monkeypatch, capsys
) -> None:
    StubCompiler.instances.clear()
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.cli.load_settings",
        lambda config_path: _compile_settings(default_compile_task_file="unused.json"),
    )
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.cli.ToolProfileCompiler",
        StubCompiler,
    )
    parse_calls: list[tuple[str, str]] = []

    def _parse_task_input(task_input_json):
        parse_calls.append(("json", task_input_json))
        return {
            "task_name": "json-task",
            "instructions": "From the CLI JSON payload.",
            "payload": {"source": "json"},
            "run_id": "run-json",
        }

    monkeypatch.setattr("databricks_mcp_agent_hello_world.cli.parse_task_input", _parse_task_input)
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.cli.parse_task_input_file",
        lambda path: (_ for _ in ()).throw(AssertionError("file parser should not be used")),
    )

    exit_code = run_named_command(
        "compile-tool-profile",
        ["--config-path", "workspace-config.yml", "--task-input-json", '{"task_name":"json-task"}'],
    )
    output = capsys.readouterr().out

    assert exit_code == 0
    assert parse_calls == [("json", '{"task_name":"json-task"}')]
    assert StubCompiler.instances[0].calls[0][0].task_name == "json-task"
    assert StubCompiler.instances[0].calls[0][1] is False
    assert "Compiled tool profile" in output


def test_compile_tool_profile_uses_cli_file_source(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    StubCompiler.instances.clear()
    config_path = _write_config(tmp_path)
    task_file = tmp_path / "compile-task.json"
    task_file.write_text(
        '{"task_name":"file-task","instructions":"From file","payload":{"source":"file"}}',
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.cli.load_settings",
        lambda config_path: _compile_settings(),
    )
    monkeypatch.setattr("databricks_mcp_agent_hello_world.cli.ToolProfileCompiler", StubCompiler)
    parse_calls: list[str] = []

    def _parse_task_input_file(path):
        parse_calls.append(path)
        return {
            "task_name": "file-task",
            "instructions": "From the CLI file payload.",
            "payload": {"source": "file"},
            "run_id": "run-file",
        }

    monkeypatch.setattr("databricks_mcp_agent_hello_world.cli.parse_task_input_file", _parse_task_input_file)
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.cli.parse_task_input",
        lambda payload: (_ for _ in ()).throw(AssertionError("json parser should not be used")),
    )

    exit_code = run_named_command(
        "compile-tool-profile",
        ["--config-path", str(config_path), "--task-input-file", str(task_file)],
    )
    output = capsys.readouterr().out

    assert exit_code == 0
    assert parse_calls == [str(task_file)]
    assert StubCompiler.instances[0].calls[0][0].task_name == "file-task"
    assert StubCompiler.instances[0].calls[0][1] is False
    assert "Compiled tool profile" in output


def test_compile_tool_profile_uses_default_compile_task_file(
    tmp_path: Path, monkeypatch
) -> None:
    StubCompiler.instances.clear()
    task_file = tmp_path / "default-compile-task.json"
    task_file.write_text(
        '{"task_name":"default-task","instructions":"From default","payload":{"source":"default"}}',
        encoding="utf-8",
    )
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.cli.load_settings",
        lambda config_path: _compile_settings(default_compile_task_file=str(task_file)),
    )
    monkeypatch.setattr("databricks_mcp_agent_hello_world.cli.ToolProfileCompiler", StubCompiler)
    parse_calls: list[str] = []

    def _parse_task_input_file(path):
        parse_calls.append(path)
        return {
            "task_name": "default-task",
            "instructions": "From the default compile task file.",
            "payload": {"source": "default"},
        }

    monkeypatch.setattr("databricks_mcp_agent_hello_world.cli.parse_task_input_file", _parse_task_input_file)
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.cli.parse_task_input",
        lambda payload: (_ for _ in ()).throw(AssertionError("json parser should not be used")),
    )

    exit_code = run_named_command("compile-tool-profile", ["--config-path", "workspace-config.yml"])

    assert exit_code == 0
    assert parse_calls == [str(task_file)]
    assert StubCompiler.instances[0].calls[0][0].task_name == "default-task"


def test_compile_tool_profile_fails_when_no_source_exists(
    monkeypatch, capsys
) -> None:
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.cli.load_settings",
        lambda config_path: _compile_settings(),
    )
    monkeypatch.setattr("databricks_mcp_agent_hello_world.cli.ToolProfileCompiler", StubCompiler)

    exit_code = run_named_command("compile-tool-profile", ["--config-path", "workspace-config.yml"])
    output = capsys.readouterr().err

    assert exit_code == 1
    assert "compile-tool-profile requires a compile task" in output
    assert "--task-input-json" in output
    assert "--task-input-file" in output
    assert "default_compile_task_file" in output


def test_compile_tool_profile_fails_when_required_task_fields_are_missing(
    monkeypatch, capsys
) -> None:
    StubCompiler.instances.clear()
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.cli.load_settings",
        lambda config_path: _compile_settings(),
    )
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.cli.set_runtime_settings",
        lambda settings: None,
    )
    monkeypatch.setattr("databricks_mcp_agent_hello_world.cli.ToolProfileCompiler", StubCompiler)

    exit_code = run_named_command(
        "compile-tool-profile",
        ["--task-input-json", '{"task_name":"compile-task","payload":{"source":"json"}}'],
    )
    output = capsys.readouterr().err

    assert exit_code == 1
    assert "compile-tool-profile requires task fields: instructions." in output


def test_print_compilation_summary_includes_compile_task_metadata(capsys) -> None:
    result = SimpleNamespace(
        reused_existing=False,
        profile=SimpleNamespace(
            profile_name="default",
            profile_version="v1",
            compile_task_name="task-a",
            compile_task_hash="compile-task-hash",
            allowed_tools=["alpha", "beta"],
            inventory_hash="inventory-hash",
        ),
    )

    _print_compilation_summary(result)
    output = capsys.readouterr().out

    assert "Compiled tool profile: default" in output
    assert "Profile version: v1" in output
    assert "Compile task name: task-a" in output
    assert "Allowed tools: 2" in output
    assert "Inventory hash: inventory-hash" in output
    assert "Compile task hash: compile-task-hash" in output


def test_run_agent_task_requires_exactly_one_input_flag() -> None:
    exit_code = run_named_command("run-agent-task", ["--config-path", "workspace-config.yml"])

    assert exit_code == 2


def test_run_agent_task_surfaces_missing_active_profile_error(
    monkeypatch, capsys
) -> None:
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.cli.load_settings",
        lambda config_path: SimpleNamespace(),
    )

    class StubRunner:
        def __init__(self, settings):
            self.settings = settings

        def run(self, task):
            raise RuntimeError(
                "No active tool profile exists for profile 'default'. "
                "Run compile_tool_profile_job first."
            )

    monkeypatch.setattr("databricks_mcp_agent_hello_world.cli.AgentRunner", StubRunner)

    exit_code = run_named_command(
        "run-agent-task",
        [
            "--task-input-json",
            '{"task_name":"run-task","instructions":"Do the thing.","payload":{"source":"json"}}',
        ],
    )
    output = capsys.readouterr().err

    assert exit_code == 1
    assert "No active tool profile exists" in output
    assert "compile_tool_profile_job" in output


def test_run_agent_task_fails_when_required_task_fields_are_missing(
    monkeypatch, capsys
) -> None:
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


def test_preflight_json_output_returns_expected_shape(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    config_path = _write_config(tmp_path)
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.cli.run_preflight",
        lambda config_path: SimpleNamespace(
            overall_status="pass",
            checks=[],
            has_active_profile=False,
            can_compile_profile=True,
            settings_summary={"config_path": config_path},
        ),
    )
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.cli.print_json_report",
        lambda payload: print(json.dumps(payload, default=lambda value: value.__dict__)),
    )

    exit_code = run_named_command(
        "preflight",
        ["--config-path", str(config_path), "--output", "json"],
    )
    output = capsys.readouterr().out

    assert exit_code == 0
    assert '"overall_status": "pass"' in output
    assert '"checks"' in output
    assert '"settings_summary"' in output
    assert '"has_active_profile": false' in output
    assert '"can_compile_profile": true' in output


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
                    failed_checks=["missing_required_allowed_tools", "below_min_tool_calls"],
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
    assert "FAIL demo: missing_required_allowed_tools; below_min_tool_calls" in output
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


def test_run_evals_reports_invalid_json_concisely(
    tmp_path: Path, monkeypatch, capsys
) -> None:
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
