#!/usr/bin/env bash
# Create the dedicated trusted Chrome profile directory (not the Playwright tenant).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=/dev/null
source "$ROOT/config/chromium.env"
# shellcheck source=/dev/null
source "$ROOT/config/trusted-browser.env"
mkdir -p "$SATURN_AGENT_BROWSER_TRUSTED_PROFILE"
chmod 700 "$SATURN_AGENT_BROWSER_TRUSTED_PROFILE"
iso="$(readlink -f "$SATURN_AGENT_BROWSER_CHROMIUM_USER_DATA")"
trust="$(readlink -f "$SATURN_AGENT_BROWSER_TRUSTED_PROFILE")"
if [[ "$trust" == "$iso" ]]; then
  echo "trusted profile must not be the isolated Chromium dir" >&2
  exit 1
fi
echo "$SATURN_AGENT_BROWSER_TRUSTED_PROFILE"
