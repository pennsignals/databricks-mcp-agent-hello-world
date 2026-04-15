# databricks-mcp-agent-hello-world

A lightweight starter template for building **non-interactive, tool-using LLM agents that run as Databricks Jobs**.

This template is intentionally:

- **Job-first**: package the project as a Python wheel and run it as a Databricks Job
- **local-first**: develop and validate from your laptop before deploying
- **simple by default**: keep the runtime small and easy to extend

This repo is for **autonomous batch-style agent workflows**, not chat apps, Databricks Apps, or long-running interactive services.

For the current MVP, **`local_python` is the only working tool runtime**. `managed_mcp` is reserved for a future extension path and is not part of the first-run flow.

On a successful first pass, you should be able to authenticate locally to Databricks, configure a Databricks-hosted LLM endpoint, compile a task-aware tool profile, run the demo locally, verify that only the allowed tools are exposed at runtime, and deploy the same workflow as Python wheel Jobs.

See the deeper docs when you are ready to customize the template:

- [Architecture](docs/ARCHITECTURE.md)
- [Convert the template into a real app](docs/CONVERT_TEMPLATE_TO_REAL_APP.md)

## How it works

The runtime flow is intentionally small:

1. load config from `workspace-config.yml`
2. discover tools from the active provider
3. compile a task-aware allowlist profile for a representative compile task
4. persist that `ToolProfile`
5. run the real task with only the allowed tools exposed
6. persist run traces and final outputs locally or to Delta

Tool selection is **LLM-driven**. The template does **not** use task-name-specific hard-coded allowlists.

For the built-in demo, the current inventory contains **five** tools:

- `get_user_profile`
- `search_onboarding_docs`
- `get_workspace_setting`
- `list_recent_job_runs`
- `create_support_ticket`

The demo compile task is a **read-only onboarding brief**, so the compiled profile should allow the **four read-only tools** and exclude the write tool `create_support_ticket`.

## Prerequisites

Before you start, make sure you have:

