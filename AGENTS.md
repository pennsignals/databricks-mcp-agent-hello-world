# databricks-mcp-agent-hello-world Operator Guide

This is the internal maintainer guide for the template. For setup, first run, day-to-day commands, and troubleshooting, use [README.md](README.md). For runtime and storage design, use [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md). For downstream customization steps, use [docs/CONVERT_TEMPLATE_TO_REAL_APP.md](docs/CONVERT_TEMPLATE_TO_REAL_APP.md).

## What this template is

- a non-interactive LLM agent template
- Databricks-only
- local Python tools are the MVP runtime path today
- `managed_mcp` is retained as a near-term extension point and is intentionally present in the codebase, but it is not implemented yet
- a scheduled Job template, not a Databricks App

## Maintainer workflow expectations

- Keep the README flow canonical for operator onboarding and day-to-day usage.
- Do not introduce alternate beginner setup paths that diverge from the README.
- Treat [`examples/demo_run_task.json`](examples/demo_run_task.json) as the canonical sample task reference instead of restating its payload in prose.
- Prefer the repo-local `.venv` for coding-agent local development when it already exists and has the needed tools installed.
- Treat `python3.11 -m pre_commit run --all-files --show-diff-on-failure` as the maintainer-recommended standard validation command.
- Treat `python3.11 -m pre_commit install` as the one-time workstation setup step for automatic git-hook enforcement.
- Do not document raw lint, test, and build commands as the normal full-validation workflow.

## Testing levels

### Standard repo validation

Commands:

```bash
python3.11 -m pre_commit install
python3.11 -m pre_commit run --all-files --show-diff-on-failure
```

Definition:

- canonical maintainer workflow
- local and CI use the same logical validation flow
- includes repo hygiene hooks, Ruff, version-reference checks, `pytest`, and wheel build validation

### Unit tests

Command:

```bash
pytest
```

Definition:

- local
- fast
- no live LLM call required
- no token usage expected
- use when you intentionally want tests only instead of the full standard validation flow

### Live integration evals

Command:

```bash
run-evals --config-path workspace-config.yml
```

Definition:

- uses the configured Databricks-hosted LLM endpoint
- requires valid auth
- consumes tokens
- may vary slightly between runs

### Hello-world demo run

Command:

```bash
run-agent-task --config-path workspace-config.yml --task-input-file examples/demo_run_task.json
```

Definition:

- demonstrates the actual end-to-end hello-world workflow
- not a test harness
- should be used after preflight and tool discovery succeed

## Core template invariants

The `workspace_onboarding_brief` flow is the starter contract this template must preserve.

- show the full discovered tool set to the model
- let the model choose which tools to call at runtime
- make at least one tool call
- return a final answer built from tool output

Contributor rules:

- keep the default template flow as runtime tool discovery plus model-driven tool selection
- do not reintroduce precompiled profiles, manual allowlists, or deterministic Python-side tool routing into the default path
- keep the bundle flow and job names aligned with `databricks.yml` and `resources/jobs.yml`
- update eval expectations when tool behavior changes

## Maintainer touchpoints

- Example app tool implementations live in `src/databricks_mcp_agent_hello_world/app/tools.py`.
- Tool metadata and JSON schemas are registered in `src/databricks_mcp_agent_hello_world/app/registry.py`.
- Runtime orchestration lives in `src/databricks_mcp_agent_hello_world/runner/agent_runner.py`.
- Runtime config rules live in `src/databricks_mcp_agent_hello_world/config.py`.

## Repo hygiene

Do not commit caches, local state, or build artifacts. These paths are transient development or packaging artifacts and are not part of the template's authored source.

Before commit, verify no content from these paths is staged:

- `.pytest_cache/`
- `__pycache__/`
- `.local_state/`
- `dist/`
- `build/`
- `*.egg-info/`
- `.coverage`
