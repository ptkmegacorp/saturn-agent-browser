#!/usr/bin/env bash
# Install Google Chrome stable. Prefer apt when passwordless sudo works;
# otherwise extract the official amd64 .deb under ~/.local/opt (same bits).
set -euo pipefail

USER_ROOT="${HOME}/.local/opt/google-chrome-stable"
USER_BIN="${USER_ROOT}/opt/google/chrome/google-chrome"

if command -v google-chrome-stable >/dev/null 2>&1; then
  google-chrome-stable --version
  exit 0
fi
if [[ -x "$USER_BIN" ]]; then
  "$USER_BIN" --version
  exit 0
fi

deb=/tmp/google-chrome-stable_current_amd64.deb
curl -fsSL -o "$deb" https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb

if sudo -n true 2>/dev/null; then
  sudo apt-get update -qq
  sudo apt-get install -y "$deb"
  google-chrome-stable --version
  exit 0
fi

rm -rf "$USER_ROOT"
mkdir -p "$USER_ROOT"
dpkg-deb -x "$deb" "$USER_ROOT"
chmod +x "$USER_BIN"
"$USER_BIN" --version
echo "installed user-local Chrome (apt needs sudo): $USER_BIN" >&2