- **Python 3.11+**
- **[`uv`](https://docs.astral.sh/uv/)**
- the **Databricks CLI** installed
- a Databricks workspace you can authenticate to locally
- a **Databricks model serving endpoint** to use as `llm_endpoint_name`
- permission to deploy bundles and run jobs in your target workspace

The serving endpoint should support the **function-calling / tool-calling pattern** this template uses.

The default deployed job definition in this repo uses **serverless job environments**. If your workspace does not support that pattern, you can still use this template, but you will need to edit the job resource before deployment.

## Authentication model

This project uses two auth modes:

- **Local development**: use **Databricks CLI profile auth**, sign in with `databricks auth login`, and store the profile name in `.env` as `DATABRICKS_CONFIG_PROFILE`.
- **Scheduled or CI/CD execution**: use your organization’s approved non-interactive auth path, typically a service principal with OAuth M2M.

For the supported beginner path, use CLI profile auth locally rather than direct Databricks credentials in `.env`.

## First-time setup

From the repo root:

```bash
uv sync
cp workspace-config.example.yml workspace-config.yml
cp .env.example .env
```

## Required edits before your first run

### 1) Set your workspace host in `databricks.yml`

Replace the placeholder host in every target you plan to validate or deploy:

```yaml
targets:
  dev:
    workspace:
      host: https://<your-workspace-host>
  prod:
    workspace:
      host: https://<your-workspace-host>
```

If you leave the placeholder host in place, `databricks bundle validate` will fail.

### 2) Set your local CLI profile in `.env`

```dotenv
DATABRICKS_CONFIG_PROFILE=DEFAULT
```

If you use a different profile name, put that value here instead.

### 3) Set the main runtime config in `workspace-config.yml`

At minimum, update these fields:

```yaml
tool_provider_type: local_python
llm_endpoint_name: <your-serving-endpoint-name>
active_profile_name: default
default_compile_task_file: examples/demo_compile_task.json
```

`default_compile_task_file` is important in the new architecture: it tells `compile-tool-profile` which representative compile-time task to use when you do not pass `--task-input-file` explicitly.

You can also override `llm_endpoint_name` from `.env` with `LLM_ENDPOINT_NAME`, but keeping the main value in `workspace-config.yml` is the clearest beginner path.

### 4) Decide where Databricks runs should persist state

The example config ships with placeholder Unity Catalog tables:

```yaml
storage:
  tool_profile_table: main.agent_demo.tool_profiles
  agent_runs_table: main.agent_demo.agent_runs
  agent_output_table: main.agent_demo.agent_outputs
  local_data_dir: ./.local_state
```

For real Databricks runs, change those table names to a **catalog and schema you can create and write to**.

For local runs, Spark is usually unavailable, so the project automatically falls back to local files under `./.local_state`.

### 5) Ignore the SQL section for the demo

The `sql:` block in `workspace-config.example.yml` is for future SQL-backed tools. It is **not required** for the current `local_python` demo flow.

## Quickstart: first successful local run

### Step 1: authenticate to Databricks

```bash
databricks auth login --host https://<your-workspace-host>
```

If you want to use a non-default profile:

```bash
databricks auth login --host https://<your-workspace-host> --profile DEV
```

Then set the same profile in `.env`:

```dotenv
DATABRICKS_CONFIG_PROFILE=DEV
```

You can verify your saved profiles with:

```bash
databricks auth profiles
```

### Step 2: run preflight

```bash
uv run preflight --config-path workspace-config.yml
```

This checks that:

- `workspace-config.yml` loads
- `.env` parses
- the Databricks CLI profile resolves
- the Databricks client initializes
- `llm_endpoint_name` is present
- the tool provider can be created
- the tool registry is non-empty
- persistence targets are configured

On a clean first run, it is normal for preflight to report that **no active profile exists yet**.

### Step 3: discover tools

```bash
uv run discover-tools --config-path workspace-config.yml
```

For the built-in demo, you should see **5 tools**. The discovery output also shows side-effect level, tags, and domains for each tool.

### Step 4: compile the tool profile

You can rely on `default_compile_task_file`:

```bash
uv run compile-tool-profile --config-path workspace-config.yml
```

Or pass the compile task explicitly:

```bash
uv run compile-tool-profile \
  --config-path workspace-config.yml \
  --task-input-file examples/demo_compile_task.json
```

This discovers the full tool inventory, compiles the active allowlist for the representative compile task, and persists the active profile.

For the built-in demo, the compiled profile should allow these four tools:

- `get_user_profile`
- `search_onboarding_docs`
- `get_workspace_setting`
- `list_recent_job_runs`

And it should exclude the write tool:

- `create_support_ticket`

### Step 5: run the demo task

Use the runtime task file:

```bash
uv run run-agent-task \
  --config-path workspace-config.yml \
  --task-input-file examples/demo_run_task.json
```

A successful run shows that the project can:

- load the persisted profile
- expose only the allowed tools
- call the necessary read-only tools
- generate a final answer grounded in tool results
- persist run artifacts

If you want machine-readable output:

```bash
uv run run-agent-task \
  --config-path workspace-config.yml \
  --task-input-file examples/demo_run_task.json \
  --output json
```

### Step 6: validate locally

Fast local tests:

```bash
uv run pytest
```

Live integration evals against the configured Databricks endpoint:

```bash
uv run run-evals \
  --config-path workspace-config.yml \
  --scenario-file evals/sample_scenarios.json
```

Live evals require valid Databricks auth and may consume tokens, so use them after the local demo flow is already working.

### Success checklist

A healthy first pass looks like this:

- `preflight` passes
- `discover-tools` shows **5** tools
- `compile-tool-profile` creates or reuses an active profile
- the compiled demo profile allows **4** tools and excludes `create_support_ticket`
- `run-agent-task` completes successfully
- local artifacts appear in `./.local_state`

## Deploying to Databricks

Do this only after the local flow is green.

This repo deploys **two Python wheel jobs**:

- `compile_tool_profile_job`
- `run_agent_task_job`

The split is intentional: one job compiles and persists the active tool profile, and the second job runs the actual agent task using that profile.

### Deploy commands

```bash
databricks bundle validate --target dev
databricks bundle deploy --target dev
databricks bundle run --target dev compile_tool_profile_job
databricks bundle run --target dev run_agent_task_job
```

Run them in exactly that order. The run job expects an active profile to exist.

The deployed jobs read the workspace copy of `workspace-config.yml` from `${workspace.file_path}/workspace-config.yml`, so keep that deployed config aligned with the local config you validated.

`databricks.yml` also defines a default bundle variable named `task_input_json` for the runtime job. Downstream teams commonly replace that default payload with their own task family.

The bundled jobs use **serverless** as the default deployed path. If your workspace does not support that pattern, edit [`resources/databricks_mcp_agent_hello_world_job.yml`](resources/databricks_mcp_agent_hello_world_job.yml) and replace the default job environment configuration with the compute model your environment allows.

This starter is intentionally **not scheduled by default**. Get the on-demand flow working first, then add a schedule in a downstream project.

## Where outputs go

### Local development

When Spark is unavailable, the project falls back to local persistence under:

```text
.local_state/
├── active_tool_profile.json
├── profiles/
├── agent_runs.jsonl
└── agent_outputs.jsonl
```

This is expected and normal for local development.

### Databricks runs

When Spark is available, the project uses the Delta targets configured in `workspace-config.yml`:

- `storage.tool_profile_table`
- `storage.agent_runs_table`
- `storage.agent_output_table`

Before you rely on deployed runs, make sure those table names point to a writable location.

## What you should customize vs keep

Replace these first in a downstream project:

- [`examples/demo_compile_task.json`](examples/demo_compile_task.json)
- [`examples/demo_run_task.json`](examples/demo_run_task.json)
- [`src/databricks_mcp_agent_hello_world/demo/tools.py`](src/databricks_mcp_agent_hello_world/demo/tools.py)
- [`src/databricks_mcp_agent_hello_world/tools/registry.py`](src/databricks_mcp_agent_hello_world/tools/registry.py)
- [`evals/sample_scenarios.json`](evals/sample_scenarios.json)
- [`databricks.yml`](databricks.yml)
- [`resources/databricks_mcp_agent_hello_world_job.yml`](resources/databricks_mcp_agent_hello_world_job.yml)

Usually keep these framework files intact unless you are intentionally changing the core runtime:

- [`src/databricks_mcp_agent_hello_world/profiles/compiler.py`](src/databricks_mcp_agent_hello_world/profiles/compiler.py)
- [`src/databricks_mcp_agent_hello_world/runner/agent_runner.py`](src/databricks_mcp_agent_hello_world/runner/agent_runner.py)
- [`src/databricks_mcp_agent_hello_world/storage/result_writer.py`](src/databricks_mcp_agent_hello_world/storage/result_writer.py)
- [`src/databricks_mcp_agent_hello_world/evals/harness.py`](src/databricks_mcp_agent_hello_world/evals/harness.py)
- [`src/databricks_mcp_agent_hello_world/models.py`](src/databricks_mcp_agent_hello_world/models.py)

## Troubleshooting

### `databricks bundle validate` fails with the placeholder host

You still have `https://your-workspace.cloud.databricks.com` in `databricks.yml`.

Fix: replace it for every target you validate or deploy.

### `preflight` says `DATABRICKS_CONFIG_PROFILE` is missing

Your CLI profile name is not set in `.env` or `workspace-config.yml`.

Fix: set `DATABRICKS_CONFIG_PROFILE=<your-profile>` in `.env`.

### `preflight` or runtime cannot find `workspace-config.yml`

You did not copy the example config into the repo root.

Fix:

```bash
cp workspace-config.example.yml workspace-config.yml
```

### `compile-tool-profile` says the compile task file is missing

Your config or CLI path points at a file that does not exist.

Fix: check `default_compile_task_file` in `workspace-config.yml` or the path you passed with `--task-input-file`.

### `.env` parsing fails because of Databricks credentials

This project intentionally rejects direct local credentials in `.env` for the supported quickstart.

Fix: remove those keys and use `databricks auth login` plus a CLI profile.

### `llm_endpoint_name` is missing or wrong

The endpoint name is empty, misspelled, or points at the wrong serving endpoint.

Fix: update `workspace-config.yml` and rerun `preflight`.

Also make sure the serving endpoint supports the tool/function-calling pattern this template expects.

### `run-agent-task` fails saying no active profile exists

You skipped the compile step.

Fix:

```bash
uv run compile-tool-profile --config-path workspace-config.yml
```

Then rerun the task.

### selected tools are wrong

Check the wording in [`examples/demo_compile_task.json`](examples/demo_compile_task.json) and the metadata in [`src/databricks_mcp_agent_hello_world/tools/registry.py`](src/databricks_mcp_agent_hello_world/tools/registry.py). Task clarity and metadata quality directly affect profile compilation.

### Local logs say Spark is unavailable

That is normal during local development.

The project will use `./.local_state` instead of Delta when Spark is not available.

### Deployed job run fails during compute provisioning

Your workspace may not support the default serverless job path in the current resource file.

Fix: update [`resources/databricks_mcp_agent_hello_world_job.yml`](resources/databricks_mcp_agent_hello_world_job.yml) to use the compute pattern your workspace allows.

### Deployed runtime cannot read or write the configured Delta tables

Your `storage.*` table names point to a catalog or schema your deployed identity cannot access.

Fix: update the table names in `workspace-config.yml` to a writable location and redeploy.

### Databricks job runs but output is empty

Inspect `storage.agent_runs_table` and `storage.agent_output_table`, then confirm the compile job ran first and that the runtime task JSON is valid.
