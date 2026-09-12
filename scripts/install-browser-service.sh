#!/usr/bin/env bash
# Install saturn-agent-browser user systemd unit.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
UNIT_SRC="$ROOT/config/saturn-agent-browser.service"
UNIT_DST="$HOME/.config/systemd/user/saturn-agent-browser.service"

if [[ ! -x "$ROOT/.venv/bin/python" ]]; then
  echo "Run scripts/setup.sh first (missing $ROOT/.venv/bin/python)" >&2
  exit 1
fi

mkdir -p "$HOME/.config/systemd/user"
cp "$UNIT_SRC" "$UNIT_DST"

"$ROOT/scripts/install-agent-profile.sh"

systemctl --user daemon-reload
echo "Installed user unit: $UNIT_DST"
echo "Start manually: saturn-agent-browser browser start"
echo "Or: systemctl --user start saturn-agent-browser"
echo "Status: systemctl --user status saturn-agent-browser"
echo "(Not enabled at boot — start only when you need the browser worker.)"
