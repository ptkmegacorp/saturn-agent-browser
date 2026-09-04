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
systemctl --user enable saturn-fbc-browser.service
echo "Installed user unit: $UNIT_DST"
echo "Start with: systemctl --user start saturn-fbc-browser"
echo "Status with: systemctl --user status saturn-fbc-browser"
