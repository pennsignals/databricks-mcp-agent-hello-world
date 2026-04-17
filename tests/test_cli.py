from types import SimpleNamespace

from databricks_mcp_agent_hello_world.cli import (
    _print_run_summary,
    build_parser,
    run_named_command,
)
from databricks_mcp_agent_hello_world.commands import CommandResult
from databricks_mcp_agent_hello_world.evals.harness import EvalSetupError
from databricks_mcp_agent_hello_world.models import AgentRunRecord, DiscoveryReport, PreflightReport


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


def test_main_rejects_removed_init_storage_command(capsys) -> None:
    from databricks_mcp_agent_hello_world.cli import main

    exit_code = main(["init-storage"])
    output = capsys.readouterr().err

    assert exit_code == 2
    assert "init-storage" in output
    assert "Expected one of" in output


def test_run_named_command_dispatches_preflight_and_renders_text(monkeypatch) -> None:
    recorded: dict[str, object] = {}
    payload = PreflightReport(overall_status="pass", checks=[], settings_summary={})

    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.cli.run_preflight_command",
        lambda config_path: recorded.update({"config_path": config_path})
        or CommandResult(exit_code=0, payload=payload),
    )
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.cli.print_preflight_summary",
        lambda report: recorded.update({"rendered": report}),
    )

    exit_code = run_named_command("preflight", ["--config-path", "custom.yml"])

    assert exit_code == 0
    assert recorded == {
        "config_path": "custom.yml",
        "rendered": payload,
    }


def test_run_named_command_dispatches_discover_tools_and_renders_json(
    monkeypatch, capsys
) -> None:
    payload = DiscoveryReport(
        provider_type="local_python",
        tool_count=0,
        provider_id="demo",
        inventory_hash="hash",
        tools=[],
    )

    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.cli.run_discover_tools_command",
        lambda config_path: CommandResult(exit_code=0, payload=payload),
    )

    exit_code = run_named_command(
        "discover-tools",
        ["--config-path", "custom.yml", "--output", "json"],
    )
    output = capsys.readouterr().out

    assert exit_code == 0
    assert '"provider_type": "local_python"' in output
    assert '"tool_count": 0' in output


def test_run_named_command_dispatches_agent_task_and_returns_nonzero_for_max_steps(
    monkeypatch,
) -> None:
    recorded: dict[str, object] = {}
    payload = AgentRunRecord(
        run_id="run-123",
        task_name="task-a",
        status="max_steps_exceeded",
        tools_called=[],
        result={"final_response": ""},
        error_message="Maximum agent steps exceeded.",
    )

    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.cli.run_agent_task_command",
        lambda config_path, *, task_input_json=None, task_input_file=None: recorded.update(
            {
                "config_path": config_path,
                "task_input_json": task_input_json,
                "task_input_file": task_input_file,
            }
        )
        or CommandResult(exit_code=1, payload=payload),
    )
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.cli._print_run_summary",
        lambda report: recorded.update({"rendered": report}),
    )

    exit_code = run_named_command(
        "run-agent-task",
        ["--config-path", "custom.yml", "--task-input-json", '{"task_name":"demo"}'],
    )

    assert exit_code == 1
    assert recorded == {
        "config_path": "custom.yml",
        "task_input_json": '{"task_name":"demo"}',
        "task_input_file": None,
        "rendered": payload,
    }


def test_run_named_command_dispatches_run_evals_and_renders_text(monkeypatch) -> None:
    recorded: dict[str, object] = {}
    payload = SimpleNamespace(
        results=[SimpleNamespace(scenario_id="demo", passed=True, failed_checks=[])],
        passed_scenarios=1,
        total_scenarios=1,
    )

    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.cli.run_evals_command",
        lambda config_path, *, scenario_file="evals/sample_scenarios.json": recorded.update(
            {
                "config_path": config_path,
                "scenario_file": scenario_file,
            }
        )
        or CommandResult(exit_code=0, payload=payload),
    )
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.cli._print_eval_summary",
        lambda report: recorded.update({"rendered": report}),
    )

    exit_code = run_named_command(
        "run-evals",
        ["--config-path", "custom.yml", "--scenario-file", "evals/custom.json"],
    )

    assert exit_code == 0
    assert recorded == {
        "config_path": "custom.yml",
        "scenario_file": "evals/custom.json",
        "rendered": payload,
    }


def test_run_named_command_maps_eval_setup_error_to_stderr(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.cli.run_evals_command",
        lambda config_path, *, scenario_file="evals/sample_scenarios.json": (
            _ for _ in ()
        ).throw(EvalSetupError("auth failed")),
    )

    exit_code = run_named_command("run-evals", ["--config-path", "custom.yml"])
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "auth failed" in captured.err


def test_run_named_command_maps_generic_exception_to_stderr(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.cli.run_discover_tools_command",
        lambda config_path: (_ for _ in ()).throw(RuntimeError("boom")),
    )

    exit_code = run_named_command("discover-tools", ["--config-path", "custom.yml"])
    captured = capsys.readouterr()

    assert exit_code == 1
    assert "boom" in captured.err


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
