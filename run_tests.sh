#!/usr/bin/env bash
set -e
export PYTEST_DISABLE_PLUGIN_AUTOLOAD=1
"$(dirname "$0")/.venv/bin/pytest" "$@"
