# databricks-mcp-agent-hello-world

A lightweight starter template for building **non-interactive, tool-using LLM agents that run as Databricks Jobs**.

This template is intentionally:

- **Job-first**: package the project as a Python wheel and run it as a Databricks Job
- **local-first**: develop and validate from your laptop before deploying
- **simple by default**: keep the runtime small and easy to extend

This repo is for **autonomous batch-style agent workflows**, not chat apps, Databricks Apps, or long-running interactive services.

For the current MVP, **`local_python` is the only working tool runtime**. `managed_mcp` is retained as a near-term extension point and is intentionally present in the codebase, but it is not implemented yet.

On a successful first pass, you should be able to authenticate locally to Databricks, configure a Databricks-hosted LLM endpoint, discover the built-in example app tools, run the example app locally, verify that the model can choose and call tools at runtime, and deploy the same workflow as a Python wheel Job.

See the deeper docs when you are ready to customize the template:

- [Architecture](docs/ARCHITECTURE.md)
- [Convert the template into a real app](docs/CONVERT_TEMPLATE_TO_REAL_APP.md)

## How it works

The runtime flow is intentionally small:

1. load config from `workspace-config.yml`
2. discover tools from the active provider
3. run the real task with the full discovered tool inventory exposed
4. persist an append-only event log locally or to Delta

Tool selection is **LLM-driven**. The model receives the discovered tool inventory and decides what to call at runtime. For the provider boundary and tool-selection rules, see [Architecture](docs/ARCHITECTURE.md).

For the built-in example app, the current inventory contains **five** tools:

- `get_user_profile`
- `search_onboarding_docs`
- `get_workspace_setting`
- `list_recent_job_runs`
- `create_support_ticket`

The canonical sample task in [`examples/demo_run_task.json`](examples/demo_run_task.json) is a **read-only onboarding brief**. The model is expected to choose the relevant tools for the task, and the template does not pre-filter the inventory before runtime. The sample app uses that same file by default both locally and in the deployed Databricks job.

## Prerequisites

Before you start, make sure you have:

- **Python 3.12 or newer**
- the **Databricks CLI** installed
- a Databricks workspace you can authenticate to locally
- a **Databricks model serving endpoint** to use as `llm_endpoint_name`

The serving endpoint should support the **function-calling / tool-calling pattern** this template uses.

