#!/usr/bin/env bash
# Install saturn-fbc-browser user systemd unit.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
UNIT_SRC="$ROOT/config/saturn-fbc-browser.service"
UNIT_DST="$HOME/.config/systemd/user/saturn-fbc-browser.service"

if [[ ! -x "$ROOT/.venv/bin/python" ]]; then
  echo "Run scripts/setup.sh first (missing $ROOT/.venv/bin/python)" >&2
  exit 1
fi

mkdir -p "$HOME/.config/systemd/user"
cp "$UNIT_SRC" "$UNIT_DST"

"$ROOT/scripts/install-agent-profile.sh"

systemctl --user daemon-reload
echo "Installed user unit: $UNIT_DST"
echo "Start manually: saturn-frontier-browser-control browser start"
echo "Or: systemctl --user start saturn-fbc-browser"
echo "Status: systemctl --user status saturn-fbc-browser"
echo "(Not enabled at boot — start only when you need the browser worker.)"
