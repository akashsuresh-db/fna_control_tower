#!/usr/bin/env bash
# Finance & Accounting Demo — Test Runner
# =========================================
# Usage:
#   ./tests/run_tests.sh             # run all tests
#   ./tests/run_tests.sh backend     # backend only
#   ./tests/run_tests.sh frontend    # frontend only
#   APP_URL=https://... ./tests/run_tests.sh frontend  # against deployed app

set -e
REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
APP_DIR="$REPO_ROOT/app"
TESTS_DIR="$REPO_ROOT/tests"
FRONTEND_DIR="$APP_DIR/frontend"

MODE="${1:-all}"

run_backend() {
  echo ""
  echo "═══════════════════════════════════════════"
  echo "  Running Backend Tests (pytest)"
  echo "═══════════════════════════════════════════"
  cd "$APP_DIR"
  PYTHONPATH="$(pwd)" \
  DATABRICKS_WAREHOUSE_ID="${DATABRICKS_WAREHOUSE_ID:-4b9b953939869799}" \
  DATABRICKS_CATALOG="${DATABRICKS_CATALOG:-hp_sf_test}" \
  DATABRICKS_SCHEMA="${DATABRICKS_SCHEMA:-finance_and_accounting}" \
  /Users/akash.s/miniconda3/bin/pytest "$TESTS_DIR/test_backend.py" -v \
    --tb=short \
    2>&1
}

run_frontend() {
  echo ""
  echo "═══════════════════════════════════════════"
  echo "  Running Frontend E2E Tests (Playwright)"
  echo "═══════════════════════════════════════════"
  cd "$FRONTEND_DIR"
  # Install playwright if needed
  if ! npx playwright --version >/dev/null 2>&1; then
    npm install -D @playwright/test
    npx playwright install chromium --with-deps
  fi
  # Start local dev server in background if no APP_URL set
  if [ -z "$APP_URL" ]; then
    echo "Starting local dev server..."
    npm run dev &
    DEV_PID=$!
    sleep 4  # wait for vite to start
    trap "kill $DEV_PID 2>/dev/null" EXIT
    export APP_URL="http://localhost:5173"
  fi
  npx playwright test \
    --config="$TESTS_DIR/playwright.config.ts" \
    2>&1
}

case "$MODE" in
  backend)  run_backend ;;
  frontend) run_frontend ;;
  all)
    run_backend
    run_frontend
    ;;
  *)
    echo "Usage: $0 [backend|frontend|all]"
    exit 1
    ;;
esac

echo ""
echo "✓ Tests complete"
