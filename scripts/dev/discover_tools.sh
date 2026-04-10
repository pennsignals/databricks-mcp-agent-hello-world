#!/usr/bin/env bash
set -euo pipefail

CONFIG_PATH="${1:-workspace-config.yml}"
uv run discover-tools --config-path "$CONFIG_PATH"
