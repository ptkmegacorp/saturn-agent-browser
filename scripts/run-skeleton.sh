#!/usr/bin/env bash
# Phase 1 skeleton: scripted fill on local fixture, no model, stop before submit.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

# shellcheck source=/dev/null
source "$ROOT/config/chromium.env"

HEADLESS="${SATURN_AGENT_BROWSER_HEADLESS:-false}"
CONTRACT="${1:-$ROOT/contracts/local-form.json}"

if [[ "${CI:-}" == "true" ]] || [[ "$HEADLESS" == "true" ]] || [[ "$HEADLESS" == "1" ]]; then
  export SATURN_AGENT_BROWSER_HEADLESS=1
  HEADLESS_FLAG="--headless"
else
  HEADLESS_FLAG=""
fi

if [[ ! -x "$ROOT/.venv/bin/saturn-agent-browser" ]]; then
  echo "Run ./scripts/setup.sh first" >&2
  exit 1
fi

TRACE_DIR="$("$ROOT/.venv/bin/saturn-agent-browser" run-skeleton --contract "$CONTRACT" $HEADLESS_FLAG)"
echo "Trace written to: $TRACE_DIR"
