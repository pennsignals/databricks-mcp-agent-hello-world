# databricks-mcp-agent-hello-world

A lightweight starter template for building non-interactive, tool-using LLM agents that run as Databricks Jobs.

The template is intentionally:

- job-first
- local-first
- simple by default

For the current MVP, `local_python` is the only working tool runtime. `managed_mcp` remains a future extension point and is not part of the first-run path.

See the deeper docs when you are ready to customize the template:

- [Architecture](docs/ARCHITECTURE.md)
- [Convert the template into a real app](docs/CONVERT_TEMPLATE_TO_REAL_APP.md)

## How it works

The runtime flow is intentionally small:

1. load config from `workspace-config.yml`
2. discover tools from the active provider
3. run the task with the full discovered tool inventory
4. persist run traces and final outputs locally or to Delta

Tool selection is **LLM-driven**. The runtime provides the full discovered tool set, and the model chooses which tools to call for each input using normal tool-calling behavior.

This template does not implement precompiled profiles, `allowed_tools`, or blocked tool calls as a narrowing layer. Those are advanced patterns for larger inventories and governance-heavy deployments, not part of this starter.

For the built-in demo, the current inventory contains five tools:

- `get_user_profile`
- `search_onboarding_docs`
- `get_workspace_setting`
- `list_recent_job_runs`
- `create_support_ticket`

## Prerequisites

Before you start, make sure you have:

- Python 3.11+
- [`uv`](https://docs.astral.sh/uv/)
- the Databricks CLI installed
- a Databricks workspace you can authenticate to locally
- a Databricks model serving endpoint to use as `llm_endpoint_name`
- permission to deploy bundles and run jobs in your target workspace

The serving endpoint should support the function-calling pattern this template uses.

## Required edits before your first run

### 1. Set your workspace host in `databricks.yml`

Replace the placeholder host in every target you plan to validate or deploy.

### 2. Set your local CLI profile in `.env`

```dotenv
DATABRICKS_CONFIG_PROFILE=DEFAULT
```

### 3. Set the main runtime config in `workspace-config.yml`

At minimum, update these fields:

```yaml
tool_provider_type: local_python
llm_endpoint_name: <your-serving-endpoint-name>
storage:
  agent_runs_table: <catalog.schema.agent_runs>
  agent_output_table: <catalog.schema.agent_outputs>
  local_data_dir: ./.local_state
```

For local runs, Spark is usually unavailable, so the project falls back to local files under `./.local_state`.

### 4. Ignore the SQL section for the demo

The `sql:` block in `workspace-config.example.yml` is for future SQL-backed tools. It is not required for the current `local_python` demo flow.

## Quickstart

From the repo root:

```bash
uv sync
cp workspace-config.example.yml workspace-config.yml
cp .env.example .env
databricks auth login --host https://<your-workspace-host>
uv run preflight --config-path workspace-config.yml
uv run discover-tools --config-path workspace-config.yml
uv run run-agent-task --config-path workspace-config.yml --task-input-file examples/demo_run_task.json
uv run pytest
uv run run-evals --config-path workspace-config.yml
```

The deployed Databricks Job reads `${workspace.file_path}/workspace-config.yml`.

## What you should customize vs keep

Customize these:

- `src/databricks_mcp_agent_hello_world/demo/tools.py`
- `src/databricks_mcp_agent_hello_world/tools/registry.py`
- `examples/demo_run_task.json`
- `evals/sample_scenarios.json`
- `workspace-config.example.yml`
- `databricks.yml`
- `resources/databricks_mcp_agent_hello_world_job.yml`

Usually keep these framework pieces intact unless you are making a platform-level change:

- `src/databricks_mcp_agent_hello_world/runner/agent_runner.py`
- `src/databricks_mcp_agent_hello_world/storage/result_writer.py`
- `src/databricks_mcp_agent_hello_world/storage/result_repository.py`
- `src/databricks_mcp_agent_hello_world/evals/harness.py`
- `src/databricks_mcp_agent_hello_world/models.py`
- `src/databricks_mcp_agent_hello_world/config.py`
- `src/databricks_mcp_agent_hello_world/prompts/agent_system_prompt.txt`

## Deploying to Databricks

This template deploys as a Databricks bundle plus Python wheel job.

The deployed surface is one job:

- `run_agent_task_job`

Validate and deploy with the normal bundle flow:

```bash
databricks bundle validate
databricks bundle deploy --target dev
databricks bundle run --target dev run_agent_task_job
```

## Advanced Concepts

This starter intentionally does not implement:

- precompiled tool profiles
- `allowed_tools`
- blocked tool-call policy layers

Those patterns can be useful later for larger tool inventories, governance controls, or token optimization, but they are out of scope for this template. MCP is also still future work rather than part of the current runtime path.
