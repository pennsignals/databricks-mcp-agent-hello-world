# Convert the template into a real app

[Back to README](../README.md)  
[Reference: Architecture](./ARCHITECTURE.md)

## Before you start

Tool selection stays LLM-driven in this template. Customize the demo assets first instead of forking the framework core.

## Step 1 — Rename the demo task family

Edit these files:

- [`examples/demo_run_task.json`](../examples/demo_run_task.json)
- [`evals/sample_scenarios.json`](../evals/sample_scenarios.json)
- [`databricks.yml`](../databricks.yml)
- [`resources/databricks_mcp_agent_hello_world_job.yml`](../resources/databricks_mcp_agent_hello_world_job.yml)

## Step 2 — Replace the demo tools

Edit these files:

- [`src/databricks_mcp_agent_hello_world/demo/tools.py`](../src/databricks_mcp_agent_hello_world/demo/tools.py)
- [`src/databricks_mcp_agent_hello_world/tools/registry.py`](../src/databricks_mcp_agent_hello_world/tools/registry.py)

Populate `description`, `capability_tags`, `side_effect_level`, `data_domains`, and `example_uses` carefully.

Do not replace LLM-driven tool selection with manual Python-side filtering or deterministic routing.

## Step 3 — Replace the runtime task file

Edit [`examples/demo_run_task.json`](../examples/demo_run_task.json).

This file carries the per-run payload the job will execute.

## Step 4 — Update prompts only if needed

Only edit [`src/databricks_mcp_agent_hello_world/prompts/agent_system_prompt.txt`](../src/databricks_mcp_agent_hello_world/prompts/agent_system_prompt.txt) if your new domain genuinely needs it.

## Step 5 — Replace eval scenarios

Edit [`evals/sample_scenarios.json`](../evals/sample_scenarios.json).

Create scenarios that cover:

1. happy path
2. missing tool use
3. unexpected write-tool use
4. output completeness

## Step 6 — Rename deployment resources

Edit these files:

- [`databricks.yml`](../databricks.yml)
- [`resources/databricks_mcp_agent_hello_world_job.yml`](../resources/databricks_mcp_agent_hello_world_job.yml)
- [`workspace-config.example.yml`](../workspace-config.example.yml)
- [`src/databricks_mcp_agent_hello_world/config.py`](../src/databricks_mcp_agent_hello_world/config.py) only if you are making a true platform-level config change

## Step 7 — Verify the full workflow

Use this checklist:

1. run preflight locally
2. discover tools locally
3. run the agent locally
4. run evals locally
5. deploy the bundle
6. run the Databricks job
7. inspect persisted artifacts

## Definition of done

Success means:

- demo assets fully replaced
- framework core unchanged except where the domain truly requires it
- LLM-driven tool selection preserved
- evals pass
- the Databricks job path succeeds end to end
