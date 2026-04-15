# Convert the template into a real app

[Back to README](../README.md)  
[Reference: Architecture](./ARCHITECTURE.md)

## Before you start

Previous PRDs are already part of the template. Tool selection remains LLM-driven, and you should customize the demo assets first rather than forking the framework core.

## Step 1 — Rename the demo task family

Edit these files to replace the demo task family name and labels:

- [`examples/demo_compile_task.json`](../examples/demo_compile_task.json) — change the compile task name to your representative task family.
- [`examples/demo_run_task.json`](../examples/demo_run_task.json) — change the runtime task name and payload labels for the real job.
- [`evals/sample_scenarios.json`](../evals/sample_scenarios.json) — rename scenario descriptions and expected task names.
- [`databricks.yml`](../databricks.yml) — rename the bundle and the default `task_input_json` payload if it still uses the demo task family.
- [`resources/databricks_mcp_agent_hello_world_job.yml`](../resources/databricks_mcp_agent_hello_world_job.yml) — rename the job names and task keys that still carry template-era names.

## Step 2 — Replace the demo tools

Edit these files:

- [`src/databricks_mcp_agent_hello_world/demo/tools.py`](../src/databricks_mcp_agent_hello_world/demo/tools.py) — remove the demo tool implementations and add your real tool implementations.
- [`src/databricks_mcp_agent_hello_world/tools/registry.py`](../src/databricks_mcp_agent_hello_world/tools/registry.py) — update the registry entries, JSON schemas, and the metadata fields the LLM compiler uses.

Populate `description`, `capability_tags`, `side_effect_level`, `data_domains`, and `example_uses` carefully. Keep tool names descriptive and non-overlapping.

Do not replace LLM-driven tool selection with a manual allowlist. Do not add task-name-based branching to the compiler.

## Step 3 — Replace the compile task file

Edit [`examples/demo_compile_task.json`](../examples/demo_compile_task.json).

This file represents the representative task contract for the task family. It should be stable enough to reuse profiles across runs, and specific enough for the LLM compiler to choose a minimal useful subset.

Do not include one-off payload details that would cause needless profile churn.

## Step 4 — Replace the runtime task file

Edit [`examples/demo_run_task.json`](../examples/demo_run_task.json).

The runtime task file carries the real per-run payload. Unlike the compile task file, it can vary from run to run while still relying on the persisted profile compiled from the representative task contract.

## Step 5 — Update prompts only if needed

Only edit these files if your new domain genuinely needs prompt changes:

- [`src/databricks_mcp_agent_hello_world/prompts/tool_filter_prompt.txt`](../src/databricks_mcp_agent_hello_world/prompts/tool_filter_prompt.txt)
- [`src/databricks_mcp_agent_hello_world/prompts/tool_audit_prompt.txt`](../src/databricks_mcp_agent_hello_world/prompts/tool_audit_prompt.txt)
- [`src/databricks_mcp_agent_hello_world/prompts/agent_system_prompt.txt`](../src/databricks_mcp_agent_hello_world/prompts/agent_system_prompt.txt)

The default generic prompts should remain unchanged unless the new domain actually requires a prompt change. Prompt changes must stay generic and must not reintroduce demo-specific branching.

## Step 6 — Replace eval scenarios

Edit [`evals/sample_scenarios.json`](../evals/sample_scenarios.json).

Create scenarios that cover:

1. happy path
2. under-selection
3. over-selection
4. forbidden write tool selection
5. output completeness

## Step 7 — Rename deployment resources

Edit these files:

- [`databricks.yml`](../databricks.yml) — rename bundle names and environment-facing defaults.
- [`resources/databricks_mcp_agent_hello_world_job.yml`](../resources/databricks_mcp_agent_hello_world_job.yml) — rename job names and task keys while keeping the wheel entry points aligned.
- [`workspace-config.example.yml`](../workspace-config.example.yml) — update table names, environment variables if your deployment conventions require them, and the default compile task file path.
- [`src/databricks_mcp_agent_hello_world/config.py`](../src/databricks_mcp_agent_hello_world/config.py) — only if you are making a true platform-level configuration change rather than a normal template conversion.

This is where you rename bundle names, job names, table names, environment variables, and the default compile task file path.

## Step 8 — Verify the full workflow

Use this checklist only:

1. compile profile locally
2. run agent locally
3. run evals locally
4. deploy bundle
5. run compile job in Databricks
6. run agent job in Databricks
7. inspect persisted artifacts

## Definition of done

Success means:

- demo assets fully replaced
- framework core unchanged except where domain truly requires it
- LLM-driven tool selection preserved
- all evals pass
- Databricks job path succeeds end-to-end
