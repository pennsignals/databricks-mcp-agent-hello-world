# Architecture

[Back to README](../README.md)  
[Next: Convert the template into a real app](./CONVERT_TEMPLATE_TO_REAL_APP.md)

## Design goals

- single-agent architecture
- async non-interactive execution
- minimal framework complexity
- LLM-driven tool selection
- persisted profiles and traces
- demo assets separated from reusable framework assets

## End-to-end flow

```text
task file -> compile-tool-profile -> persisted ToolProfile
run task file -> run-agent-task -> generic runner -> persisted AgentRunRecord / AgentOutputRecord
```

Expanded flow:

```text
examples/demo_compile_task.json
  -> ToolProfileCompiler.compile(...)
  -> _filter_tools(...)
  -> ToolProfileRepository.save(...)
  -> persisted ToolProfile

examples/demo_run_task.json
  -> AgentRunner.run(...)
  -> generic runner loop
  -> ResultWriter.write_run_record(...)
  -> ResultWriter.write_output_record(...)
  -> persisted AgentRunRecord / AgentOutputRecord
```

## Compile-time tool selection

`_filter_tools(...)` in [compiler.py](/Users/mbecker/git/databricks-mcp-agent-hello-world/src/databricks_mcp_agent_hello_world/profiles/compiler.py) is the selection mechanism. The LLM receives the task plus tool metadata, then returns a profile decision with `allowed_tools` and `disallowed_tools`. The compiler validates the structure, persists the resulting `ToolProfile`, and reuses that profile when the compile task and inventory hash still match.

There is no task-name-based branching. There is no task-specific hard-coded allowlist. There is no deterministic rule engine choosing tools. Metadata quality and prompt design influence the LLM’s selection quality, so the descriptive fields in each `ToolSpec` matter.

## Runtime execution loop

The runtime loop in [agent_runner.py](/Users/mbecker/git/databricks-mcp-agent-hello-world/src/databricks_mcp_agent_hello_world/runner/agent_runner.py) works like this:

- system prompt + task message
- tools exposed = allowed tools only
- LLM may return a tool call
- application executes tool
- tool result is appended
- loop continues until final response or stop condition

This matches the standard tool-calling pattern where the model is given tools and can decide whether to call them. Runtime allowlist enforcement still remains in place as a safety boundary, so a tool name outside `allowed_tools` is blocked even if the model tries to call it.

## Persistence model

- `ToolProfile` — persisted compile output used at runtime. Key fields: `profile_name`, `profile_version`, `compile_task_name`, `compile_task_hash`, `discovered_tools`, `allowed_tools`, `disallowed_tools`, and `inventory_hash`.
- `AgentRunRecord` — persisted execution trace for a specific run. Key fields: `run_id`, `task_name`, `status`, `tools_called`, `blocked_calls`, `llm_turn_count`, `result`, and `profile_version`.
- `AgentOutputRecord` — persisted output payload for downstream consumption. Key fields: `run_id`, `task_name`, `status`, `profile_name`, `profile_version`, and `output_payload`.

Locally, persistence falls back to JSON and JSONL under `storage.local_data_dir`. On Databricks compute, the same logical artifacts are written to the configured Delta tables.

## Demo assets vs framework assets

- Framework assets: `src/databricks_mcp_agent_hello_world/profiles/compiler.py`, `src/databricks_mcp_agent_hello_world/profiles/repository.py`, `src/databricks_mcp_agent_hello_world/runner/agent_runner.py`, `src/databricks_mcp_agent_hello_world/storage/result_writer.py`, `src/databricks_mcp_agent_hello_world/storage/result_repository.py`, `src/databricks_mcp_agent_hello_world/evals/harness.py`, `src/databricks_mcp_agent_hello_world/models.py`, `src/databricks_mcp_agent_hello_world/config.py`.
- Demo assets: `src/databricks_mcp_agent_hello_world/demo/`, `src/databricks_mcp_agent_hello_world/tools/registry.py`, `examples/demo_compile_task.json`, `examples/demo_run_task.json`, `evals/sample_scenarios.json`, `databricks.yml`, `resources/databricks_mcp_agent_hello_world_job.yml`.

## What downstream teams should customize

- demo tools in [demo/tools.py](/Users/mbecker/git/databricks-mcp-agent-hello-world/src/databricks_mcp_agent_hello_world/demo/tools.py)
- task files in [examples/demo_compile_task.json](/Users/mbecker/git/databricks-mcp-agent-hello-world/examples/demo_compile_task.json) and [examples/demo_run_task.json](/Users/mbecker/git/databricks-mcp-agent-hello-world/examples/demo_run_task.json)
- prompts where applicable in [tool_filter_prompt.txt](/Users/mbecker/git/databricks-mcp-agent-hello-world/src/databricks_mcp_agent_hello_world/prompts/tool_filter_prompt.txt), [tool_audit_prompt.txt](/Users/mbecker/git/databricks-mcp-agent-hello-world/src/databricks_mcp_agent_hello_world/prompts/tool_audit_prompt.txt), and [agent_system_prompt.txt](/Users/mbecker/git/databricks-mcp-agent-hello-world/src/databricks_mcp_agent_hello_world/prompts/agent_system_prompt.txt)
- eval scenarios in [evals/sample_scenarios.json](/Users/mbecker/git/databricks-mcp-agent-hello-world/evals/sample_scenarios.json)
- bundle/job names in [databricks.yml](/Users/mbecker/git/databricks-mcp-agent-hello-world/databricks.yml) and [databricks_mcp_agent_hello_world_job.yml](/Users/mbecker/git/databricks-mcp-agent-hello-world/resources/databricks_mcp_agent_hello_world_job.yml)
- environment-specific config in [workspace-config.example.yml](/Users/mbecker/git/databricks-mcp-agent-hello-world/workspace-config.example.yml)

## What downstream teams should not fork

Do not fork the generic runner loop, the profile compiler architecture, or the result persistence model unless you have a genuine platform-level need. The stable extension seams are the demo assets, task files, prompts, eval scenarios, and deployment names, not the framework core.
