# databricks-mcp-agent-hello-world

`databricks-mcp-agent-hello-world` is a bundle-based, Python-wheel Databricks Job template for a non-interactive, tool-using agent workflow. It is a Databricks Job template, not a Databricks App, and it is meant to be run locally first and then deployed as a bundle.

For MVP, `local_python` is the only working runtime backend. `managed_mcp` is reserved for a future extension path.

## Required edits before your first run

- [ ] Replace the placeholder workspace host in `databricks.yml` before you run `databricks bundle validate` or `databricks bundle deploy`.
  - Placeholder:
    ```yaml
    targets:
      dev:
        workspace:
          host: https://your-workspace.cloud.databricks.com
      prod:
        workspace:
          host: https://your-workspace.cloud.databricks.com
    ```
  - Intended pattern:
    ```yaml
    targets:
      dev:
        workspace:
          host: https://<your-workspace-host>
      prod:
        workspace:
          host: https://<your-workspace-host>
    ```
- [ ] Create a real repo-root `workspace-config.yml` by copying `workspace-config.example.yml`.
- [ ] Keep `workspace-config.yml` in the repo root for local runs.
- [ ] Make sure the deployed job YAML uses this exact config path syntax:
  ```yaml
  config_path: ${workspace.file_path}/workspace-config.yml
  ```

## Quickstart

Use one path only: CLI profile auth, repo-root `workspace-config.yml`, local checks first, then bundle deploy.

1. Install prerequisites

   Install the Databricks CLI, Python, and `uv`.

   Success: all three are available on your machine.

2. Authenticate locally

   ```bash
   databricks auth login
   ```

   If you are not using the `DEFAULT` profile, pass `--profile <name>` and use the same profile name in `DATABRICKS_CONFIG_PROFILE`.

   Success: the Databricks CLI can authenticate with your workspace profile.

3. Copy starter config files

   ```bash
   cp .env.example .env
   cp workspace-config.example.yml workspace-config.yml
   ```

   Success: both files exist at the repo root.

4. Edit required local settings

   Set `LLM_ENDPOINT_NAME` in `.env`.

   If your Databricks CLI profile is not `DEFAULT`, set `DATABRICKS_CONFIG_PROFILE` in `.env` to the same profile name.

   Success: local commands know which LLM endpoint and CLI profile to use, while `workspace-config.yml` stays the main project config file.

5. Update `databricks.yml` before bundle validation

   Replace the placeholder host shown above with your real workspace host for `targets.dev.workspace.host`, and for `targets.prod.workspace.host` if that target is present.

   Success: bundle validation points at your actual workspace instead of the placeholder URL.

6. Run local checks in this exact order

   ```bash
   uv sync
   uv run preflight --config-path workspace-config.yml
   uv run discover-tools --config-path workspace-config.yml
   uv run compile-tool-profile --config-path workspace-config.yml
   uv run run-agent-task --config-path workspace-config.yml --task-input-json '{"task_name":"hello_world_demo"}'
   ```

   Success:
   - `uv sync` installs the project dependencies.
   - `preflight` passes and confirms config parsing, profile resolution, and tool registration.
   - `discover-tools` shows the full discovered tool set.
   - `compile-tool-profile` produces the hello-world allowlist profile.
   - `run-agent-task` shows the discovered tool count, the allowed subset, the actual tool calls, and the final answer.

   Note: if local logs say Spark is unavailable, that is expected off-cluster. Local fallback persistence is normal during local development, and Delta-backed persistence is expected only when the code runs on Databricks compute.

7. Deploy to Databricks

   ```bash
   databricks bundle validate --target dev
   databricks bundle deploy --target dev
   databricks bundle run --target dev compile_tool_profile_job
   databricks bundle run --target dev run_agent_task_job
   ```

   Success:
   - `bundle validate` passes after the placeholder host has been replaced.
   - `bundle deploy --target dev` succeeds.
   - `compile_tool_profile_job` runs successfully and compiles the active profile in the workspace.
   - `run_agent_task_job` runs successfully and returns the hello-world result on Databricks.

## Common setup issues

1. `databricks bundle validate` fails with the placeholder host

   Symptom: validation errors reference `https://your-workspace.cloud.databricks.com`.

   Fix: update `targets.<target>.workspace.host` in `databricks.yml`.

2. `preflight` or runtime cannot find `workspace-config.yml`

   Symptom: the command fails because the config file is missing.

   Fix: copy `workspace-config.example.yml` to `workspace-config.yml` and keep it in the repo root.

3. `LLM_ENDPOINT_NAME` is missing or invalid

   Symptom: local validation fails or the agent cannot start with the configured endpoint.

   Fix: update `.env` or `workspace-config.yml` with the correct Databricks-hosted endpoint name.

4. Local logs say Spark is unavailable

   Symptom: local runs print a message about Spark not being present.

   Fix: that is expected in local mode. Local fallback persistence is normal off-cluster.

5. Job runtime cannot find the config path

   Symptom: the Databricks job cannot load `workspace-config.yml`.

   Fix: confirm `config_path` in the job YAML matches the deployed workspace file path and that `workspace-config.yml` is part of the deployed project.
