#!/usr/bin/env bash
set -euo pipefail

CONFIG_PATH="${1:-workspace-config.yml}"
uv run compile_tool_profile --config-path "$CONFIG_PATH"
