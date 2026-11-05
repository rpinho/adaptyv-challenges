#!/bin/bash
# Local health supervisor for the two C3 control planes. It does NOT touch GPUs or arms:
# it only relaunches an autopilot whose lock owner is dead, so a controller crash cannot
# leave five paid pods idle. Duplicate-proof: an alive lock owner is never restarted, and a
# single watchdog instance is enforced with an atomic mkdir lock.
# usage: c3c4_controller_watchdog_20261025.sh [--once]
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1
LOG=results/controller_watchdog_20261025.log
WLOCK=/tmp/c3c4_controller_watchdog.lock.d
END=$(python3 -c "import datetime;print(int(datetime.datetime(2026,10,25,8,10).timestamp()))")
SD=results/c3_sampling_depth_v1_20261025
SR=results/c3_seed_replication_v1_20261025
mkdir -p results
log() { echo "$(date '+%F %T %Z') $*" | tee -a "$LOG"; }

acquire() {
  if ! mkdir "$WLOCK" 2>/dev/null; then
    if [ -n "$(find "$WLOCK" -maxdepth 0 -mmin +10 2>/dev/null)" ]; then rm -rf "$WLOCK"; mkdir "$WLOCK" 2>/dev/null || return 1; else return 1; fi
  fi
  echo "$$" >"$WLOCK/pid"
}
release() { [ "$(cat "$WLOCK/pid" 2>/dev/null)" = "$$" ] && rm -rf "$WLOCK"; }

# A controller is healthy if EITHER its lock owner is alive OR its script process is actually
# running inside the expected tmux session. Requiring only the lock created a dangerous gap:
# a controller that has started but not yet claimed the lock looked dead, and the next cycle
# would have killed a healthy session. Requiring only the session would miss a hung shell.
alive_lock() { local p; p=$(cat "$1" 2>/dev/null || true); [ -n "$p" ] && kill -0 "$p" 2>/dev/null; }
alive_proc() { pgrep -f "bash $1" >/dev/null 2>&1; }
healthy() { # $1=lock file $2=tmux session $3=script path
  tmux has-session -t "$2" 2>/dev/null || return 1
  alive_lock "$1" || alive_proc "$3"
}

relaunch() { # $1=arm label $2=lock $3=session $4=script $5=tee path
  local p
  p=$(cat "$2" 2>/dev/null || true)
  if [ -n "$p" ] && kill -0 "$p" 2>/dev/null; then
    log "$1 controller_alive pid=$p; no action"; return 0
  fi
  log "$1 controller_DEAD lock=${p:-none}; relaunching"
  tmux kill-session -t "$3" 2>/dev/null
  sleep 1
  tmux new-session -d -s "$3" "cd $PWD && bash $4 2>&1 | tee -a $5"
  sleep 6
  p=$(cat "$2" 2>/dev/null || true)
  if healthy "$2" "$3" "$4"; then
    log "$1 relaunched pid=${p:-pending}"
  else
    log "$1 RELAUNCH_UNCONFIRMED lock=${p:-none} session_missing_or_hung"
  fi
}

once() {
  # A FINALIZED arm is complete: never relaunch its controller (that would only re-finalize
  # frozen evidence and churn SHA256SUMS). The seed arm still needs its supervisor.
  if [ -e "$SD/.finalized" ]; then log "sd FINALIZED; no relaunch"; else
    healthy "$SD/autopilot.instance.lock" sd-autopilot scripts/c3_sd_autopilot_20261025.sh && log "sd OK" || \
      relaunch sd "$SD/autopilot.instance.lock" sd-autopilot scripts/c3_sd_autopilot_20261025.sh "$SD/autopilot_tmux.out"
  fi
  # BUGFIX 07:34: the seed arm also writes .finalized (06:38 ET). Without this guard the
  # watchdog relaunched a COMPLETED arm as soon as its supervisor exited at 07:55, which only
  # re-reads frozen evidence and churns the lock. Same rule as the depth arm above.
  if [ -e "$SR/.finalized" ]; then log "seedrep FINALIZED; no relaunch"; else
    healthy "$SR/autopilot.instance.lock" seedrep-autopilot scripts/c3_seedrep_autopilot_20261025.sh && log "seedrep OK" || \
      relaunch seedrep "$SR/autopilot.instance.lock" seedrep-autopilot scripts/c3_seedrep_autopilot_20261025.sh "$SR/autopilot_tmux.out"
  fi
}

if [ "${1:-}" = "--once" ]; then once; exit $?; fi
if ! acquire; then echo "WATCHDOG_ALREADY_RUNNING"; exit 0; fi
trap release EXIT INT TERM
log "WATCHDOG_START pid=$$ end=$END"
while true; do
  [ "$(date +%s)" -ge "$END" ] && { log "WATCHDOG_END_TIME"; break; }
  once
  sleep 60
done
