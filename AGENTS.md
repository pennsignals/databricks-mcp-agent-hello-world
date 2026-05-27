# databricks-mcp-agent-hello-world Operator Guide

This is the internal maintainer guide for the template. For setup and first run, use [README.md](README.md). For runtime design, use [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md). For downstream customization, use [docs/CONVERT_TEMPLATE_TO_REAL_APP.md](docs/CONVERT_TEMPLATE_TO_REAL_APP.md).

## What This Template Is

- a batch/non-interactive LLM agent template
- Databricks-only
- local Python tools plus optional Databricks MCP tool discovery
- a Databricks Job template, not a Databricks App

## Maintainer Workflow Expectations

- Keep the README flow canonical for operator onboarding.
- Treat [examples/demo_run_task.json](examples/demo_run_task.json) as the canonical sample task reference.
- Prefer the repo-local `.venv` for coding-agent local development when it already exists and has the needed tools installed.
- Treat `python3.12 -m pre_commit run --all-files --show-diff-on-failure` as the standard validation command.
- Treat `python3.12 -m pre_commit install` as the one-time workstation setup step for automatic git-hook enforcement.
- Do not document raw lint, test, and build commands as the normal full-validation workflow.

## Testing Levels

### Standard Repo Validation

Commands:

```bash
python3.12 -m pre_commit install
python3.12 -m pre_commit run --all-files --show-diff-on-failure
```

Definition:

- canonical maintainer workflow
- local and CI use the same logical validation flow
- includes repo hygiene hooks, Ruff, Markdown linting, test execution, and wheel build validation

### Unit Tests

Command:

```bash
python -m nox -s unit
```

Definition:

- local
- fast
- no live LLM call required
- no token usage expected

### Contract Tests

Command:

```bash
python -m nox -s contract
```

Definition:

- validates public behavior and stable cross-module contracts
- no live LLM call required

### All Tests

Command:

```bash
python -m nox -s tests
```

### Live Integration Evals

Command:

```bash
run-evals --config-path workspace-config.yml --scenario-file evals/sample_scenarios.json
```

Definition:

- uses the configured Databricks-hosted LLM endpoint
- requires valid auth
- consumes tokens
- verifies run status, expected tool use, and required output text

### Hello-World Demo Run

Command:

```bash
run-agent-task --config-path workspace-config.yml --task-input-file examples/demo_run_task.json
```

Definition:

- demonstrates the end-to-end hello-world workflow
- should be used after preflight and tool discovery succeed

## Core Template Invariants

The `workspace_onboarding_brief` flow is the starter contract this template must preserve.

- show the full discovered tool set to the model
- let the model choose which tools to call at runtime
- make at least one tool call
- return a final answer built from tool output

Contributor rules:

- keep the default template flow as runtime tool discovery plus model-driven tool selection
- do not add manual allowlists or deterministic Python-side tool routing into the default path
- keep the bundle flow and job names aligned with `databricks.yml` and `resources/jobs.yml`
- update eval expectations when tool behavior changes

## Maintainer Touchpoints

- Example app tool implementations live in `src/databricks_mcp_agent_hello_world/app/tools.py`.
- Tool metadata and JSON schemas are registered in `src/databricks_mcp_agent_hello_world/app/registry.py`.
- Runtime orchestration lives in `src/databricks_mcp_agent_hello_world/runner/agent_runner.py`.
- Runtime config rules live in `src/databricks_mcp_agent_hello_world/config.py`.

## Repo Hygiene

Do not commit caches, local state, or build artifacts. These paths are transient development or packaging artifacts and are not part of the template's authored source.

Before commit, verify no content from these paths is staged:

- `.pytest_cache/`
- `__pycache__/`
- `.local_state/`
- `dist/`
- `build/`
- `*.egg-info/`
- `.coverage`
