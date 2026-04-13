# databricks-mcp-agent-hello-world

`databricks-mcp-agent-hello-world` is a bundle-based, Python-wheel Databricks Job template for a non-interactive, tool-using agent workflow. PRD 3 keeps one guided example path, `hello_world_demo`, while making the runtime durable enough for scheduled jobs.

This project is not a Databricks App and does not use `app.yaml`.

For MVP, `local_python` is the only working runtime backend. The provider/executor abstraction is intentionally future-ready, and `managed_mcp` is a reserved future value, but it is not implemented in this template.

## Local quickstart

### 1. Install dependencies

```bash
uv sync
```

### 2. Authenticate locally

```bash
databricks auth login --host https://<your-workspace-url>
```

The supported local quickstart uses Databricks CLI profile auth. Keep direct Databricks secrets out of `.env`.

### 3. Copy config files

```bash
cp workspace-config.example.yml workspace-config.yml
```

If you use a local `.env`, keep it limited to non-secret defaults such as `DATABRICKS_CONFIG_PROFILE`.

### 4. Edit `workspace-config.yml`

Set `llm_endpoint_name` and make sure the persistence table names match your workspace. `workspace-config.yml` is the primary runtime config file.

## Hello-world walkthrough

The frozen demo task is `hello_world_demo`. The checked-in task input lives at [examples/hello_world_task.json](/Users/mbecker/git/databricks-mcp-agent-hello-world/examples/hello_world_task.json) and asks the agent to write a short report for Ada using only relevant tools.

The default tool registry contains exactly four local Python tools, in this order:

- `greet_user`
- `search_demo_handbook`
- `get_demo_setting`
- `tell_demo_joke`

For `hello_world_demo`, the expected useful subset is:

- Allowed: `greet_user`, `search_demo_handbook`, `get_demo_setting`
- Filtered out: `tell_demo_joke`

The joke tool is intentionally irrelevant so the demo clearly shows both discovery and restriction.

### Run the documented local flow

```bash
uv run preflight --config-path workspace-config.yml
uv run discover-tools --config-path workspace-config.yml
uv run compile-tool-profile --config-path workspace-config.yml
uv run run-agent-task --config-path workspace-config.yml --task-input-file examples/hello_world_task.json --output json
```

You can also run the same flow with the thin wrapper:

```bash
./scripts/dev/run_hello_world.sh workspace-config.yml
```

The hello-world JSON result should visibly include these top-level fields:

- `task_name`
- `available_tools`
- `allowed_tools`
- `disallowed_tools`
- `tool_calls`
- `final_answer`

`available_tools` shows the full discovered registry in order. `allowed_tools` and `disallowed_tools` show the compiled filtered profile in order. `tool_calls` shows the actual execution order. `final_answer` is plain English, not JSON.

## Commands

The supported top-level console commands are:

- `preflight`
- `discover-tools`
- `compile-tool-profile`
- `run-agent-task`
- `run-evals`

Every command accepts `--config-path`, which defaults to `workspace-config.yml`.

### `preflight`

`preflight` checks:

- config file parse
- `.env` parse when present
- `DATABRICKS_CONFIG_PROFILE` resolution
- Databricks client initialization
- `llm_endpoint_name`
- local tool registry import
- at least one registered tool
- provider factory resolution
- persistence target names
- read-only reachability of configured Delta targets when Spark is available
- whether an active profile currently exists
- whether profile compilation is available in the current environment

It does not call the LLM, compile profiles, run the agent, or write to Delta.

### `discover-tools`

`discover-tools` prints the provider type, total tool count, normalized tool names, tool descriptions, and input schema summaries.

### `compile-tool-profile`

`compile-tool-profile` compiles the frozen hello-world allowlist so the local demo is deterministic and inspectable. Scheduled runs load the active profile from the configured Delta table and reuse it when the discovered inventory hash has not changed, unless `--force-refresh` is set.

### `run-agent-task`

`run-agent-task` accepts exactly one of:

- `--task-input-json <json>`
- `--task-input-file <path>`

It never compiles implicitly. If no active profile exists for the configured `active_profile_name`, the command exits with a clear error and you should run `compile-tool-profile` first.

### `run-evals`

`run-evals` executes exactly two hello-world eval scenarios:

- `hello_world_happy_path`
- `allowlist_enforced`

You can run all scenarios or select one with `--scenario <id>`.

## Databricks Job path

The default bundle deploys two separate Python wheel jobs:

- `compile_tool_profile_job`
- `run_agent_task_job`

The hello-world payload is passed to `run_agent_task_job` through the wheel task named parameter `task_input_json`, not through a workspace file path.

Validate the bundle:

```bash
databricks bundle validate
```

Deploy the bundle:

```bash
databricks bundle deploy
```

Run the demo job:

```bash
databricks bundle run compile_tool_profile_job
databricks bundle run run_agent_task_job
```

Local development uses attended Databricks CLI profile auth. Scheduled Jobs should use unattended auth such as service principal OAuth.
