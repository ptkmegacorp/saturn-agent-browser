#!/usr/bin/env bash
# Create venv, install package, Playwright Chromium, and agent profile dirs.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

# shellcheck source=/dev/null
source "$ROOT/config/chromium.env"

if ! command -v uv >/dev/null 2>&1; then
  echo "uv is required but not installed" >&2
  exit 1
fi

uv venv .venv
# shellcheck source=/dev/null
source .venv/bin/activate

uv pip install -e ".[dev]"

export PLAYWRIGHT_BROWSERS_PATH
python -m playwright install chromium

"$ROOT/scripts/install-agent-profile.sh"
"$ROOT/scripts/setup-keepass-agent-vault.sh" || true

echo "Setup complete. Activate with: source $ROOT/.venv/bin/activate"
