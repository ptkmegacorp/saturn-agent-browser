#!/usr/bin/env bash
# Smoke-test ~/bin/saturn-agent-browser JSON CLI.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CLI="${SATURN_AGENT_BROWSER_CLI:-$(command -v saturn-agent-browser || echo ./.venv/bin/saturn-agent-browser)}"

json_ok() {
  python3 -c 'import json,sys; json.load(sys.stdin)' >/dev/null
}

echo "== version =="
"$CLI" version

echo "== status =="
"$CLI" status | json_ok

echo "== validate-contract =="
"$CLI" validate-contract "$ROOT/contracts/local-form.json" | json_ok

echo "== broker-status =="
"$CLI" broker-status | json_ok

echo "== run-skeleton headless =="
"$CLI" run-skeleton --contract "$ROOT/contracts/local-form.json" --headless | json_ok

echo "== last =="
"$CLI" last | json_ok

echo "smoke-cli: OK"
