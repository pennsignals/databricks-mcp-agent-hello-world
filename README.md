# databricks-mcp-agent-hello-world

`databricks-mcp-agent-hello-world` is a bundle-based, Python-wheel Databricks Job template for a non-interactive, tool-using agent workflow. It is designed for local development first, scheduled execution in Databricks Jobs, and a future migration path to Managed MCP without making Managed MCP a runtime dependency today.

This project is not a Databricks App and does not use `app.yaml`.

## Local quickstart

### 1. Install dependencies

```bash
uv sync
```

### 2. Authenticate locally

```bash
databricks auth login --host https://<your-workspace-url>
```

This stores attended local auth in your Databricks CLI profile. The supported local quickstart path uses that profile instead of putting Databricks credentials in `.env`.

### 3. Copy config files

```bash
cp .env.example .env
cp workspace-config.example.yml workspace-config.yml
```

### 4. Edit the local config

Update:

- `.env`
- `workspace-config.yml`

Set `llm_endpoint_name` in `workspace-config.yml`, and make sure the persistence table names match your workspace. Keep `.env` limited to non-secret local defaults such as `DATABRICKS_CONFIG_PROFILE` and `LOG_LEVEL`.

### 5. Run the local commands

```bash
uv run preflight --config-path workspace-config.yml
uv run discover-tools --config-path workspace-config.yml
uv run compile-tool-profile --config-path workspace-config.yml
uv run run-agent-task --config-path workspace-config.yml --task-input-file examples/hello_world_task.json
```

## Commands

The supported top-level console commands are:

- `preflight`
- `discover-tools`
- `compile-tool-profile`
- `run-agent-task`
- `run-evals`

Every command accepts `--config-path`, which defaults to `workspace-config.yml`.

### `preflight`

`preflight` is a lightweight validation command. It checks:

- config file exists and parses
- `.env` parsing succeeds when `.env` is present
- `DATABRICKS_CONFIG_PROFILE` resolves
- Databricks client initialization succeeds
- `llm_endpoint_name` is present
- local tool registry imports successfully
- at least one tool is registered
- `tool_provider_type` is recognized
- persistence target names are present

It does not call the LLM, compile a profile, run the agent, or write to Delta.

### `discover-tools`

`discover-tools` loads the configured tool provider and prints the normalized tool inventory without calling the LLM, compiling profiles, or executing tools.

### `compile-tool-profile`

`compile-tool-profile` discovers tools, asks the configured Databricks-hosted LLM endpoint to build an allowlist, validates the result, and saves the active profile locally.

### `run-agent-task`

`run-agent-task` accepts exactly one of:

- `--task-input-json <json>`
- `--task-input-file <path>`

The sample quickstart uses [`examples/hello_world_task.json`](/Users/mbecker/git/databricks-mcp-agent-hello-world/examples/hello_world_task.json).

### `run-evals`

`run-evals` executes the sample eval scenarios and optionally filters to one scenario with `--scenario <id>`.

## Dev scripts

The supported thin wrappers are:

- [`scripts/dev/preflight.sh`](/Users/mbecker/git/databricks-mcp-agent-hello-world/scripts/dev/preflight.sh)
- [`scripts/dev/discover_tools.sh`](/Users/mbecker/git/databricks-mcp-agent-hello-world/scripts/dev/discover_tools.sh)
- [`scripts/dev/compile_profile.sh`](/Users/mbecker/git/databricks-mcp-agent-hello-world/scripts/dev/compile_profile.sh)
- [`scripts/dev/run_hello_world.sh`](/Users/mbecker/git/databricks-mcp-agent-hello-world/scripts/dev/run_hello_world.sh)

Each script defaults to `workspace-config.yml` and only calls the documented console commands.

## Bundle workflow

Validate the bundle:

```bash
databricks bundle validate
```

Deploy the bundle:

```bash
databricks bundle deploy
```

Run the sample job:

```bash
databricks bundle run databricks_mcp_agent_hello_world_job
```

The local path uses Databricks CLI profile auth for attended development. Future scheduled-job auth should use unattended credentials such as service principal OAuth.
