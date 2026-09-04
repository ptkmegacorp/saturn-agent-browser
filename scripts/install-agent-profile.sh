#!/usr/bin/env bash
# Create this project's dedicated Chromium profile + Playwright browsers dirs.
# Does not launch a browser. Does not touch other Chromium/Firefox profiles.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=/dev/null
source "$ROOT/config/chromium.env"

umask 0077
mkdir -p "$SATURN_FBC_CHROMIUM_USER_DATA" "$PLAYWRIGHT_BROWSERS_PATH"
chmod 700 "$SATURN_FBC_SHARE" "$SATURN_FBC_CHROMIUM_USER_DATA" "$PLAYWRIGHT_BROWSERS_PATH"

cat <<EOF
saturn-frontier-browser-control Chromium tenant:
  user-data:  $SATURN_FBC_CHROMIUM_USER_DATA
  browsers:   $PLAYWRIGHT_BROWSERS_PATH
  wm class:   $SATURN_FBC_NAME
EOF
