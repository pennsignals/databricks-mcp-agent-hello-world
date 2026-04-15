# databricks-mcp-agent-hello-world

## What this template is

This is a non-interactive async agent template for repeatable Databricks Jobs workflows. It uses a single agent with tool calling, a task-aware profile compilation step, and a runtime execution step. The demo assets are meant to be replaced, while the framework is intended to be reused as-is. Databricks Jobs can orchestrate repeatable tasks and run Python wheel tasks, which is why this template is packaged as a bundle plus wheel-driven jobs.

[See Architecture](docs/ARCHITECTURE.md)  
[See Convert the template into a real app](docs/CONVERT_TEMPLATE_TO_REAL_APP.md)

## How the agent works

The runtime stays intentionally small:

1. discover tools
2. compile a task-aware allowlist profile
3. persist the profile
4. run the agent with only the allowed tools exposed
5. let the LLM decide which allowed tools to call
6. persist run artifacts and outputs

Tool selection is LLM-driven. The template does not use task-specific hard-coded allowlists.

Compile-time tool filtering happens in `_filter_tools(...)` in [`src/databricks_mcp_agent_hello_world/profiles/compiler.py`](src/databricks_mcp_agent_hello_world/profiles/compiler.py). Runtime tool use happens through the generic tool-calling loop in [`src/databricks_mcp_agent_hello_world/runner/agent_runner.py`](src/databricks_mcp_agent_hello_world/runner/agent_runner.py), and runtime allowlist enforcement still exists as a safety boundary.

Architecture summary: the compiler asks the model to choose the smallest useful tool subset for a representative task, persists that `ToolProfile`, then the generic runner executes the real task with only those tools exposed and persists run traces plus final outputs.

## Project layout

- `src/databricks_mcp_agent_hello_world/profiles/` — core framework; compiles and loads persisted tool profiles.
- `src/databricks_mcp_agent_hello_world/runner/` — core framework; runs the generic agent loop with runtime allowlist checks.
- `src/databricks_mcp_agent_hello_world/tools/` — demo asset; registers the current local demo tool inventory and metadata.
- `src/databricks_mcp_agent_hello_world/demo/` — demo asset; contains the replaceable demo tool implementations and fixture data.
- `src/databricks_mcp_agent_hello_world/evals/` — core framework; provides the generic eval harness used to score scenarios.
- `examples/` — demo asset; contains the demo compile task file and demo run task file.
- `docs/` — validation/test asset; contains the architecture and conversion guides for maintainers.
- `resources/` — deployment config; defines the Databricks Jobs resources for compile and run.
- `tests/` — validation/test asset; contains unit tests, demo contract tests, and docs consistency checks.

## Run the demo locally

Use one canonical local path:

```bash
uv sync
cp workspace-config.example.yml workspace-config.yml
cp .env.example .env
databricks auth login --host https://<your-workspace-host>
```

Set `llm_endpoint_name` in `workspace-config.yml`, set `DATABRICKS_CONFIG_PROFILE` in `.env`, and keep `default_compile_task_file: examples/demo_compile_task.json`.

```bash
uv run compile-tool-profile \
  --config-path workspace-config.yml \
  --task-input-file examples/demo_compile_task.json
```

```bash
uv run run-agent-task \
  --config-path workspace-config.yml \
  --task-input-file examples/demo_run_task.json
```

```bash
uv run run-evals \
  --config-path workspace-config.yml \
  --scenario-file evals/sample_scenarios.json
```

The current demo discovers five tools. For the read-only onboarding brief, the LLM-driven compiler should allow the four read-only tools and disallow the write tool.

## Run the demo in Databricks

Use one canonical Databricks path:

```bash
databricks bundle deploy --target dev
databricks bundle run --target dev compile_tool_profile_job
databricks bundle run --target dev run_agent_task_job
```

Inspect results in the configured persistence targets:

- `storage.tool_profile_table` for the persisted `ToolProfile`
- `storage.agent_runs_table` for `AgentRunRecord`
- `storage.agent_output_table` for `AgentOutputRecord`

The deployed jobs read the workspace copy of `workspace-config.yml` from `${workspace.file_path}/workspace-config.yml`, so keep that deployed config aligned with the local config you validated.

