#!/usr/bin/env bash
# Create Agent.kdbx + master key file for saturn-agent-browser broker.
# Stops before anything that needs the KeePassXC GUI or Personal.kdbx.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# shellcheck source=/dev/null
source "$ROOT/config/credentials.env" 2>/dev/null || true

KDBX="${AGENT_KDBX:-$HOME/keepass/Agent.kdbx}"
KEY_DIR="${HOME}/.config/saturn-agent-browser"
KEY_FILE="${AGENT_VAULT_KEY_FILE:-${KEY_DIR}/agent-vault.key}"
SITES_GROUP="Sites"

die() { echo "setup-keepass-agent-vault: $*" >&2; exit 1; }

command -v keepassxc-cli >/dev/null || die "keepassxc-cli not installed"

mkdir -p "$(dirname "$KDBX")" "$KEY_DIR"
chmod 700 "$(dirname "$KDBX")" "$KEY_DIR"

if [[ -f "$KDBX" && ! -f "$KEY_FILE" ]]; then
  die "Agent.kdbx exists but key file missing: $KEY_FILE — create the key file with the vault master password, or remove Agent.kdbx and re-run"
fi

if [[ -f "$KDBX" && -f "$KEY_FILE" ]]; then
  echo "Agent vault already configured:"
  echo "  kdbx: $KDBX"
  echo "  key:  $KEY_FILE"
  exit 0
fi

umask 077
MASTER="$(python3 - <<'PY'
import secrets, string
alphabet = string.ascii_letters + string.digits + "!@#$%^&*-_=+"
print("".join(secrets.choice(alphabet) for _ in range(32)), end="")
PY
)"
printf '%s\n' "$MASTER" >"$KEY_FILE"
chmod 600 "$KEY_FILE"

printf '%s\n%s\n' "$MASTER" "$MASTER" | keepassxc-cli db-create -p -q "$KDBX"
chmod 600 "$KDBX"

printf '%s\n' "$MASTER" | keepassxc-cli mkdir "$KDBX" "$SITES_GROUP" -q

cat <<EOF
Agent vault created.

  Database:  $KDBX
  Master key file: $KEY_FILE  (mode 600)

YOUR STEP (one-time):
  1. Back up the master password from the key file to somewhere you trust.
  2. Optional: keepassxc & → File → Open Database → $KDBX
     (password is in the key file) → verify Sites group exists.

Do not share this key file with agents or commit it to git.
EOF
