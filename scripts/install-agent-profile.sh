#!/usr/bin/env bash
# Create this project's dedicated Chromium profile + Playwright browsers dirs.
# Does not launch a browser. Does not touch other Chromium/Firefox profiles.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=/dev/null
source "$ROOT/config/chromium.env"

umask 0077
mkdir -p "$SATURN_AGENT_BROWSER_CHROMIUM_USER_DATA" "$PLAYWRIGHT_BROWSERS_PATH"
chmod 700 "$SATURN_AGENT_BROWSER_SHARE" "$SATURN_AGENT_BROWSER_CHROMIUM_USER_DATA" "$PLAYWRIGHT_BROWSERS_PATH"

cat <<EOF
saturn-agent-browser Chromium tenant:
  user-data:  $SATURN_AGENT_BROWSER_CHROMIUM_USER_DATA
  browsers:   $PLAYWRIGHT_BROWSERS_PATH
  wm class:   $SATURN_AGENT_BROWSER_NAME
EOF
