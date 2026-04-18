# Convert the template into a real app

[Back to README](../README.md)  
[Reference: Architecture](./ARCHITECTURE.md)

## Before you start

Tool selection stays LLM-driven in this template. Customize the example app assets first instead of forking the framework core.

The persistence layer is also intentional now: the template uses one canonical PyArrow-backed event-log schema shared by local JSONL and Databricks Delta. Downstream teams should extend that event schema carefully instead of reintroducing separate local and Spark persistence contracts.

Storage provisioning is explicit too, but only where it adds value. Local JSONL storage creates itself lazily on first write, while Databricks Delta storage is initialized by the dedicated `init_storage_job`. If your production fork needs stronger controls, replace that job with migrations or infrastructure-as-code rather than moving provisioning back into normal runtime execution.

`managed_mcp` is retained as a near-term extension point and is intentionally present in the codebase, but it is not implemented yet. Build on the working `local_python` path unless you are intentionally taking on that implementation work.

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

Do not replace LLM-driven tool selection with manual Python-side filtering or deterministic routing.

## Step 3 — Replace the runtime task file

Edit [`examples/demo_run_task.json`](../examples/demo_run_task.json).

This file carries the per-run payload the job will execute.

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

When you extend config, keep `src/databricks_mcp_agent_hello_world/config.py` as the only place that decides:

- which keys are canonical
- which aliases are deprecated
- which stale or unknown keys should warn
- which fields are truly required at runtime

The current canonical keys include `tool_provider_type` and `databricks_config_profile`. The commented `sql:` block in the example config is a future/example note only and is not part of the active runtime surface.

## Persistence extension guidance

Keep the event-log architecture intact unless your domain truly needs a different storage model.

### Make `run_key` deterministic for resumable workflows

In the demo, `run_key` can match the run UUID. In a real app, make it deterministic when you need idempotency or resumability. Good candidates include:

- a workflow request ID
- a stable document or ticket ID plus processing stage
- a composite business key that identifies the intended work item

That lets future retries append or reconcile against a stable logical execution key instead of a random runtime-generated ID.

### Promote fields out of `payload_json` only when they become stable query keys

The default pattern is:

- keep the schema flat
- keep raw event detail in `payload_json`
- promote only the small set of fields that will be filtered, grouped, or joined often

Good reasons to promote a field:

- you query it frequently in Delta SQL
- you need it for retention or lineage policies
- it has become a durable part of the app contract

Avoid promoting one-off nested payload details too early. That is how schema sprawl starts.

### Add new `event_type` values by extending the single canonical schema contract

The right extension point is usually:

1. keep the same event table
2. add a new `event_type`
3. store event-specific detail in `payload_json`
4. promote new top-level columns only if they become broadly useful across runs

That preserves one canonical schema while letting the runtime evolve.

### Keep the template bootstrap path simple and safe

The template's bootstrap flow is intentionally minimal:

- local mode creates `storage.local_data_dir` lazily and does not create an empty JSONL file eagerly
- the Databricks `init_storage_job` creates a missing schema automatically
- the Databricks `init_storage_job` creates a missing table automatically
- a mismatched table fails with a schema diff and no mutation

That makes the default template automation-friendly without turning the runtime itself into a provisioning tool.

If your production fork has stricter controls, the next step is usually:

- provision catalogs and schemas with platform IaC
- manage table evolution with formal migrations
- keep runtime writes and bootstrap checks aligned to the same canonical Arrow schema

Avoid reintroducing a second authored Spark schema just to support provisioning. The point of the current design is that local validation, Databricks writes, and bootstrap all derive from one Arrow contract.

### Plan for redaction and truncation when payloads become sensitive or large

`payload_json` is intentionally high-fidelity, which is useful but comes with governance implications. When you fork this template for production, decide:

- which raw LLM and tool payloads should be redacted before persistence
- whether any payload classes should be dropped entirely
- whether excerpts or hashes are enough for some events
- how long raw event rows should be retained

If payload size grows quickly, add targeted truncation or redaction rules around event serialization rather than fragmenting the storage schema.

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

Inspect the single event store rather than looking for separate run and output tables. The intended storage artifacts are:

- local: `.local_state/agent_events.jsonl`
- Databricks: `storage.agent_events_table`

If you are validating a fresh Databricks environment, include `init_storage_job` before the first remote workload run so storage readiness is explicit and repeatable. Local JSONL does not need a bootstrap command.

## Definition of done

Success means:

- example app assets fully replaced
- framework core unchanged except where the domain truly requires it
- LLM-driven tool selection preserved
- single-schema event-log persistence preserved or intentionally extended
- evals pass
- the Databricks job path succeeds end to end
