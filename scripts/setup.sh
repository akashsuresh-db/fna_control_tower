#!/usr/bin/env bash
# FnA Control Tower — Demo Setup
# Usage: ./scripts/setup.sh [target] [--skip-deploy] [--skip-etl] [--extract-only]
# Examples:
#   ./scripts/setup.sh fevm
#   ./scripts/setup.sh dev --skip-deploy
#   ./scripts/setup.sh fevm --extract-only   # re-wire variables from last job run

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

cd "$REPO_ROOT"
exec python3 scripts/setup.py "$@"
