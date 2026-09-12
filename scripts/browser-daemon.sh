#!/usr/bin/env bash
# Launch persistent Chromium daemon with bash-expanded config paths.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=/dev/null
source "$ROOT/config/chromium.env"
# shellcheck source=/dev/null
source "$ROOT/config/browser.env"

export DISPLAY="${DISPLAY:-:0}"
export XAUTHORITY="${XAUTHORITY:-$HOME/.Xauthority}"
export SATURN_AGENT_BROWSER_HEADLESS="${SATURN_AGENT_BROWSER_HEADLESS:-0}"

exec "$ROOT/.venv/bin/python" -m saturn_agent_browser.browser.daemon
