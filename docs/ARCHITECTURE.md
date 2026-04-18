# Architecture

[Back to README](../README.md)  
[Next: Convert the template into a real app](./CONVERT_TEMPLATE_TO_REAL_APP.md)

## Design goals

- single-agent architecture
- async non-interactive execution
- minimal framework complexity
- LLM-driven tool selection
- one canonical persistence contract across local and Databricks runtimes
- one authored package version source in `pyproject.toml`
- example app assets separated from reusable framework assets

## Version source of truth

The template authors the package version once in `pyproject.toml`.

Runtime code reads the installed package version from metadata instead of duplicating a hardcoded `__version__` literal, and Databricks bundle wheel references are kept in sync with `python scripts/sync_version_refs.py`.

That keeps the checked-in bundle YAML readable while avoiding manual version drift between package metadata, wheel artifact names, and tests.

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
  -> provider.call_tool(...)
  -> runtime emits execution events incrementally
  -> write_event_rows(...)
```

## Runtime tool selection

The runtime loop in [`src/databricks_mcp_agent_hello_world/runner/agent_runner.py`](../src/databricks_mcp_agent_hello_world/runner/agent_runner.py) exposes the full discovered tool inventory to the model for each run.

There is no compile step. There is no task-specific hard-coded allowlist. There is no deterministic prefilter layer. The model decides which tools to call, and the application only validates that a requested tool actually exists before executing it.

This matches the standard tool-calling pattern where the model is given tools and can decide whether to call them. The intended runtime model is provider-based discovery plus provider-based execution rather than split provider and executor routing.

## Provider model

There should be one canonical tool-provider resolution point in the runtime. `local_python` is the working runtime today. `managed_mcp` is retained as a near-term extension point and is intentionally present in the codebase, but it is not implemented yet.

That means:

- the provider advertises the discovered tool inventory
- the provider boundary is also the execution seam for tool calls
- unrelated modules should not branch separately on provider type

## Config loading contract

`src/databricks_mcp_agent_hello_world/config.py` is the single source of truth for runtime config validity.

- `tool_provider_type` and `databricks_config_profile` are the canonical YAML keys
- `provider_type` and `databricks_cli_profile` are accepted as deprecated aliases and produce warnings
- deprecated, stale, or unknown config keys do not fail config load by themselves
- `preflight` consumes the same config warning list instead of maintaining a second set of config rules

The commented `sql:` block in `workspace-config.example.yml` is documentation for a future extension path only. It is not part of the active runtime config surface today.

## Persistence model

The persisted source of truth is an append-only event log with one row per execution event. Summary objects such as `AgentRunRecord` still exist as runtime conveniences for CLI output and evals, but they are no longer the authored storage contract.

Storage bootstrap is split by runtime now. Local JSONL stays lazy and implicit, while remote Delta bootstrap is explicit and runs only through the Databricks bundle job.

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
- during bootstrap, the same schema is used to generate Delta DDL for missing table creation and expected schema comparison

This keeps the template aligned with two hard rules:

- one authored schema only
- no duplicated Spark `StructType` that can drift from the local contract

### Why bootstrap is split by execution context

The template keeps storage setup explicit where it matters, but removes ceremony where it does not:

- local developers should not need an init command just to create `./.local_state`
- Databricks users should initialize Delta storage inside Databricks, where Spark is actually present
- first workload runs should focus on doing work, not on choosing whether to create storage objects
- schema mismatches should be surfaced clearly instead of silently repaired

That is why local JSONL is created lazily during normal writes, while remote Delta provisioning happens through `init_storage_job`. `preflight` stays read-only, and runtime execution stays focused on event writing.

### Canonical event-log shape

Every persisted row belongs to the same event schema. A few top-level fields stay queryable in Delta SQL:

- `run_key`: the persisted run identifier
- `turn_index`: turn number for LLM and tool events, `null` for run-level events
- `event_index`: strictly increasing sequence number within the run
- `event_type`: event category such as `run_started`, `llm_request`, `tool_call`, `tool_result`, or `run_completed`
- `status`: stable status marker for success, failure, or tool execution state
- `tool_name`, `tool_call_id`, `model_name`, `inventory_hash`: queryable operational metadata
- `final_response_excerpt`, `error_message`: short convenience fields for quick scans
- `created_at`: ISO-8601 UTC timestamp string

Everything event-specific and potentially nested stays in `payload_json`.

`run_key + event_index` is the only supported event identity pair. The template does not persist `conversation_id`, and it intentionally does not persist a composite `event_id` because that can always be reconstructed later from those two fields.

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

Bootstrap behavior follows a clear split:

- local mode without Spark lets the normal JSONL writer create `storage.local_data_dir` lazily on first write
- the Databricks bootstrap job checks the configured `catalog.schema.table`, creates a missing schema automatically, creates a missing table automatically, and compares an existing table against the canonical schema exactly

The Databricks path is intentionally conservative. Catalogs must already exist, the job never prompts, and a mismatched table fails with a readable schema diff instead of dropping or recreating data automatically.

## Demo assets vs framework assets

- Framework assets: `src/databricks_mcp_agent_hello_world/runner/agent_runner.py`, `src/databricks_mcp_agent_hello_world/storage/write.py`, `src/databricks_mcp_agent_hello_world/storage/schema.py`, `src/databricks_mcp_agent_hello_world/storage/bootstrap.py`, `src/databricks_mcp_agent_hello_world/evals/harness.py`, `src/databricks_mcp_agent_hello_world/models.py`, `src/databricks_mcp_agent_hello_world/config.py`
- Example app assets: `src/databricks_mcp_agent_hello_world/app/tools.py`, `src/databricks_mcp_agent_hello_world/app/registry.py`, `examples/demo_run_task.json`, `evals/sample_scenarios.json`, `databricks.yml`, `workspace-config.example.yml`, `resources/jobs.yml`

## What downstream teams should customize

- `src/databricks_mcp_agent_hello_world/app/tools.py`
- `src/databricks_mcp_agent_hello_world/app/registry.py`
- `examples/demo_run_task.json`
- `evals/sample_scenarios.json`
- `databricks.yml`
- `workspace-config.example.yml`
- `resources/jobs.yml`
- `src/databricks_mcp_agent_hello_world/prompts/agent_system_prompt.txt` only if the domain genuinely needs it

## Advanced concepts

Precompiled tool-governance layers, manual tool allowlists such as `allowed_tools`, and policy-based tool-call blocking are intentionally out of scope for this template. They may be useful later for larger inventories, governance, or token optimization, but they are not implemented here.
