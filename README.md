# databricks-mcp-agent-hello-world

A starter template for batch/non-interactive LLM agents that run as Databricks Jobs and call tools at runtime.

Use this repo when you want a small Databricks-only agent template with:

- local Python tools for app-specific logic
- optional Databricks MCP tools for governed/shared Databricks-hosted tools
- Databricks SDK authentication shared by LLM, MCP, and preflight code
- local JSONL event persistence by default, with optional Spark table persistence

For runtime design, see [Architecture](docs/ARCHITECTURE.md). For downstream edits, see [Convert the template into a real app](docs/CONVERT_TEMPLATE_TO_REAL_APP.md).

## Install/Setup

Prerequisites:

- Python 3.12 or newer
- Databricks CLI installed
- access to a Databricks workspace
- a Databricks model serving endpoint for `llm_endpoint_name`

From the repo root:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .[dev]
python3.12 -m pre_commit install
cp workspace-config.example.yml workspace-config.yml
```

Authenticate to Databricks with the CLI:

```bash
databricks auth login --host https://<your-workspace-host>
```

## Configure

Edit `workspace-config.yml`.

At minimum, set:

```yaml
llm_endpoint_name: your-serving-endpoint-name
databricks_config_profile: DEFAULT
```

Do not commit real workspace hosts, endpoint names, table names, MCP URLs, or credentials in public repos.

The agent can use tools from multiple enabled sources. Local Python tools are for app-specific logic. Databricks MCP tools are for governed/shared Databricks-hosted tools. Tool names must be unique across enabled sources.

To keep the first run local-tool only, leave:

```yaml
tools:
  local_python:
    enabled: true
  databricks_mcp:
    enabled: false
```

Databricks authentication is handled by the Databricks SDK. The template passes `databricks_config_profile` and/or `workspace_host` through one shared client helper used by LLM, MCP, and preflight code.

`agent_system_prompt_path` is optional. If omitted, the built-in default prompt is used. If set, the path must exist and contain non-empty text.

Storage routing has one rule:

- if `storage.agent_events_table` is unset, events are written to local JSONL under `storage.local_data_dir`
- if `storage.agent_events_table` is set, an active Spark session is required and events are written to that table
- the template never silently falls back from table persistence to local persistence

## Run Preflight

```bash
preflight --config-path workspace-config.yml
```

Preflight loads the same config path used by the runtime, checks strict config keys, constructs the shared Databricks client settings, verifies enabled tool sources can be created, confirms at least one tool is discoverable, and reports the configured storage mode.

Preflight does not verify that the serving endpoint exists, check endpoint permissions, call the LLM endpoint, run an agent task, or prove a deployed Databricks job will succeed. For an end-to-end live check, run the demo task or sample evals.

## Discover Tools

```bash
discover-tools --config-path workspace-config.yml
```

For the built-in example app, discovery should show:

- `lookup_customer`
- `create_support_ticket`

The default local inventory intentionally includes a relevant read tool and an irrelevant write-like tool. The demo task should use `lookup_customer` and should not use `create_support_ticket`; this shows that the model sees the full inventory but should select only tools relevant to the task.

## Run The Demo Task

```bash
run-agent-task \
  --config-path workspace-config.yml \
  --task-input-file examples/demo_run_task.json
```

A successful run discovers tools, lets the model choose which tool to call, returns a final answer from tool output, and writes event records.

Local JSONL state is created lazily on first write under `./.local_state`.

For machine-readable output:

```bash
run-agent-task \
  --config-path workspace-config.yml \
  --task-input-file examples/demo_run_task.json \
  --output json
```

## Run Tests

Standard repo validation:

```bash
python3.12 -m pre_commit run --all-files --show-diff-on-failure
```

The standard pre-commit validation flow also lints Markdown documentation.

Unit tests:

```bash
python -m nox -s unit
```

Contract tests:

```bash
python -m nox -s contract
```

All tests:

```bash
python -m nox -s tests
```

Evals are a lightweight smoke-test harness that verifies run status, expected tool use, and required output text.

Supported scenario assertion fields are:

- `expected_status`
- `required_executed_tools`
- `forbidden_executed_tools`
- `required_output_substrings`

Eval summary reports are written locally under `storage.local_data_dir`; agent execution events still follow the configured storage route.

Run the sample evals only when Databricks auth and the configured LLM endpoint are ready:

```bash
run-evals \
  --config-path workspace-config.yml \
  --scenario-file evals/sample_scenarios.json
```

## Customize The Template

For most downstream apps, replace:

- [examples/demo_run_task.json](examples/demo_run_task.json)
- [src/databricks_mcp_agent_hello_world/app/tools.py](src/databricks_mcp_agent_hello_world/app/tools.py)
- [src/databricks_mcp_agent_hello_world/app/registry.py](src/databricks_mcp_agent_hello_world/app/registry.py)
- [evals/sample_scenarios.json](evals/sample_scenarios.json)
- [databricks.yml](databricks.yml)
- [resources/jobs.yml](resources/jobs.yml)

Keep the default runtime contract simple: discover enabled tool sources, expose the full discovered tool inventory to the model, execute the tool the model requests, and persist events through the configured storage route.

See [Convert the template into a real app](docs/CONVERT_TEMPLATE_TO_REAL_APP.md) for the practical checklist.

## Deploy To Databricks

After the local demo works, update [databricks.yml](databricks.yml) and [resources/jobs.yml](resources/jobs.yml) for your workspace, then validate and deploy with Databricks Asset Bundles.

For tag-driven GitHub Actions deployment, see [CD deployment](docs/CD_DEPLOYMENT.md).

Keep deployment-specific workspace hosts, endpoints, table names, and secrets out of public committed config.

## Output Locations

Local events are written to:

```text
.local_state/agent_events.jsonl
```

Spark-backed events are written to:

```text
storage.agent_events_table
```

Persisted event payloads can include task inputs, prompt messages, tool arguments, tool results, model responses, errors, and final outputs. Before running with real customer, employee, regulated, proprietary, or otherwise sensitive data, review whether those payloads are appropriate for your access controls and retention requirements.
