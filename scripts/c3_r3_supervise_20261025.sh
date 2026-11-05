#!/bin/bash
# Idempotent host supervisor for the two R3 watchers. Safe to run every 60 s.
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1
TMUX=/Users/ricardo/.local/bin/tmux
[ -x "$TMUX" ] || { echo "SUPERVISE_ERROR tmux not found" >&2; exit 1; }
needs_restart() {
  local pattern=$1
  ps -eo args= | awk -v p="$pattern" '$0 == p {n++} END{exit !(n>=1)}' && return 1
  return 0
}
start() {
  local session=$1 cmd=$2
  if "$TMUX" has-session -t "$session" 2>/dev/null; then
    "$TMUX" send-keys -t "$session" C-c >/dev/null 2>&1 || true
    sleep 1
    "$TMUX" kill-session -t "$session" >/dev/null 2>&1 || true
  fi
  "$TMUX" new-session -d -s "$session" "cd '$PWD' && $cmd"
}
if needs_restart 'bash scripts/c3_r3_autopilot_20261025.sh'; then
  start r3-autopilot 'bash scripts/c3_r3_autopilot_20261025.sh >> results/c3_r3_20261025/logs/autopilot.out 2>&1'
fi
if needs_restart 'bash scripts/c3_r3_guard_20261025.sh'; then
  start r3-guard 'bash scripts/c3_r3_guard_20261025.sh >> results/c3_r3_20261025/logs/guard.out 2>&1'
fi
