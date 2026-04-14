# databricks-mcp-agent-hello-world

`databricks-mcp-agent-hello-world` is a bundle-based, Python-wheel Databricks Job template for a non-interactive, tool-using agent workflow. The guided example path is `hello_world_demo`, and it is meant to show a beginner the full tool-backed flow end to end.

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

### 3. Set the Databricks host in `databricks.yml`

Before running `databricks bundle validate`, update the workspace host for the target environment in `databricks.yml`. At minimum, set `targets.dev.workspace.host`, and set `targets.prod.workspace.host` if you will deploy there too.

### 4. Copy config files

```bash
cp workspace-config.example.yml workspace-config.yml
```

If you use a local `.env`, keep it limited to non-secret defaults such as `DATABRICKS_CONFIG_PROFILE`. Keep `workspace-config.yml` in the repo root before you validate or deploy the bundle.

### 5. Edit `workspace-config.yml`

Set `llm_endpoint_name` and make sure the persistence table names match your workspace. Local CLI commands read the repo-root `workspace-config.yml`, while Databricks Jobs read the deployed copy at `${workspace.file_path}/workspace-config.yml`.

The `sql:` section in `workspace-config.example.yml` is optional and is only a placeholder for future SQL-backed tools. You do not need it for the current hello-world flow.
You can leave the `sql:` values as-is for the hello-world MVP path.

## Hello-world walkthrough

The default demo uses local Python tools only. SQL-backed tools are not required, and Managed MCP is not required for the MVP demo.

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

Successful `hello_world_demo` output must make four things obvious:

- how many tools were discovered in total
- which tools were allowed for the task
- which tools were actually called
- how the final answer was assembled from tool output

The important beginner signal is the difference between the full discovered set, the filtered allowlist, and the tools the model really used.

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
- `available_tools_count`
- `available_tools`
- `allowed_tools`
- `tool_calls`
- `final_answer`

`available_tools_count` and `available_tools` show the full discovered registry. `allowed_tools` shows the filtered subset exposed to the model. `tool_calls` shows the actual execution order. `final_answer` is plain English, not JSON.

Example successful output:

```json
{
  "task_name": "hello_world_demo",
  "available_tools_count": 4,
  "available_tools": ["greet_user", "search_demo_handbook", "get_demo_setting", "tell_demo_joke"],
  "allowed_tools": ["greet_user", "search_demo_handbook", "get_demo_setting"],
  "tool_calls": ["greet_user", "search_demo_handbook"],
  "final_answer": "Ada, I greeted you and checked the handbook. The handbook says the demo should stay focused on useful tools."
}
```

If `tool_calls` is empty for `hello_world_demo`, treat that as a bug or regression rather than acceptable behavior.

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

The Databricks flow is:

1. `databricks bundle validate`
2. `databricks bundle deploy`
3. run `compile_tool_profile_job`
4. run `run_agent_task_job`

The hello-world payload is passed to `run_agent_task_job` through the wheel task named parameter `task_input_json`, not through a workspace file path. Deployed Jobs read `workspace-config.yml` from `${workspace.file_path}/workspace-config.yml`.

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
