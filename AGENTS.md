# databricks-mcp-agent-hello-world Operator Guide

This is the internal maintainer guide for the template. It should track the same canonical flow as `README.md` and stay aligned with `REQUIREMENTS.md`.

## What this template is

- a non-interactive LLM agent template
- Databricks-only
- local Python tools are the MVP runtime path today
- `managed_mcp` is a future extension point only
- a scheduled Job template, not a Databricks App

## Local development flow

Maintain the same sequence as the README and do not introduce alternate onboarding paths:

1. Run `uv sync`.
2. Authenticate locally with the Databricks CLI using `databricks auth login`.
3. Copy `.env.example` to `.env` and `workspace-config.example.yml` to `workspace-config.yml`.
4. Run `uv run preflight --config-path workspace-config.yml`.
5. Run `uv run discover-tools --config-path workspace-config.yml`.
6. Run `uv run run-agent-task --config-path workspace-config.yml --task-input-file examples/demo_run_task.json`.
7. Run `uv run pytest`.
8. Run `uv run run-evals --config-path workspace-config.yml`.

Local commands read the repo-root `workspace-config.yml`. Deployed Jobs read `${workspace.file_path}/workspace-config.yml`.

## Testing levels

### Unit tests

Command:

```bash
uv run pytest
```

Definition:

- local
- fast
- no live LLM call required
- no token usage expected

### Live integration evals

Command:

```bash
uv run run-evals --config-path workspace-config.yml
```

Definition:

- uses the configured Databricks-hosted LLM endpoint
- requires valid auth
- consumes tokens
- may vary slightly between runs

### Hello-world demo run

Command:

```bash
uv run run-agent-task --config-path workspace-config.yml --task-input-file examples/demo_run_task.json
```

Definition:

- demonstrates the actual end-to-end hello-world workflow
- not a test harness
- should be used after preflight and tool discovery succeed

## Hello-world contract

The `workspace_onboarding_brief` flow is the starter contract this template must preserve.

- show the full discovered tool set to the model
- let the model choose which tools to call at runtime
- make at least one tool call
- return a final answer built from tool output

## Adding or modifying tools

- Demo tool implementations live in `src/databricks_mcp_agent_hello_world/demo/tools.py`.
- Tool metadata and JSON schemas are registered in `src/databricks_mcp_agent_hello_world/tools/registry.py`.
- Runtime orchestration lives in `src/databricks_mcp_agent_hello_world/runner/agent_runner.py`.
- Update eval expectations in `tests/test_evals.py` and related runtime tests when tool behavior changes.

Keep the tool contract simple: the runner should expose the discovered tool inventory to the model and only reject tool calls whose names are not present in that inventory.

## Deployment model

- The project deploys as a Databricks bundle plus Python wheel job.
- The deployed job is `run_agent_task_job`.
- The job reads `config_path: ${workspace.file_path}/workspace-config.yml` from the deployed workspace copy.
- Local development may fall back to local persistence when Spark is unavailable.
- On Databricks compute, Delta-backed persistence is the normal deployed path.

For deployment changes, keep the bundle flow and job names in sync with `databricks.yml` and `resources/databricks_mcp_agent_hello_world_job.yml`.
