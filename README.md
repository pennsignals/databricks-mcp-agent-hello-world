# databricks-mcp-agent-hello-world

`databricks-mcp-agent-hello-world` is a local-first, production-oriented Python wheel template for formulaic Databricks agent workloads. It uses local Python code tools today, keeps the runtime free of Databricks Public Preview dependencies, and preserves a narrow future path to Managed MCP through provider-compatible interfaces.

The package is built around:

- canonical `ToolSpec`, `ToolCall`, `ToolResult`, and `ToolProfile` contracts
- a default `LocalPythonToolProvider` and `LocalPythonToolExecutor`
- a `ToolProfileCompiler` that filters a discovered tool catalog through a Databricks-hosted LLM endpoint
- an `AgentRunner` that enforces the allowlist in application code and executes one tool at a time
- append-friendly persistence for profiles, runs, outputs, and local fallbacks
- Databricks wheel-task friendly entrypoints for compile and run

## Project layout

```text
.
├── databricks.yml
├── resources/
│   └── databricks_mcp_agent_hello_world_job.yml
├── scripts/
│   └── dev/
│       ├── compile_local.sh
│       └── run_local_task.sh
├── src/
│   └── databricks_mcp_agent_hello_world/
│       ├── cli.py
│       ├── config.py
│       ├── llm_client.py
│       ├── logging_utils.py
│       ├── models.py
│       ├── profiles/
│       ├── providers/
│       ├── runner/
│       ├── storage/
│       └── tools/
├── tests/
├── pyproject.toml
└── workspace-config.example.yml
```

## Quick start

### 1. Prerequisites

- Python 3.11+
- `uv`
- Databricks CLI authenticated locally
- A Databricks-hosted LLM endpoint that supports OpenAI-compatible chat/function calling

### 2. Install dependencies

```bash
uv sync
```

### 3. Create a local config file

```bash
cp workspace-config.example.yml workspace-config.yml
```

Then set:

- `llm_endpoint_name`
- `active_profile_name`
- target Delta table names if you want Spark-backed persistence on Databricks
- any auth-related environment variables such as `DATABRICKS_CLI_PROFILE`

### 4. Compile a tool profile locally

```bash
./scripts/dev/compile_local.sh workspace-config.yml
```

This will:

- discover the local Python tools in [`src/databricks_mcp_agent_hello_world/tools/registry.py`](/Users/mbecker/git/databricks-mcp-agent-hello-world/src/databricks_mcp_agent_hello_world/tools/registry.py)
- normalize them into a canonical inventory
- ask your configured Databricks-hosted LLM endpoint to allow or disallow them
- validate that every discovered tool appears exactly once in the result
- save an active profile snapshot and append a versioned profile record

### 5. Run the starter agent locally

```bash
./scripts/dev/run_local_task.sh workspace-config.yml '{"task_name":"demo","instructions":"Find relevant incident context and summarize customer CUST-12345.","payload":{"customer_id":"CUST-12345","service_name":"billing-api"}}'
```

The built-in tools are intentionally self-contained mock retrieval and structured lookup functions so the template remains runnable without preview Databricks runtime features.

## How to add your own tools

Open:

- [`src/databricks_mcp_agent_hello_world/tools/builtin.py`](/Users/mbecker/git/databricks-mcp-agent-hello-world/src/databricks_mcp_agent_hello_world/tools/builtin.py)
- [`src/databricks_mcp_agent_hello_world/tools/registry.py`](/Users/mbecker/git/databricks-mcp-agent-hello-world/src/databricks_mcp_agent_hello_world/tools/registry.py)

Add a new Python function in `builtin.py`, then register it in `registry.py` with:

- a stable tool name
- a description written for the LLM
- a JSON schema for arguments
- tags if helpful

## Runtime behavior

### Local

When no active Spark session is available, the project writes tool profiles, run records, and outputs to `.local_state/` as JSON and JSONL artifacts.

### Databricks Job

When Spark is available and table names are configured, the project appends tool profiles, run records, and outputs to Delta tables.

## Configuration contract

The runtime supports the required settings from the revised spec. The main ones are:

- `DATABRICKS_CLI_PROFILE`
- `WORKSPACE_HOST`
- `LLM_ENDPOINT_NAME`
- `TOOL_PROVIDER_TYPE`
- `TOOL_FILTER_PROMPT_PATH`
- `TOOL_AUDIT_PROMPT_PATH`
- `TOOL_PROFILE_TABLE`
- `AGENT_RUNS_TABLE`
- `AGENT_OUTPUT_TABLE`
- `ACTIVE_PROFILE_NAME`
- `MAX_ALLOWED_TOOLS`
- `MAX_AGENT_STEPS`
- `LOG_LEVEL`
- `AUTH_MODE`

Environment variables override YAML config values.

## Bundle workflow

Validate locally:

```bash
databricks bundle validate
```

Deploy:

```bash
databricks bundle deploy
```

Run the job:

```bash
databricks bundle run databricks_mcp_agent_hello_world_job
```

## Job entrypoints

The wheel exposes two entrypoints:

- `compile_tool_profile`
- `run_agent_task`

The bundle job first compiles the profile and then runs one agent task using that active profile.

## Architecture notes

- The runtime depends on provider-agnostic tool contracts, not MCP transport.
- The current implementation supports `local_python` at runtime.
- [`src/databricks_mcp_agent_hello_world/providers/managed_mcp.py`](/Users/mbecker/git/databricks-mcp-agent-hello-world/src/databricks_mcp_agent_hello_world/providers/managed_mcp.py) reserves the future adapter shape without making Managed MCP a runtime dependency.
- The sequential loop is deterministic by design: one LLM turn, at most one tool decision set, one tool execution at a time, repeated until completion or stop conditions.

## Important next steps for real projects

This is still starter code. For a real deployment, you will likely want to:

- replace mock retrieval and lookup tools with real business logic
- point persistence at governed Delta tables
- harden Databricks auth and secret management for service-principal OAuth M2M
- add retries and timeout policy around LLM calls and tool execution
- expand tests to cover real Spark-backed persistence in CI