Deployment-specific requirements are covered later in [Deploying to Databricks](#deploying-to-databricks).

## First-time setup

From the repo root:

The template supports **Python 3.12 and newer**. **Python 3.11 is no longer supported** so the wheel metadata, local tooling, CI, and CD all align with current Databricks serverless and modern Databricks runtime Python versions.

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e .[dev]
python -m pre_commit install
cp workspace-config.example.yml workspace-config.yml
cp .env.example .env
```

`pre-commit` is the canonical repo-wide validation entrypoint in this repository. Install the git hooks once on your workstation, let them run automatically on commit, and use the full-repo command below when you want to validate everything manually.

## Required edits before your first run

For the smoothest first pass, start with the local-only setup below and leave deployment-specific changes for the later Databricks section.

### Local first-run edits

### 1) Set your local CLI profile in `.env`

```dotenv
DATABRICKS_CONFIG_PROFILE=DEFAULT
```

If you use a different profile name, put that value here instead.
`DATABRICKS_CONFIG_PROFILE` is the canonical runtime setting for selecting your
Databricks CLI profile.

### 2) Set the main runtime config in `workspace-config.yml`

At minimum, update these fields:

```yaml
tool_provider_type: local_python
llm_endpoint_name: <your-serving-endpoint-name>
```

You can also override `llm_endpoint_name` from `.env` with `LLM_ENDPOINT_NAME`, but keeping the main value in `workspace-config.yml` is the clearest beginner path.

### 3) Leave storage on the local default for your first pass

The example config ships with one event-store target and one local fallback directory:

```yaml
storage:
  agent_events_table: main.agent_demo.agent_events
  local_data_dir: ./.local_state
```

For your first local run, you usually do not need to change either value. When Spark is unavailable, the template automatically falls back to local JSONL under `./.local_state`.

### 4) Ignore the commented SQL example for the demo

The commented `sql:` block in `workspace-config.example.yml` is a future/example section only. It is **not used by the current runtime**.

## Quickstart: first successful local run

### Step 1: authenticate to Databricks

Use **Databricks CLI profile auth** for the supported beginner path.

```bash
databricks auth login --host https://<your-workspace-host>
```

If you want to use a non-default profile:

```bash
databricks auth login --host https://<your-workspace-host> --profile DEV
```

Then set the same profile in `.env`:

```dotenv
DATABRICKS_CONFIG_PROFILE=DEV
```

You can verify your saved profiles with:

```bash
databricks auth profiles
```

### Step 2: run preflight

```bash
preflight --config-path workspace-config.yml
```

This checks that:

- `workspace-config.yml` and optional `.env` load through the shared runtime config path
- deprecated or unused config keys are surfaced as warnings instead of load failures
- the Databricks CLI profile resolves
- the Databricks client initializes
- `llm_endpoint_name` is present
- the tool provider can be created
- the tool registry is non-empty
- persistence is configured for the active runtime

If `workspace-config.yml` or `.env` still contains deprecated or stale keys such as `provider_type`, `databricks_cli_profile`, `auth_mode`, or `local_tool_backend_mode`, config loading still succeeds and preflight reports warnings so you can clean them up without blocking the run.

When Spark is unavailable locally, `preflight` reports that local JSONL fallback would be used. When Spark is available but `storage.agent_events_table` has not been initialized yet, `preflight` fails intentionally and the required next step is `init_storage_job`.

### Step 3: discover tools

```bash
discover-tools --config-path workspace-config.yml
```

For the built-in example app, you should see **5 tools**. The discovery output may also show metadata such as side-effect level, tags, and domains for each tool.

### Step 4: run the demo task

Use the runtime task file:

```bash
run-agent-task \
  --config-path workspace-config.yml \
  --task-input-file examples/demo_run_task.json
```

A successful run shows that the project can:

- discover the runtime tool inventory
- expose the discovered tools to the model
- let the model choose and call the needed tools
- generate a final answer grounded in tool results
- persist incremental execution events

If you want machine-readable output:

```bash
run-agent-task \
  --config-path workspace-config.yml \
  --task-input-file examples/demo_run_task.json \
  --output json
```

Local JSONL state is created lazily on the first write under `./.local_state`, so no separate local bootstrap command is required.

### Step 5: validate locally

Standard repo validation:

```bash
python3.12 -m pre_commit run --all-files --show-diff-on-failure
```

This is the canonical full validation flow for local development and CI. It runs the repository hygiene hooks plus the shared `nox` validation flow for Ruff linting, Ruff format validation, `pytest` with coverage, and wheel build verification.

The first full run may take noticeably longer because `pre-commit` and `nox` may need to create their environments. Subsequent runs are normally much faster because those environments are reused.

Targeted unit tests only:

```bash
pytest
```

Coverage is configured centrally in `pyproject.toml`, so a normal `pytest` measures only the package under `src/databricks_mcp_agent_hello_world`, prints missing lines, writes `coverage.xml`, and fails if package coverage drops below 100%. Use `pytest` when you intentionally want the fastest test-focused feedback loop rather than the full repo validation flow.

Live integration evals against the configured Databricks endpoint:

```bash
run-evals \
  --config-path workspace-config.yml \
  --scenario-file evals/sample_scenarios.json
```

Live evals require valid Databricks auth and may consume tokens, so use them after the local demo flow is already working.

### Databricks-hosted development

If you are developing from fresh Databricks compute instead of a local workstation, the recommended path is notebook-based setup with `%pip install`, because that is the lowest-friction option for serverless and other ephemeral environments.

Open the repo from a Databricks-hosted checkout, or otherwise make sure you are running from the repository root before installing dependencies or running validation.

Install the repo's development dependencies into the active notebook environment:

```python
%pip install -e ".[dev]"
```

Then run the canonical repo-wide validation flow with that same Python interpreter:

```python
import subprocess
import sys

subprocess.run(
    [sys.executable, "-m", "pre_commit", "run", "--all-files", "--show-diff-on-failure"],
    check=True,
)
```

`python3.12 -m pre_commit install` is primarily for workstation-based git-hook development. In Databricks notebook workflows, the standard path is to run `pre-commit` manually with `run --all-files`.

If you have a browser-based terminal or workspace shell available, you can optionally use the same commands as local development after installing `.[dev]`. Cluster-level preinstallation of dev tooling can help on long-lived dedicated compute, but it is an optimization rather than the default recommendation.

### Success checklist

A healthy first pass looks like this:

- `preflight` passes
- `discover-tools` shows **5** tools
- `run-agent-task` completes successfully
- local artifacts appear under `./.local_state`

## Deploying to Databricks

Do this only after the local flow is green.

Local deployment remains supported for first validation and debugging. For shared, repeatable `dev` deployments, GitHub Actions CD with OIDC is the recommended path. See [CD deployment with GitHub Actions and OIDC](docs/CD_DEPLOYMENT.md).

The bundle targets intentionally separate personal testing from shared automation:

- `local`: personal developer deployment, run by an individual user, with bundle files under `~/.bundle/${bundle.name}/${bundle.target}`
- `dev`: shared GitHub Actions CD deployment, run by a service principal only, with bundle files under `/Workspace/Users/${workspace.current_user.userName}/.bundle/${bundle.name}/${bundle.target}`
- `prod`: future production deployment, run by a service principal only, with bundle files under `/Workspace/Users/${workspace.current_user.userName}/.bundle/${bundle.name}/${bundle.target}`

Local developers should use `local`. GitHub Actions uses `dev`. The `prod` target exists as a template placeholder for future production automation. Local developers should not deploy `dev` or `prod`.

No workspace hosts are stored in `databricks.yml`. Local authentication comes from your Databricks CLI auth configuration, such as a profile or `DATABRICKS_HOST`. GitHub CD gets `DATABRICKS_HOST` from the `dev` GitHub environment and authenticates with OIDC.

For GitHub CD, `${workspace.current_user.userName}` resolves to the authenticated Databricks service principal, so shared `dev` bundle files and deployment state are scoped to that deployer identity instead of a workspace-wide shared folder.

The `dev` and `prod` targets intentionally grant the workspace `users` group `CAN_VIEW` on bundle-managed resources so normal Databricks users can observe shared jobs and runs. That grant does not provide deployment control or job management access; do not grant `users` `CAN_MANAGE` unless your workspace intentionally wants all users to manage bundle-managed resources.

GitHub CD suppresses Databricks job stdout and stderr in Actions logs because public repository workflow logs can be visible to public readers. Downstream apps should avoid printing secrets, credentials, sensitive prompts, sensitive model responses, row-level data, or private config to stdout and stderr. Databricks-side logs may still retain output according to workspace and job permissions; this only suppresses GitHub Actions log output.

Before you deploy, make these additional Databricks-specific updates:

### 1) Point `storage.agent_events_table` at a writable Delta target

In `workspace-config.yml`, change `storage.agent_events_table` to a **catalog and schema you can create and write to** for deployed Databricks runs.

### 2) Confirm your deployment permissions and compute model

You need permission to deploy bundles and run jobs in your target workspace.

The default deployed job definition in this repo uses **serverless job environments**. If your workspace does not support that pattern, edit [`resources/jobs.yml`](resources/jobs.yml) before deploying.

This repo deploys **two Python wheel jobs**:

- `init_storage_job`
- `run_agent_task_job`

### Deploy commands

```bash
databricks bundle validate --target local

databricks bundle deploy --target local

databricks bundle run --target local init_storage_job

databricks bundle run --target local run_agent_task_job
```

Run `init_storage_job` only after the bundle has been deployed. It initializes the remote Delta table inside Databricks before the first remote workload run.

Both deployed jobs read the workspace copy of `workspace-config.yml` from `${workspace.file_path}/workspace-config.yml`, so keep that deployed config aligned with the local config you validated.

The default deployed sample job also reads the workspace copy of [`examples/demo_run_task.json`](examples/demo_run_task.json), so the sample app runs the same canonical task locally and when deployed.

The deployed wheel tasks intentionally use **separate Databricks job entry points** from the local CLI commands:

- local development keeps using `run-agent-task ...`
- remote storage bootstrap uses the package `run_init_storage` wrapper
- the bundled Databricks job uses the package `run_agent_task` wrapper
- `run_init_storage` loads settings, calls the shared bootstrap logic, and exits non-zero on mismatch
- the runtime job passes `--config-path`, `--task-input-file`, and `--output` through `python_wheel_task.parameters`, and the wrapper forwards `sys.argv[1:]` into the existing `argparse` command handler

The deployed jobs install the **built wheel artifact** through job environment dependencies such as `../dist/databricks_mcp_agent_hello_world-*.whl`. That keeps serverless wheel jobs compatible with Databricks job environments and points the bundle at the artifact that was actually built.

Package versions are derived from Git state with `hatch-vcs`. Release tags like `v1.2.3` build `1.2.3`, tagged post-release commits build SCM-derived development versions, and no-tag repos bootstrap through `scripts/build_wheel.py` as `0.1.0.dev...+g...` builds so local/manual deploys stay visibly non-release and traceable.

When you change packaged job behavior, rebuild and redeploy the wheel instead of editing a static `project.version`. Serverless environments can reuse cached custom-package environments, so the SCM-derived wheel version is what tells Databricks to install the new artifact content.

If you want the deployed job to use a different task contract later, update [`resources/jobs.yml`](resources/jobs.yml) on purpose. The starter keeps the default deployed path pointed at the same canonical sample task file used locally.

This starter is intentionally **not scheduled by default**. Get the on-demand flow working first, then add a schedule in a downstream project.

The template includes a `prod` target for future use, but prod CD automation is not implemented yet.

## Where outputs go

### Local development

When Spark is unavailable, the project falls back to local persistence under:

```text
.local_state/
└── agent_events.jsonl
```

Each line is one execution event.
The directory and JSONL file appear lazily on the first write.

### Databricks runs

When Spark is available, the project uses the Delta event store configured in `workspace-config.yml`:

- `storage.agent_events_table`

Before you rely on deployed runs, make sure `storage.agent_events_table` points to a writable location, then run `databricks bundle run --target local init_storage_job` for local deployment or let GitHub CD run `databricks bundle run --target dev init_storage_job` for shared dev deployment.

## Persistence model

The template uses one append-only event store shared across local JSONL and Databricks Delta. Operator-facing paths are:

- local: `.local_state/agent_events.jsonl`
- remote: `storage.agent_events_table`

For the event schema, `run_key + event_index` identity model, and `payload_json` rationale, see [Architecture](docs/ARCHITECTURE.md).

## What you should customize vs keep

For the full downstream customization guide, use [Convert the template into a real app](docs/CONVERT_TEMPLATE_TO_REAL_APP.md).

Replace these first in a downstream project:

- [`examples/demo_run_task.json`](examples/demo_run_task.json)
- [`src/databricks_mcp_agent_hello_world/app/tools.py`](src/databricks_mcp_agent_hello_world/app/tools.py)
- [`src/databricks_mcp_agent_hello_world/app/registry.py`](src/databricks_mcp_agent_hello_world/app/registry.py)
- [`evals/sample_scenarios.json`](evals/sample_scenarios.json)
- [`databricks.yml`](databricks.yml)
- [`resources/jobs.yml`](resources/jobs.yml)

Usually keep these framework files intact unless you are intentionally changing the core runtime:

- [`src/databricks_mcp_agent_hello_world/runner/agent_runner.py`](src/databricks_mcp_agent_hello_world/runner/agent_runner.py)
- [`src/databricks_mcp_agent_hello_world/storage/write.py`](src/databricks_mcp_agent_hello_world/storage/write.py)
- [`src/databricks_mcp_agent_hello_world/storage/schema.py`](src/databricks_mcp_agent_hello_world/storage/schema.py)
- [`src/databricks_mcp_agent_hello_world/evals/harness.py`](src/databricks_mcp_agent_hello_world/evals/harness.py)
- [`src/databricks_mcp_agent_hello_world/models.py`](src/databricks_mcp_agent_hello_world/models.py)
- [`src/databricks_mcp_agent_hello_world/config.py`](src/databricks_mcp_agent_hello_world/config.py)

## Troubleshooting

### `databricks bundle validate` uses the wrong workspace

The bundle does not store workspace hosts in `databricks.yml`. Local validation uses your Databricks CLI auth configuration, such as a profile or `DATABRICKS_HOST`; GitHub CD uses the `dev` environment secrets and OIDC.

### `preflight` says `DATABRICKS_CONFIG_PROFILE` is missing

Your CLI profile name is not set in `.env` or `workspace-config.yml`.

Fix: set `DATABRICKS_CONFIG_PROFILE=<your-profile>` in `.env`.

### `preflight` or runtime cannot find `workspace-config.yml`

You did not copy the example config into the repo root.

Fix:

```bash
cp workspace-config.example.yml workspace-config.yml
```

### `.env` parsing fails because of Databricks credentials

This project intentionally rejects direct local credentials in `.env` for the supported quickstart.

Fix: remove those keys and use `databricks auth login` plus a CLI profile.

### `llm_endpoint_name` is missing or wrong

The endpoint name is empty, misspelled, or points at the wrong serving endpoint.

Fix: update `workspace-config.yml` and rerun `preflight`.

Also make sure the serving endpoint supports the tool/function-calling pattern this template expects.

### selected tools are wrong

Check the wording in [`examples/demo_run_task.json`](examples/demo_run_task.json) and the metadata in [`src/databricks_mcp_agent_hello_world/app/registry.py`](src/databricks_mcp_agent_hello_world/app/registry.py). Task clarity and metadata quality directly affect runtime tool selection.

### Local logs say Spark is unavailable

That is normal during local development.

The project will use `./.local_state` instead of Delta when Spark is not available.

### `preflight` says the Delta event store is not initialized yet

Your Spark-backed storage target is configured, but the Delta table has not been created yet.

Fix: run `init_storage_job`.

### `preflight` fails for `managed_mcp`

`managed_mcp` is still a placeholder and is not implemented yet as a working runtime.

Fix: use `local_python` or implement the `managed_mcp` feature.

### The remote init job fails with a schema mismatch

That means the existing Delta table does not match the canonical Arrow event schema.

Fix: inspect the schema diff from `init_storage_job`, then decide whether to migrate the table, replace it intentionally, or point `storage.agent_events_table` at a fresh target. The template does not drop or recreate tables automatically.

### Deployed job run fails during compute provisioning

Your workspace may not support the default serverless job path in the current resource file.

Fix: update [`resources/jobs.yml`](resources/jobs.yml) to use the compute pattern your workspace allows.

### Deployed runtime cannot read or write the configured Delta tables

Your `storage.agent_events_table` points to a catalog or schema your deployed identity cannot access.

Fix: update `storage.agent_events_table` in `workspace-config.yml` to a writable location and redeploy.

### Databricks job runs but output is empty

Inspect `storage.agent_events_table`, then confirm the runtime task JSON is valid. For the canonical event model and queryable fields, see [Architecture](docs/ARCHITECTURE.md).
