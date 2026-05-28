# Convert The Template To A Real App

[Back to README](../README.md)
[Architecture](./ARCHITECTURE.md)

Use this checklist after the README quickstart works.

## 1. Replace The Demo Task

Edit [examples/demo_run_task.json](../examples/demo_run_task.json).

This file is the canonical sample task. The local demo command and default job wiring both point at it.

## 2. Replace Local Python Tools

Edit:

- [src/databricks_mcp_agent_hello_world/app/tools.py](../src/databricks_mcp_agent_hello_world/app/tools.py)
- [src/databricks_mcp_agent_hello_world/app/registry.py](../src/databricks_mcp_agent_hello_world/app/registry.py)

For each local tool, define:

- `name`
- `description`
- `input_schema`
- `fn`

The local adapter turns those fields into the function spec shown to the model.

## 3. Configure Tool Sources

The agent can use tools from multiple enabled sources.

Local Python tools are for app-specific logic. Databricks MCP tools are for governed/shared Databricks-hosted tools. Tool names must be unique across enabled sources.

For local app logic, keep:

```yaml
tools:
  local_python:
    enabled: true
```

For a Databricks MCP source, set:

```yaml
tools:
  databricks_mcp:
    enabled: true
    server:
      name: uc_functions
      url: https://<workspace-hostname>/api/2.0/mcp/functions/<catalog>/<schema>
```

## 4. Update Prompt Behavior Only If Needed

`agent_system_prompt_path` is optional.

If omitted, the built-in default prompt is used. If set, the path must exist and contain non-empty text.

Edit [src/databricks_mcp_agent_hello_world/prompts/agent_system_prompt.txt](../src/databricks_mcp_agent_hello_world/prompts/agent_system_prompt.txt) only when the default prompt no longer fits your domain.

## 5. Choose Storage Routing

For local development, keep:

```yaml
storage:
  local_data_dir: ./.local_state
  agent_events_table: null
```

If `storage.agent_events_table` is unset, events are written to local JSONL under `storage.local_data_dir`.

If `storage.agent_events_table` is set, an active Spark session is required and events are written to that table.

The template never silently falls back from table persistence to local persistence.

## 6. Replace Eval Scenarios

Edit [evals/sample_scenarios.json](../evals/sample_scenarios.json).

Evals are a lightweight smoke-test harness that verifies run status, expected tool use, and required output text.

Normal run statuses are `success` and `max_steps_exceeded`. Unexpected runtime failures are exceptions; evals report them as scenario execution errors. `tools_called` is the canonical tool-call trace, while `result` contains user-facing output.

Supported scenario assertion fields are:

- `expected_status`
- `required_executed_tools`
- `forbidden_executed_tools`
- `required_output_substrings`

Eval summary reports are written locally under `storage.local_data_dir`; agent execution events still follow the configured storage route.

Keep scenarios small and tied to behavior users expect from the app.

## 7. Update Job Wiring

Edit:

- [databricks.yml](../databricks.yml)
- [resources/jobs.yml](../resources/jobs.yml)
- [workspace-config.example.yml](../workspace-config.example.yml)

Keep local console commands and Databricks wheel task arguments aligned around the same config and task files unless your app intentionally needs separate task inputs.

## 8. Validate

Run:

```bash
preflight --config-path workspace-config.yml
discover-tools --config-path workspace-config.yml
run-agent-task --config-path workspace-config.yml --task-input-file examples/demo_run_task.json
python -m nox -s unit
python -m nox -s contract
python -m nox -s tests
```

Before using real data, review persisted event payloads. They can include task inputs, prompt messages, tool arguments, tool results, model responses, errors, and final outputs.
