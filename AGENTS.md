# databricks-mcp-agent-hello-world Operator Guide

## Purpose

This project is a bundle-based, Python-wheel Databricks Job template for a non-interactive, tool-using agent workflow. It is not a Databricks App and does not use `app.yaml`.

## Runtime modes

- Local development:
  - authenticate with `databricks auth login --profile <profile>`
  - copy `.env.example` to `.env`
  - optionally keep `workspace-config.yml` for YAML-based configuration
- Databricks Jobs:
  - deploy with Databricks Bundle
  - run as Python wheel tasks
  - use service principal OAuth or equivalent unattended auth outside local-dev mode

## Tool architecture

- `ToolSpec` defines the LLM-facing contract
- `ToolCall` and `ToolResult` normalize execution requests and responses
- `LocalPythonToolProvider` exposes the current tool registry
- `LocalPythonToolExecutor` executes tools and returns normalized results
- The compiler and runner depend on those internal abstractions, not on MCP transport

## Adding a local Python tool

1. Add the tool function in [`src/databricks_mcp_agent_hello_world/tools/builtin.py`](/Users/mbecker/git/databricks-mcp-agent-hello-world/src/databricks_mcp_agent_hello_world/tools/builtin.py).
2. Register it in [`src/databricks_mcp_agent_hello_world/tools/registry.py`](/Users/mbecker/git/databricks-mcp-agent-hello-world/src/databricks_mcp_agent_hello_world/tools/registry.py).
3. Define:
   - stable tool name
   - description written for the LLM
   - JSON-schema parameters
   - provider metadata and tags
4. If the tool should hit real Databricks services locally, use the Databricks gateway helpers under `src/databricks_mcp_agent_hello_world/clients/`.

## Discovering tools

- `uv run discover-tools --config-path workspace-config.yml`
- `uv run python -m databricks_mcp_agent_hello_world.cli discover-tools --config-path workspace-config.yml`

This prints the normalized tool inventory, provider metadata, inventory hash, and active profile details when available.

## Compiling a profile

- `uv run compile-tool-profile --config-path workspace-config.yml`

The compiler discovers tools, asks the configured LLM endpoint to allow/disallow them, validates the response, writes a versioned profile, and saves the active profile locally.

## Allowlist enforcement

The runner enforces the active allowlist in application code before executing any tool. If the model requests a tool that is not allowlisted, the request is blocked and recorded in the run trace.

## Local execution flow

1. `databricks auth login --profile <profile>`
2. `cp .env.example .env`
3. Fill in `LLM_ENDPOINT_NAME` and optional SQL warehouse/table settings
4. Run `uv run preflight --config-path workspace-config.yml`
5. Run `uv run compile-tool-profile --config-path workspace-config.yml`
6. Run `uv run run-agent-task --config-path workspace-config.yml --task-input-json '<json>'`

## Bundle deployment and Jobs

- `databricks bundle validate`
- `databricks bundle deploy`
- `databricks bundle run databricks_mcp_agent_hello_world_job`

The bundle target remains a scheduled Job using Python wheel tasks.

## Evals

- `uv run run-evals --config-path workspace-config.yml --scenarios-path evals/sample_scenarios.json`

The eval harness runs canned scenarios through `AgentRunner`, captures tool usage and blocked calls, and returns a per-scenario summary.

## Future Managed MCP migration

Managed MCP should be implemented as a future provider and executor adapter. Keep:

- tool names stable
- tool descriptions stable
- input schemas stable
- result envelopes stable

The goal is to swap the backing provider/executor without rewriting the agent loop.
