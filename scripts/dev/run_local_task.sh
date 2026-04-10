#!/usr/bin/env bash
set -euo pipefail

CONFIG_PATH="${1:-workspace-config.yml}"
TASK_INPUT_JSON="${2:-{\"task_name\":\"demo-task\",\"instructions\":\"Use tools if helpful to summarize the current customer and incident context.\"}}"
uv run run_agent_task --config-path "$CONFIG_PATH" --task-input-json "$TASK_INPUT_JSON"
