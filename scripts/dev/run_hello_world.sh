#!/usr/bin/env bash
set -euo pipefail

CONFIG_PATH="${1:-workspace-config.yml}"

uv run preflight --config-path "$CONFIG_PATH"
uv run discover-tools --config-path "$CONFIG_PATH"
# The runtime discovers the available tools and lets the LLM choose which tools to call for this input.
uv run run-agent-task \
  --config-path "$CONFIG_PATH" \
  --task-input-file examples/demo_run_task.json \
  --output json
