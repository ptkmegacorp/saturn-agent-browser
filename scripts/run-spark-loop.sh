#!/usr/bin/env bash
# Spark observe/act loop on a contract (fixtures by default).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
source "$ROOT/config/chromium.env"

CONTRACT="${1:-$ROOT/contracts/local-form.json}"
HEADLESS="${SATURN_FBC_HEADLESS:-0}"
EXTRA=()
if [[ "$HEADLESS" == "1" ]]; then
  EXTRA+=(--headless)
fi

exec "$ROOT/.venv/bin/saturn-fbc" run --contract "$CONTRACT" "${EXTRA[@]}"
