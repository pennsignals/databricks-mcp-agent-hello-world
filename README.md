# databricks-mcp-agent-hello-world

`databricks-mcp-agent-hello-world` is a bundle-based, Python-wheel Databricks Job template for a non-interactive, tool-using agent workflow. It is designed for local development first, scheduled execution in Databricks Jobs, and a future migration path to Managed MCP without making Managed MCP a runtime dependency today.

This project is intentionally **not** a Databricks App. It does not use `app.yaml`, does not start a local web server, and keeps the runtime model aligned to Bundles plus Python wheel tasks.

## What the template includes

- provider-agnostic tool contracts: `ToolSpec`, `ToolCall`, `ToolResult`, `ToolProfile`
- a `local_python` provider and executor
- a tool-profile compiler that filters tools through a Databricks-hosted LLM endpoint
- an `AgentRunner` that enforces the allowlist in application code
- local development support with `.env` plus Databricks CLI profile auth
- real Databricks-backed local tool execution through Databricks SQL when configured
- preflight, discover-tools, compile, run, and eval entrypoints
- local JSON/JSONL persistence plus Delta append support when Spark/table config is available

## Project layout

```text
.
├── .env.example
├── AGENTS.md
├── databricks.yml
├── evals/
├── resources/
├── scripts/
├── src/
├── tests/
├── pyproject.toml
└── workspace-config.example.yml
```

## Local setup

### 1. Install dependencies

```bash
uv sync
```

### 2. Authenticate to Databricks

The recommended attended local-development path is Databricks CLI profile auth:

```bash
databricks auth login --profile DEFAULT
```

### 3. Create local config

Copy the sample environment file:

```bash
cp .env.example .env
```

Optional: also copy the YAML config if you want a checked-in local config file:

```bash
cp workspace-config.example.yml workspace-config.yml
```

Environment variables take precedence over `.env`, `.env` takes precedence over YAML, and YAML takes precedence over code defaults.

### 4. Fill in the important values

At minimum, set:

- `DATABRICKS_CONFIG_PROFILE`
- `LLM_ENDPOINT_NAME`
- `TOOL_PROFILE_TABLE`
- `AGENT_RUNS_TABLE`
- `AGENT_OUTPUT_TABLE`

For real local Databricks-backed tools, also set:

- `DATABRICKS_SQL_WAREHOUSE_ID`
- the relevant table names such as `INCIDENT_KB_TABLE`, `CUSTOMER_SUMMARY_TABLE`, and `SERVICE_INCIDENTS_TABLE`

If SQL settings are not configured and `LOCAL_TOOL_BACKEND_MODE=auto`, the local tools fall back to mock data.

## Local workflows

### Preflight

Run preflight before compiling or running the agent:

```bash
./scripts/dev/preflight.sh workspace-config.yml
```

Or:

```bash
uv run preflight --config-path workspace-config.yml
```

Preflight checks:

- config loading
- auth coherence
- prompt files
- tool registry loading
- persistence target configuration
- active profile availability
- LLM endpoint reachability

### Discover tools

Inspect the current normalized tool surface without running the agent:

```bash
./scripts/dev/discover_tools.sh workspace-config.yml
```

Or:

```bash
uv run discover-tools --config-path workspace-config.yml
```

This prints:

- tool names
- descriptions
- tags
- provider metadata
- inventory hash
- active profile information when available

### Compile a tool profile

```bash
./scripts/dev/compile_local.sh workspace-config.yml
```

Or:

```bash
uv run compile-tool-profile --config-path workspace-config.yml
```

This discovers tools, asks the configured Databricks-hosted LLM endpoint to allow or disallow them, validates the result, saves a versioned profile, and writes the active profile snapshot locally.

### Run one agent task

```bash
./scripts/dev/run_local_task.sh workspace-config.yml '{"task_name":"demo","instructions":"Find relevant incident context and summarize customer CUST-12345.","payload":{"customer_id":"CUST-12345","service_name":"billing-api"}}'
```

Or:

```bash
uv run run-agent-task --config-path workspace-config.yml --task-input-json '{"task_name":"demo","instructions":"...","payload":{}}'
```

`run-agent-task` accepts:

- `task_name`
- `instructions`
- `payload`
- optional `run_id`
- optional `idempotency_key`

### Run evals

```bash
./scripts/dev/run_evals.sh workspace-config.yml evals/sample_scenarios.json
```

Or:

```bash
uv run run-evals --config-path workspace-config.yml --scenarios-path evals/sample_scenarios.json
```

The eval harness runs canned scenarios through `AgentRunner` and records tool usage, blocked calls, outputs, and pass/fail summaries.

## Real local Databricks execution

This project supports running **locally against real Databricks services**.

That means:

- the Python process runs on your machine
- Databricks auth comes from CLI profile or compatible env vars
- the LLM calls hit your real Databricks-hosted serving endpoint
- tool functions can hit a real Databricks SQL warehouse when configured

It does **not** mean the code is executing on a Databricks cluster during local development.

## Runtime behavior

### Local persistence

Without a Databricks-backed persistence implementation, local runs write to `.local_state/`:

- `active_tool_profile.json`
- `profiles/<profile_name>_<profile_version>.json`
- `tool_profiles.jsonl`
- `agent_runs.jsonl`
- `agent_outputs.jsonl`

### Databricks Jobs

When deployed through the bundle, the package runs as Python wheel tasks in a Databricks Job.

The example bundled job currently:

1. compiles a tool profile
2. runs one agent task

That means the sample job recompiles the tool profile before each run. Hash-based compile skipping is not implemented yet.

## Bundle workflow

Validate:

```bash
databricks bundle validate
```

Deploy:

```bash
databricks bundle deploy
```

Run the sample job:

```bash
databricks bundle run databricks_mcp_agent_hello_world_job
```

## Package entrypoints

The wheel exposes:

- `preflight`
- `discover-tools`
- `compile-tool-profile`
- `run-agent-task`
- `run-evals`

Compatibility aliases also exist for the original underscore-style compile/run entrypoints.

## Adding tools

To add a new local Python tool:

1. add the function in [`builtin.py`](/Users/mbecker/git/databricks-mcp-agent-hello-world/src/databricks_mcp_agent_hello_world/tools/builtin.py)
2. register it in [`registry.py`](/Users/mbecker/git/databricks-mcp-agent-hello-world/src/databricks_mcp_agent_hello_world/tools/registry.py)
3. define a stable tool name, description, and JSON-schema input contract

If the tool should call real Databricks resources locally, use the Databricks client helpers under [`clients/`](/Users/mbecker/git/databricks-mcp-agent-hello-world/src/databricks_mcp_agent_hello_world/clients).

## Managed MCP future path

The current runtime supports `local_python` only. [`managed_mcp.py`](/Users/mbecker/git/databricks-mcp-agent-hello-world/src/databricks_mcp_agent_hello_world/providers/managed_mcp.py) is a placeholder for a future adapter. The intended migration path is to preserve:

- tool names
- tool descriptions
- argument schemas
- result envelopes
- provider/executor interfaces

## Production auth guidance

For local attended development, prefer Databricks CLI profile auth. For scheduled production jobs, use service-principal-based auth such as OAuth M2M through Databricks-supported mechanisms rather than interactive local credentials.

## Operator guide

See [`AGENTS.md`](/Users/mbecker/git/databricks-mcp-agent-hello-world/AGENTS.md) for the operator and extension guide.
