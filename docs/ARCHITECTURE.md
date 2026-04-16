# Architecture

[Back to README](../README.md)  
[Next: Convert the template into a real app](./CONVERT_TEMPLATE_TO_REAL_APP.md)

## Design goals

- single-agent architecture
- async non-interactive execution
- minimal framework complexity
- LLM-driven tool selection
- persisted run traces and outputs
- demo assets separated from reusable framework assets

## End-to-end flow

```text
task file -> run-agent-task -> generic runner -> persisted AgentRunRecord / AgentOutputRecord
```

Expanded flow:

```text
examples/demo_run_task.json
  -> AgentRunner.run(...)
  -> provider.list_tools(...)
  -> model receives the full discovered tool inventory
  -> generic runner loop
  -> ResultWriter.write_run_record(...)
  -> ResultWriter.write_output_record(...)
```

## Runtime tool selection

The runtime loop in [`src/databricks_mcp_agent_hello_world/runner/agent_runner.py`](../src/databricks_mcp_agent_hello_world/runner/agent_runner.py) exposes the full discovered tool inventory to the model for each run.

There is no compile step. There is no task-specific hard-coded allowlist. There is no deterministic prefilter layer. The model decides which tools to call, and the application only validates that a requested tool actually exists before executing it.

This matches the standard tool-calling pattern where the model is given tools and can decide whether to call them.

## Persistence model

- `AgentRunRecord` captures the execution trace for a run, including status, tool calls, LLM turn count, and result payload.
- `AgentOutputRecord` stores the final output payload for downstream consumption.

Locally, persistence falls back to JSONL under `storage.local_data_dir`. On Databricks compute, the same logical artifacts are written to the configured Delta tables.

## Demo assets vs framework assets

- Framework assets: `src/databricks_mcp_agent_hello_world/runner/agent_runner.py`, `src/databricks_mcp_agent_hello_world/storage/result_writer.py`, `src/databricks_mcp_agent_hello_world/storage/result_repository.py`, `src/databricks_mcp_agent_hello_world/evals/harness.py`, `src/databricks_mcp_agent_hello_world/models.py`, `src/databricks_mcp_agent_hello_world/config.py`
- Demo assets: `src/databricks_mcp_agent_hello_world/demo/tools.py`, `src/databricks_mcp_agent_hello_world/tools/registry.py`, `examples/demo_run_task.json`, `evals/sample_scenarios.json`, `databricks.yml`, `workspace-config.example.yml`, `resources/databricks_mcp_agent_hello_world_job.yml`

## What downstream teams should customize

- `src/databricks_mcp_agent_hello_world/demo/tools.py`
- `src/databricks_mcp_agent_hello_world/tools/registry.py`
- `examples/demo_run_task.json`
- `evals/sample_scenarios.json`
- `databricks.yml`
- `workspace-config.example.yml`
- `resources/databricks_mcp_agent_hello_world_job.yml`
- `src/databricks_mcp_agent_hello_world/prompts/agent_system_prompt.txt` only if the domain genuinely needs it

## Advanced concepts

Precompiled profiles, `allowed_tools`, and blocked tool-call policy layers are intentionally out of scope for this template. They may be useful later for larger inventories, governance, or token optimization, but they are not implemented here.
