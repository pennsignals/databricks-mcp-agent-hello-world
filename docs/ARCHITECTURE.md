# Architecture

[Back to README](../README.md)
[Next: Convert the template into a real app](./CONVERT_TEMPLATE_TO_REAL_APP.md)

Use this document for runtime, provider, config, and storage design. For setup, first run, and troubleshooting, go back to the [README](../README.md). For downstream edits, use [Convert the template into a real app](./CONVERT_TEMPLATE_TO_REAL_APP.md).

## Design goals

- single-agent architecture
- async non-interactive execution
- minimal framework complexity
- LLM-driven tool selection
- one canonical persistence contract across local and Databricks runtimes
- one SCM-derived package version source
- example app assets separated from reusable framework assets

## Version source of truth

The template derives package versions from Git state with `hatch-vcs`.

Runtime code reads the installed package version from metadata instead of duplicating a hardcoded `__version__` literal. Bundle jobs consume the built wheel from `../dist/*.whl`, so deployment follows the actual artifact that was built rather than a separately synchronized version string.

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
  -> runtime_tool.execute(...)
  -> runtime emits execution events incrementally
  -> write_event_rows(...)
```

The canonical sample task lives at [`examples/demo_run_task.json`](../examples/demo_run_task.json). The default local CLI flow and the default deployed Databricks job both point at that same authored file.

## Runtime tool selection

The runtime loop in [`src/databricks_mcp_agent_hello_world/runner/agent_runner.py`](../src/databricks_mcp_agent_hello_world/runner/agent_runner.py) exposes the full discovered tool inventory to the model for each run.

There is no compile step. There is no task-specific hard-coded allowlist. There is no deterministic prefilter layer. The model decides which tools to call, and the application only validates that a requested tool actually exists before executing it.

This matches the standard tool-calling pattern where the model is given tools and can decide whether to call them. The intended runtime model is provider-based discovery of `RuntimeTool` objects, followed by direct execution of the selected tool's `execute` callable.

## Provider model

There should be one canonical tool-provider resolution point in the runtime. `local_python` exposes the built-in repo-local Python tools. `databricks_mcp` uses Databricks' `McpServerToolkit` to discover tools from one configured Databricks MCP server at runtime. When multiple sources are enabled, a small composite provider combines them and fails fast if two sources expose the same tool name.

That means:

- the provider advertises the discovered `RuntimeTool` inventory
- each `RuntimeTool` contains the model-visible function spec and execution callable
- unrelated modules should not branch separately on provider type

The internal runtime tool shape is intentionally small:

```python
RuntimeTool(
    name="tool_name",
    spec={...},      # Databricks/OpenAI-compatible function tool spec
    execute=fn,      # called with parsed model arguments
    source=ToolSource(type="local_python" | "databricks_mcp", id="..."),
)
```

Tool source metadata is for logging and discovery output only. Fields that do not affect model-visible specs, execution, config, tests, or traceability are kept out of the runtime model.

The LLM sees plain global tool names. Source labels such as `local_python` and `databricks_mcp` are retained only for traces, debugging, and discovery output.

## Config loading contract

`src/databricks_mcp_agent_hello_world/config.py` is the single source of truth for runtime config validity.

- `tools` is the canonical tool-source config
- `databricks_config_profile` and `workspace_host` are optional Databricks auth settings
- `tools.local_python.enabled` defaults to `true`
- `tools.databricks_mcp.enabled` defaults to `false`
- enabled Databricks MCP requires `tools.databricks_mcp.server.name` and `tools.databricks_mcp.server.url`
- at least one tool source must be enabled
- unknown top-level and nested YAML keys fail config loading with a clear `ValueError`
- `preflight` consumes the same strict config validation path instead of maintaining a second set of config rules

`workspace-config.example.yml` only includes supported config keys. Downstream apps should add new keys only after extending the strict config-loading contract.

## Persistence model

The persisted source of truth is an append-only event log with one row per execution event. Summary objects such as `AgentRunRecord` still exist as runtime conveniences for CLI output and evals, but they are no longer the authored storage contract.

Storage bootstrap is split by runtime:

- local JSONL is created lazily on first write
- remote Delta bootstrap is explicit and runs through `init_storage_job`

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

### Persisted event payload sensitivity

`payload_json` is intentionally rich so local and Databricks runs can be debugged after the fact. It should be treated as application data.

Depending on the task and tools, persisted event payloads may include:

- the original task payload
- system and user prompt content
- LLM request messages
- model responses
- tool-call names and arguments
- tool-result content
- exception messages
- final response text

The template does not apply application-level redaction, truncation, classification, encryption, or filtering to these fields before persistence. Downstream apps that handle sensitive data should decide whether to:

- restrict access to the local JSONL directory and Delta event table
- point `storage.agent_events_table` at an appropriately protected schema
- reduce what their tools return
- avoid placing secrets in task payloads or prompts
- add app-specific redaction or truncation before persistence
- define retention and cleanup rules for event data

This is intentionally a downstream application decision. The MVP template keeps persistence simple and observable by default.

### Local and Databricks parity

Both backends use the same logical row shape:

- local development appends validated rows to `.local_state/agent_events.jsonl`
- Databricks execution appends validated rows to `storage.agent_events_table`

Because events are written incrementally, partial runs and failures still leave behind useful persisted history.

The Databricks path is intentionally conservative. Catalogs must already exist, the job never prompts, and a mismatched table fails with a readable schema diff instead of dropping or recreating data automatically.

## Demo assets vs framework assets

- Framework assets: `src/databricks_mcp_agent_hello_world/runner/agent_runner.py`, `src/databricks_mcp_agent_hello_world/storage/write.py`, `src/databricks_mcp_agent_hello_world/storage/schema.py`, `src/databricks_mcp_agent_hello_world/storage/bootstrap.py`, `src/databricks_mcp_agent_hello_world/evals/harness.py`, `src/databricks_mcp_agent_hello_world/models.py`, `src/databricks_mcp_agent_hello_world/config.py`
- Example app assets: `src/databricks_mcp_agent_hello_world/app/tools.py`, `src/databricks_mcp_agent_hello_world/app/registry.py`, `examples/demo_run_task.json`, `evals/sample_scenarios.json`, `databricks.yml`, `workspace-config.example.yml`, `resources/jobs.yml`

## Customization boundary

Downstream teams usually replace the example app assets and keep the framework core intact. Use [Convert the template into a real app](./CONVERT_TEMPLATE_TO_REAL_APP.md) for the actual edit sequence and file-by-file customization checklist.

## Advanced concepts

Precompiled tool-governance layers, manual tool allowlists such as `allowed_tools`, and policy-based tool-call blocking are intentionally out of scope for this template. They may be useful later for larger inventories, governance, or token optimization, but they are not implemented here.
