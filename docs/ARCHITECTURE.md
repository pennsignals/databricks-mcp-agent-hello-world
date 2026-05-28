# Architecture

[Back to README](../README.md)

This template is a small Databricks Jobs runtime for batch/non-interactive LLM agent tasks.

## Config Loading

`src/databricks_mcp_agent_hello_world/config.py` is the source of truth for supported config keys.

The default config path is `workspace-config.yml`. Loading is strict: unknown top-level and nested YAML keys fail fast.

The final config shape is:

- `llm_endpoint_name`
- `max_agent_steps`
- `log_level`
- `databricks_config_profile`
- `workspace_host`
- `agent_system_prompt_path`
- `tools.local_python.enabled`
- `tools.databricks_mcp.enabled`
- `tools.databricks_mcp.server.name`
- `tools.databricks_mcp.server.url`
- `storage.local_data_dir`
- `storage.agent_events_table`

Databricks authentication is handled by the Databricks SDK. The template passes `databricks_config_profile` and/or `workspace_host` through one shared client helper used by LLM, MCP, and preflight code.

`agent_system_prompt_path` is optional. If omitted, the built-in default prompt is used. If set, the path must exist and contain non-empty text.

## Tool Source Discovery

The agent can use tools from multiple enabled sources.

Local Python tools are for app-specific logic. Databricks MCP tools are for governed/shared Databricks-hosted tools. Tool names must be unique across enabled sources.

The default local inventory includes `lookup_customer` plus the write-like `create_support_ticket` example on purpose. The read-only demo task should select `lookup_customer` and avoid `create_support_ticket`, demonstrating model-driven selection from the full inventory.

Discovery returns `RuntimeTool` objects with:

- a global tool name
- a model-visible function spec
- an execution callable
- source metadata for traces and discovery output

When multiple sources are enabled, the composite provider combines their tools and fails if two tools share the same name.

## Agent Runner Loop

`AgentRunner` loads the enabled tool inventory, sends that inventory to the configured LLM endpoint, executes requested tool calls, and repeats until the model returns a final answer or the run reaches `max_agent_steps`.

Tool selection is model-driven. The runtime validates that a requested tool exists before executing it.

## Storage/Event Persistence

The runtime persists append-only execution events.

If `storage.agent_events_table` is unset, events are written to local JSONL under `storage.local_data_dir`.

If `storage.agent_events_table` is set, an active Spark session is required and events are written to that table.

The template never silently falls back from table persistence to local persistence.

## Runtime And Eval Contracts

Normal agent run records have one of two statuses:

- `success`
- `max_steps_exceeded`

Unexpected runtime failures are raised as exceptions. The runner emits a `run_failed` event before re-raising; evals show those failures as scenario execution errors rather than agent run records.

`tools_called` is the canonical tool-call trace on `AgentRunRecord`. The `result` payload is reserved for user-facing output such as `final_response`.

Evals are a lightweight smoke-test harness that verifies run status, expected tool use, and required output text.

Supported scenario assertion fields are:

- `expected_status`
- `required_executed_tools`
- `forbidden_executed_tools`
- `required_output_substrings`

Eval summary reports are written locally under `storage.local_data_dir`; agent execution events still follow the configured storage route.

## CLI/Wheel Entrypoint Flow

Local console commands and Databricks wheel entrypoints delegate to the same command implementations.

The main operator commands are:

- `preflight --config-path workspace-config.yml`
- `discover-tools --config-path workspace-config.yml`
- `run-agent-task --config-path workspace-config.yml --task-input-file examples/demo_run_task.json`
- `run-evals --config-path workspace-config.yml --scenario-file evals/sample_scenarios.json`

Databricks Jobs run the packaged wheel and pass the same config and task arguments through the job definition.
