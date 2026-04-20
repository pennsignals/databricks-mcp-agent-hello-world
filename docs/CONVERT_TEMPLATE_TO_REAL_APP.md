# Convert the template into a real app

[Back to README](../README.md)  
[Reference: Architecture](./ARCHITECTURE.md)

Use this guide when you are adapting the template for a real downstream app. For setup, first run, and troubleshooting, use the [README](../README.md). For runtime, provider, config, and storage rationale, use [Architecture](./ARCHITECTURE.md).

## Step 1 — Rename the demo task family

Edit these files:

- [`examples/demo_run_task.json`](../examples/demo_run_task.json)
- [`evals/sample_scenarios.json`](../evals/sample_scenarios.json)
- [`databricks.yml`](../databricks.yml)
- [`resources/jobs.yml`](../resources/jobs.yml)

## Step 2 — Replace the example app tools

Edit these files:

- [`src/databricks_mcp_agent_hello_world/app/tools.py`](../src/databricks_mcp_agent_hello_world/app/tools.py)
- [`src/databricks_mcp_agent_hello_world/app/registry.py`](../src/databricks_mcp_agent_hello_world/app/registry.py)

Populate `description`, `capability_tags`, `side_effect_level`, `data_domains`, and `example_uses` carefully.

Do not replace LLM-driven tool selection with manual Python-side filtering or deterministic routing. The runtime boundary and tool-selection model are described in [Architecture](./ARCHITECTURE.md).

## Step 3 — Replace the runtime task file

Edit [`examples/demo_run_task.json`](../examples/demo_run_task.json).

This file carries the per-run payload the sample app executes by default. The local demo flow and the default deployed Databricks job both point at this same file, so replace it here instead of creating a second deployment-only sample task.

If you intentionally want deployed behavior to use a different task contract later, change [`resources/jobs.yml`](../resources/jobs.yml) on purpose.

## Step 4 — Update prompts only if needed

Only edit [`src/databricks_mcp_agent_hello_world/prompts/agent_system_prompt.txt`](../src/databricks_mcp_agent_hello_world/prompts/agent_system_prompt.txt) if your new domain genuinely needs it.

## Step 5 — Replace eval scenarios

Edit [`evals/sample_scenarios.json`](../evals/sample_scenarios.json). You can point scenarios at the canonical sample task file with `task_input_file` instead of duplicating the full JSON payload inline.

Create scenarios that cover:

1. happy path
2. missing tool use
3. unexpected write-tool use
4. output completeness

## Step 6 — Rename deployment resources

Edit these files:

- [`databricks.yml`](../databricks.yml)
- [`resources/jobs.yml`](../resources/jobs.yml)
- [`workspace-config.example.yml`](../workspace-config.example.yml)
- [`src/databricks_mcp_agent_hello_world/config.py`](../src/databricks_mcp_agent_hello_world/config.py) only if you are making a true platform-level config change

When you extend config, keep `src/databricks_mcp_agent_hello_world/config.py` as the only place that decides config behavior. For canonical keys, deprecated aliases, stale-key warnings, and the current `sql:` note, follow the config-loading contract in [Architecture](./ARCHITECTURE.md).

## Step 7 — Verify the full workflow

Use this checklist:

1. run preflight locally
2. if you are validating Databricks persistence, run `databricks bundle run --target <target> init_storage_job`
3. discover tools locally
4. run the agent locally
5. run evals locally
6. deploy the bundle
7. run the Databricks job
8. inspect persisted artifacts

The operator commands and troubleshooting live in the [README](../README.md). The persistence contract and event model live in [Architecture](./ARCHITECTURE.md).

## Definition of done

Success means:

- example app assets fully replaced
- framework core unchanged except where the domain truly requires it
- LLM-driven tool selection preserved
- evals pass
- the Databricks job path succeeds end to end