## Files you will customize first

- [`examples/demo_compile_task.json`](examples/demo_compile_task.json) — the representative compile-time task contract the LLM compiler uses to select a minimal useful tool subset.
- [`examples/demo_run_task.json`](examples/demo_run_task.json) — the runtime task payload the generic runner executes after a profile already exists.
- [`src/databricks_mcp_agent_hello_world/demo/tools.py`](src/databricks_mcp_agent_hello_world/demo/tools.py) — the current demo tool implementations you replace with real project tools.
- [`src/databricks_mcp_agent_hello_world/tools/registry.py`](src/databricks_mcp_agent_hello_world/tools/registry.py) — the demo tool registry entries and metadata the compiler sees.
- [`evals/sample_scenarios.json`](evals/sample_scenarios.json) — the demo eval scenarios that should be rewritten for your domain.
- [`databricks.yml`](databricks.yml) — the bundle name and default run payload that downstream teams commonly rename.
- [`resources/databricks_mcp_agent_hello_world_job.yml`](resources/databricks_mcp_agent_hello_world_job.yml) — the demo job names and task names for the compile and runtime jobs.
- [`workspace-config.example.yml`](workspace-config.example.yml) — the example config fields, including `default_compile_task_file`, profile naming, endpoint naming, and storage targets.

## Files you should usually leave alone

- [`src/databricks_mcp_agent_hello_world/profiles/compiler.py`](src/databricks_mcp_agent_hello_world/profiles/compiler.py) — compiler core; keep the LLM-driven profile compilation architecture intact.
- [`src/databricks_mcp_agent_hello_world/runner/agent_runner.py`](src/databricks_mcp_agent_hello_world/runner/agent_runner.py) — runner core; keep the generic tool-calling loop and allowlist boundary intact.
- [`src/databricks_mcp_agent_hello_world/storage/result_writer.py`](src/databricks_mcp_agent_hello_world/storage/result_writer.py) — storage/result writer; keep the local-versus-Delta persistence behavior intact.
- [`src/databricks_mcp_agent_hello_world/evals/harness.py`](src/databricks_mcp_agent_hello_world/evals/harness.py) — generic eval harness; keep the compile-then-run scoring flow intact.
- [`src/databricks_mcp_agent_hello_world/models.py`](src/databricks_mcp_agent_hello_world/models.py) — core data models for `ToolProfile`, `AgentRunRecord`, and `AgentOutputRecord`.

## Convert this template into a real app

Use [See Convert the template into a real app](docs/CONVERT_TEMPLATE_TO_REAL_APP.md) as the step-by-step migration guide. It names the exact files to edit when you replace the demo with a real async agent job.

## Troubleshooting

### no active profile found

`run-agent-task` requires a persisted profile. Re-run:

```bash
uv run compile-tool-profile \
  --config-path workspace-config.yml \
  --task-input-file examples/demo_compile_task.json
```

### compile task file missing

Your config or CLI path points at a file that does not exist. Check [`workspace-config.example.yml`](workspace-config.example.yml) and confirm `default_compile_task_file` or your `--task-input-file` path matches a real file.

### selected tools are wrong

Check the task wording in [`examples/demo_compile_task.json`](examples/demo_compile_task.json) and the metadata in [`src/databricks_mcp_agent_hello_world/tools/registry.py`](src/databricks_mcp_agent_hello_world/tools/registry.py). Metadata quality and task clarity directly affect `_filter_tools(...)`.

### Databricks job runs but output is empty

Inspect `storage.agent_runs_table` and `storage.agent_output_table`, then check whether the run hit a max-step or empty-final-response case in [`src/databricks_mcp_agent_hello_world/runner/agent_runner.py`](src/databricks_mcp_agent_hello_world/runner/agent_runner.py). Also confirm the compile job ran first and that the task input JSON passed to the job is valid.

### evals failing after demo replacement

Update [`evals/sample_scenarios.json`](evals/sample_scenarios.json) to match your new tools, task files, and output contract. The generic harness in [`src/databricks_mcp_agent_hello_world/evals/harness.py`](src/databricks_mcp_agent_hello_world/evals/harness.py) is meant to stay stable while scenario content changes.
