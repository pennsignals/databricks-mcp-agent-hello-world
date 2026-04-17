# Architecture

[Back to README](../README.md)  
[Next: Convert the template into a real app](./CONVERT_TEMPLATE_TO_REAL_APP.md)

## Design goals

- single-agent architecture
- async non-interactive execution
- minimal framework complexity
- LLM-driven tool selection
- one canonical persistence contract across local and Databricks runtimes
- demo assets separated from reusable framework assets

## End-to-end flow

```text
task file -> run-agent-task -> generic runner -> persisted event rows
```

Expanded flow:

```text
examples/demo_run_task.json
  -> AgentRunner.run(...)
  -> provider.list_tools(...)
  -> model receives the full discovered tool inventory
  -> generic runner loop
  -> runtime emits execution events incrementally
  -> ResultWriter.write_event_rows(...)
```

## Runtime tool selection

The runtime loop in [`src/databricks_mcp_agent_hello_world/runner/agent_runner.py`](../src/databricks_mcp_agent_hello_world/runner/agent_runner.py) exposes the full discovered tool inventory to the model for each run.

There is no compile step. There is no task-specific hard-coded allowlist. There is no deterministic prefilter layer. The model decides which tools to call, and the application only validates that a requested tool actually exists before executing it.

This matches the standard tool-calling pattern where the model is given tools and can decide whether to call them.

## Persistence model

The persisted source of truth is an append-only event log with one row per execution event. Summary objects such as `AgentRunRecord` still exist as runtime conveniences for CLI output and evals, but they are no longer the authored storage contract.

Storage bootstrap is also explicit now. The template expects operators to run `init-storage` before the first real workload that needs durable persistence, instead of letting normal workload execution create schemas or tables implicitly.

### Why event rows replaced run/output summary rows

The old summary-row model was easy to start with, but it was a poor template pattern:

- nested runtime payloads were fragile under Spark schema inference
- persistence mostly happened at run completion instead of incrementally
- partial runs and failures were hard to analyze cleanly
- SQL analysis in Delta was awkward because the shape was oriented around blobs, not events

The event-log model fixes that by persisting each significant runtime step as its own flat row.

### Why PyArrow is the single schema source

The template defines one authored `pyarrow.Schema` and uses it in both runtimes:

- locally, rows are validated before appending to `agent_events.jsonl`
- on Databricks, rows are validated before Spark creates a DataFrame from the Arrow table and appends to Delta
- during bootstrap, the same schema is used to construct an empty Arrow table so Spark can create the Delta table from the canonical shape

This keeps the template aligned with two hard rules:

- one authored schema only
- no duplicated Spark `StructType` that can drift from the local contract

### Why bootstrap is explicit instead of lazy

The template treats storage provisioning as operator intent, not runtime side effect:

- local developers should be able to prepare storage without needing Spark
- Databricks users should be able to inspect and approve namespace-creating or destructive actions
- first workload runs should focus on doing work, not deciding whether to create infrastructure
- schema mismatches should be surfaced clearly instead of silently repaired

That is why `init-storage` exists separately from `preflight` and `run-agent-task`. `preflight` stays read-only, and runtime execution stays focused on event writing.

### Canonical event-log shape

Every persisted row belongs to the same event schema. A few top-level fields stay queryable in Delta SQL:

- `conversation_id`: logical conversation or workflow identifier
- `run_key`: idempotency and future resume key
- `turn_index`: turn number for LLM and tool events, `null` for run-level events
- `event_index`: strictly increasing sequence number within the run
- `event_type`: event category such as `run_started`, `llm_request`, `tool_call`, `tool_result`, or `run_completed`
- `status`: stable status marker for success, failure, or tool execution state
- `tool_name`, `tool_call_id`, `model_name`, `inventory_hash`: queryable operational metadata
- `final_response_excerpt`, `error_message`: short convenience fields for quick scans
- `created_at`: ISO-8601 UTC timestamp string

Everything event-specific and potentially nested stays in `payload_json`.

### Why `payload_json` exists

`payload_json` stores the raw event detail as a JSON string. That includes things like:

- full LLM request payloads
- full LLM responses
- tool arguments and tool results
- terminal success or failure payloads

This keeps the schema stable and flat while still preserving fidelity for later debugging, SQL analysis, and future resumability work.

### Local and Databricks parity

Both backends use the same logical row shape:

- local development appends validated rows to `.local_state/agent_events.jsonl`
- Databricks execution appends validated rows to `storage.agent_events_table`

Because events are written incrementally, partial runs and failures still leave behind useful persisted history.

Bootstrap behavior also follows the same split:

- local mode without Spark creates `storage.local_data_dir` and stops there
- Databricks or Spark mode checks the configured `catalog.schema.table`, creates a missing schema only after confirmation, creates a missing table automatically once the schema exists, and compares an existing table against the canonical schema exactly

The Databricks path is intentionally conservative. Catalogs must already exist, prompts default to `No`, and a mismatched table is only dropped and recreated after confirmation or when `--yes` is supplied for automation.

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

Precompiled tool-governance layers, manual tool allowlists such as `allowed_tools`, and policy-based tool-call blocking are intentionally out of scope for this template. They may be useful later for larger inventories, governance, or token optimization, but they are not implemented here.
