# databricks-mcp-agent-hello-world Operator Guide

Review `REQUIREMENTS.md` before starting work, and re-read it before finishing to confirm your changes still match the project requirements.

## Local development model

- Local auth uses Databricks CLI profile auth via `databricks auth login`.
- `workspace-config.yml` is the primary runtime config file.
- `.env` is optional and only for non-secret local defaults plus `DATABRICKS_CONFIG_PROFILE`.
- Do not put `DATABRICKS_HOST`, `DATABRICKS_TOKEN`, `DATABRICKS_CLIENT_ID`, or `DATABRICKS_CLIENT_SECRET` in `.env` for the supported local quickstart path.

## Config precedence

1. CLI flags
2. `workspace-config.yml`
3. `.env`
4. Databricks CLI profile settings from `.databrickscfg`

`llm_endpoint_name` is configured in `workspace-config.yml`.

## Supported commands

- `preflight`
- `discover-tools`
- `compile-tool-profile`
- `run-agent-task`
- `run-evals`

All commands accept `--config-path`, which defaults to `workspace-config.yml`.

## What `preflight` checks

- config file parse
- `.env` parse when present
- `DATABRICKS_CONFIG_PROFILE` resolution
- Databricks client initialization
- `llm_endpoint_name`
- local tool registry import
- at least one registered tool
- provider factory resolution
- persistence target names
- read-only Delta target reachability when Spark is available
- `has_active_profile`
- `can_compile_profile`

`preflight` does not call the LLM, compile profiles, run the agent, or write to Delta.

## What `discover-tools` shows

- provider type
- total tool count
- normalized tool names
- tool descriptions
- input schema summaries

## Local vs. scheduled jobs

- Local development uses attended CLI profile auth.
- Databricks Jobs should use unattended auth such as service principal OAuth.
- Keep the local quickstart simple now, while preserving the future path for scheduled-job auth and Managed MCP adapters later.
- For MVP, `local_python` is the only working runtime backend. `managed_mcp` is a reserved future provider value and should fail fast if selected.
