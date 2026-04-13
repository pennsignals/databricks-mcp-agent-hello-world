from pathlib import Path

from databricks_mcp_agent_hello_world.cli import build_parser, run_named_command


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


def test_preflight_json_output_returns_expected_shape(
    tmp_path: Path, monkeypatch, capsys
) -> None:
    config_path = _write_config(tmp_path)
    monkeypatch.setattr(
        "databricks_mcp_agent_hello_world.ops.get_workspace_client",
        lambda settings: type("Client", (), {"config": type("Cfg", (), {"host": "x"})()})(),
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
