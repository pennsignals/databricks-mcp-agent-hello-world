#!/usr/bin/env bash
set -euo pipefail

CONFIG_PATH="${1:-workspace-config.yml}"
SCENARIOS_PATH="${2:-evals/sample_scenarios.json}"
uv run run-evals --config-path "$CONFIG_PATH" --scenarios-path "$SCENARIOS_PATH"
