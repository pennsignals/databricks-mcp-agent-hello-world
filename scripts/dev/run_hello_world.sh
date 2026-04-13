#!/usr/bin/env bash
set -euo pipefail

CONFIG_PATH="${1:-workspace-config.yml}"
uv run run-agent-task \
  --config-path "$CONFIG_PATH" \
  --task-input-file examples/hello_world_task.json
