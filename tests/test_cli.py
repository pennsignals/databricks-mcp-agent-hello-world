from pathlib import Path
from types import SimpleNamespace

from databricks_mcp_agent_hello_world.cli import build_parser, run_named_command
from databricks_mcp_agent_hello_world.evals.harness import EvalSetupError


def _write_config(tmp_path: Path) -> Path:
    config_path = tmp_path / "workspace-config.yml"
    config_path.write_text(
        "\n".join(
            [
                "llm_endpoint_name: endpoint-a",
                "tool_provider_type: local_python",
                "active_profile_name: default",
                "databricks_config_profile: DEFAULT",
                "storage:",
                "  tool_profile_table: main.agent.tool_profiles",
                "  agent_runs_table: main.agent.agent_runs",
                "  agent_output_table: main.agent.agent_outputs",
            ]
        ),
        encoding="utf-8",
    )
    return config_path


def _summary(*, passed: int, failed: int, errored: int):
    return SimpleNamespace(
        total_scenarios=passed + failed + errored,
        passed=passed,
        failed=failed,
        errored=errored,
        results=[],
    )


def test_parsers_accept_documented_flags() -> None:
    preflight_args = build_parser("preflight", prog="preflight").parse_args([])
    discover_args = build_parser("discover-tools", prog="discover-tools").parse_args([])
    compile_args = build_parser("compile-tool-profile", prog="compile-tool-profile").parse_args(
        ["--force-refresh"]
    )
    run_task_args = build_parser("run-agent-task", prog="run-agent-task").parse_args(
        ["--task-input-json", "{}"]
    )
    run_evals_args = build_parser("run-evals", prog="run-evals").parse_args(["--scenario", "demo"])

    assert preflight_args.config_path == "workspace-config.yml"
    assert discover_args.output == "text"
    assert compile_args.force_refresh is True
    assert run_task_args.task_input_json == "{}"
    assert run_evals_args.scenario == "demo"


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

    exit_code = run_named_command("run-agent-task", ["--task-input-json", "{}"])
    output = capsys.readouterr().err

    assert exit_code == 1
    assert "No active tool profile exists" in output
    assert "compile_tool_profile_job" in output


def test_preflight_json_output_returns_expected_shape(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    config_path = _write_config(tmp_path)
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.ops.get_workspace_client",
        lambda settings: type("Client", (), {"config": type("Cfg", (), {"host": "x"})()})(),
    )
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.ops.get_spark_session",
        lambda: None,
    )
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.ops.ToolProfileRepository",
        lambda settings: type("Repo", (), {"load_active": lambda self, profile_name: None})(),
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
    ran_scenarios = False

    def _unexpected_run_eval_scenarios(*args, **kwargs):
        nonlocal ran_scenarios
        ran_scenarios = True
        raise AssertionError("run_eval_scenarios should not run on setup failure")

    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.cli.prepare_run_evals",
        lambda settings: (_ for _ in ()).throw(EvalSetupError("auth failed")),
    )
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.cli.run_eval_scenarios",
        _unexpected_run_eval_scenarios,
    )

    exit_code = run_named_command(
        "run-evals",
        ["--config-path", str(config_path)],
    )
    captured = capsys.readouterr()

    assert exit_code == 2
    assert ran_scenarios is False
    assert "Running live integration evals against the configured Databricks LLM endpoint." in captured.out
    assert "This command requires valid Databricks auth and may consume tokens." in captured.out
    assert "auth failed" in captured.err


def test_run_evals_returns_failure_exit_code_when_a_scenario_fails(
    tmp_path: Path, monkeypatch
) -> None:
    config_path = _write_config(tmp_path)
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.cli.prepare_run_evals",
        lambda settings: (object(), SimpleNamespace()),
    )
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.cli.load_eval_scenarios",
        lambda path: [SimpleNamespace(scenario_id="demo")],
    )
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.cli.run_eval_scenarios",
        lambda scenarios, runner, scenario_id=None, active_profile=None: _summary(
            passed=0,
            failed=1,
            errored=0,
        ),
    )

    exit_code = run_named_command(
        "run-evals",
        ["--config-path", str(config_path)],
    )

    assert exit_code == 1


def test_run_evals_returns_success_exit_code_when_all_scenarios_pass(
    tmp_path: Path, monkeypatch
) -> None:
    config_path = _write_config(tmp_path)
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.cli.prepare_run_evals",
        lambda settings: (object(), SimpleNamespace()),
    )
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.cli.load_eval_scenarios",
        lambda path: [SimpleNamespace(scenario_id="demo")],
    )
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.cli.run_eval_scenarios",
        lambda scenarios, runner, scenario_id=None, active_profile=None: _summary(
            passed=1,
            failed=0,
            errored=0,
        ),
    )

    exit_code = run_named_command(
        "run-evals",
        ["--config-path", str(config_path)],
    )

    assert exit_code == 0
