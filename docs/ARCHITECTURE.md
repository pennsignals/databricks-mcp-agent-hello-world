# Architecture

[Back to README](../README.md)

This template is a small Databricks Jobs runtime for batch/non-interactive LLM agent tasks.

## Config Loading

`src/databricks_tool_agent_template/config.py` is the source of truth for supported config keys.

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

All Databricks SDK client construction belongs in `clients/databricks.py`; other modules should depend on the shared factory helpers.

`agent_system_prompt_path` is optional. If omitted, the built-in default prompt is used. If set, the path must exist and contain non-empty text.

## Tool Source Discovery

The agent can use tools from multiple enabled sources.

Local Python tools are for app-specific logic. Databricks MCP tools are for governed/shared Databricks-hosted tools. Tool names must be unique across enabled sources.

MCP is optional at the tool-provider configuration layer. The template still depends on `databricks-openai` because the package is Databricks-first and uses Databricks-hosted LLM execution. Keeping one dependency profile avoids extra install modes and keeps the template easier to understand.

The default local inventory includes `lookup_customer` plus the write-like `create_support_ticket` example on purpose. The read-only demo task should select `lookup_customer` and avoid `create_support_ticket`, demonstrating model-driven selection from the full inventory.

Local tools are customized through `app/tools.py` and `app/registry.py`.
`LocalPythonToolProvider` is framework internals and should not be edited for
normal app customization. The app registry builder converts
`LocalToolDefinition` entries into `RuntimeTool` objects, and `AgentRunner`
executes the selected `RuntimeTool.execute` callable after argument validation.
Lower-level conversion helpers are implementation details, not the recommended
extension path.

Discovery returns `RuntimeTool` objects with:

- a global tool name
- a model-visible function spec
- an execution callable
- source metadata for traces and discovery output

When multiple sources are enabled, the composite provider combines their tools and fails if two tools share the same name.

## Agent Runner Loop

`AgentRunner` loads the enabled tool inventory, sends that inventory to the configured LLM endpoint, executes requested tool calls, and repeats until the model returns a final answer or the run reaches `max_agent_steps`.

Tool selection is model-driven. The Databricks LLM client explicitly uses automatic tool selection so the model can choose from the full tool inventory. The runtime validates that a requested tool exists before executing it.

## Storage/Event Persistence

The runtime persists append-only execution events.

If `storage.agent_events_table` is unset, events are written to local JSONL under `storage.local_data_dir`.

If `storage.agent_events_table` is set, an active Spark session is required and events are written to that table.

The template never silently falls back from table persistence to local persistence.

Observability events persist normalized LLM turn payloads, not raw SDK responses. Normalized LLM response events contain only assistant `content` and normalized `tool_calls`.

Run summaries include `started_at` and `completed_at`. Individual event records continue to include `created_at` for the time each event was emitted.

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

Local console commands and Databricks wheel entrypoints delegate to the same command implementations. Console entrypoints raise `SystemExit(code)`. Package-root Databricks wheel entrypoints call non-exiting `*_main()` functions and only raise `SystemExit(nonzero)` on failure.

The main operator commands are:

- `preflight --config-path workspace-config.yml`
- `discover-tools --config-path workspace-config.yml`
- `run-agent-task --config-path workspace-config.yml --task-input-file examples/demo_run_task.json`
- `run-evals --config-path workspace-config.yml --scenario-file evals/sample_scenarios.json`

Databricks Jobs run the packaged wheel and pass the same config and task arguments through the job definition.
