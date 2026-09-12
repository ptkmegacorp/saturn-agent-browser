#!/usr/bin/env bash
# Foreground supervisor for the trusted Chrome lane (systemd Type=simple).
#
# start_trusted() daemonizes, so this wrapper starts Chrome, waits on the
# recorded pid, then exits: 0 when the lane was deliberately stopped
# (state cleared by stop_trusted / ExecStop), 1 on unexpected death so
# Restart=on-failure brings the lane back. Closing the window by hand
# counts as unexpected: use `systemctl --user stop` (or the CLI stop,
# which clears state and yields a clean exit) for a deliberate shutdown.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
# Same order as the ~/bin shim: base paths first, lane overlay last.
# shellcheck source=/dev/null
source "$ROOT/config/chromium.env"
# shellcheck source=/dev/null
source "$ROOT/config/browser.env"
# shellcheck source=/dev/null
source "$ROOT/config/trusted-browser.env"

export DISPLAY="${DISPLAY:-:0}"
export XAUTHORITY="${XAUTHORITY:-$HOME/.Xauthority}"
export SATURN_AGENT_BROWSER_HEADLESS="${SATURN_AGENT_BROWSER_HEADLESS:-0}"

PY="$ROOT/.venv/bin/python"
if [[ ! -x "$PY" ]]; then
  echo "trusted-chrome-service: missing $PY (run scripts/setup.sh)" >&2
  exit 1
fi

START_JSON="$("$PY" -m saturn_agent_browser.cli browser trusted start)"
echo "$START_JSON" | "$PY" -c "import json,sys; d=json.load(sys.stdin); sys.exit(0 if d.get('ok') else 1)" || {
  echo "trusted-chrome-service: start failed: $START_JSON" >&2
  exit 1
}

PID="$("$PY" -m saturn_agent_browser.cli browser trusted status | "$PY" -c "import json,sys; print(json.load(sys.stdin).get('pid') or '')")"
if [[ -z "$PID" ]]; then
  echo "trusted-chrome-service: no pid after start" >&2
  exit 1
fi

while kill -0 "$PID" 2>/dev/null; do
  sleep 2
done

# pid gone: a deliberate stop clears the state file, a crash/window-close
# leaves it behind. Only the latter should trigger Restart=on-failure.
# Grace period covers stop_trusted()'s kill-then-clear sequence racing us.
lane_still_claimed() {
  "$PY" -c "from saturn_agent_browser.browser.trusted import read_trusted_state; raise SystemExit(0 if read_trusted_state() is None else 1)"
}
if ! lane_still_claimed; then
  exit 0
fi
sleep 12
if ! lane_still_claimed; then
  exit 0
fi
echo "trusted-chrome-service: chrome pid $PID exited unexpectedly" >&2
exit 1
