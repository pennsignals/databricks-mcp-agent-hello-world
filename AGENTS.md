# databricks-mcp-agent-hello-world Operator Guide

This is the internal maintainer guide for the template. It should track the same canonical flow as `README.md` and stay aligned with `REQUIREMENTS.md`.

## What this template is

- A non-interactive LLM agent template.
- Databricks-only.
- Local Python tools are the MVP runtime path today.
- `managed_mcp` is a future extension point only.
- This is a scheduled Job template, not a Databricks App.

## Local development flow

Maintain the same sequence as the README and do not introduce alternate onboarding paths:

1. Run `uv sync`.
2. Authenticate locally with the Databricks CLI using `databricks auth login`.
3. Copy `.env.example` to `.env` and `workspace-config.example.yml` to `workspace-config.yml`.
4. Run `uv run preflight --config-path workspace-config.yml`.
5. Run `uv run discover-tools --config-path workspace-config.yml`.
6. Run `uv run compile-tool-profile --config-path workspace-config.yml`.
7. Run `uv run run-agent-task --config-path workspace-config.yml --task-input-json '{"task_name":"hello_world_demo"}'`.
8. Run `uv run pytest`.
9. Run `uv run run-evals --config-path workspace-config.yml`.

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

- uses configured Databricks-hosted LLM endpoint
- requires valid auth
- consumes tokens
- may vary slightly between runs

Live integration evals call the configured Databricks-hosted LLM endpoint and may consume tokens.
Use them after local setup and basic hello-world verification succeed.

### Hello-world demo run

Command:

```bash
uv run run-agent-task --config-path workspace-config.yml --task-input-json '{"task_name":"hello_world_demo"}'
```

Definition:

- demonstrates the actual end-to-end hello-world workflow
- not a test harness
- should be used after preflight and profile compilation

## Hello-world contract

The `hello_world_demo` flow is the starter contract this template must preserve.

- Show the full discovered tool set.
- Show the allowed and disallowed subset.
- Use only allowlisted tools at execution time.
- Make at least one tool call.
- Return a final answer built from tool output.

The expected allowlist for the demo is the smallest useful subset of the local Python tools. `tell_demo_joke` stays out of the demo path unless the task explicitly changes.

## Adding or modifying tools

- Dummy demo tools live in `src/databricks_mcp_agent_hello_world/tools/builtin.py`.
- Tool metadata and JSON schemas are registered in `src/databricks_mcp_agent_hello_world/tools/registry.py`.
- The hello-world allowlist and compile-time demo contract live in `src/databricks_mcp_agent_hello_world/profiles/compiler.py`.
- Runtime allowlist enforcement happens in `src/databricks_mcp_agent_hello_world/runner/agent_runner.py`.
- Update eval expectations in `tests/test_evals.py` and related compiler/runtime tests when tool behavior changes.

Keep the tool contract simple: the runner should expose only the filtered subset to the model and block any disallowed call in application code.

## Deployment model

- The project deploys as a Databricks bundle plus Python wheel job.
- The current job split is `compile_tool_profile_job` and `run_agent_task_job`.
- `compile_tool_profile_job` materializes the active tool profile.
- `run_agent_task_job` loads that profile and runs the actual agent task.
- Both jobs read `config_path: ${workspace.file_path}/workspace-config.yml` from the deployed workspace copy.
- Local development may fall back to local persistence when Spark is unavailable.
- On Databricks compute, Delta-backed persistence is expected and should be treated as the normal deployed path.

For deployment changes, keep the bundle flow and job names in sync with `databricks.yml` and `resources/databricks_mcp_agent_hello_world_job.yml`.
