#!/bin/bash
# N=2 health watcher. Read-only on the pods except for restarting an R3 driver
# that has died. Runs until the 03:15 quiesce.
#
# A pod is restarted only when it has NO r3 python driver and NO sibling-lane
# work. Exactly one driver is launched (never two). Every cycle also pulls.
#
# usage: c3_r3_n2_watch_20261025.sh [--once]
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1
KEY=$HOME/.ssh/runpod_ed25519
R3=results/c3_r3_20261025
LOG=$R3/logs/n2_watch.log
mkdir -p "$R3/logs"
ADMIT=1792911600
QUIESCE=1792912500
LOCK=$R3/logs/n2_watch.instance.lock

acquire() {
  if [ -e "$LOCK" ]; then
    o=$(cat "$LOCK" 2>/dev/null || true)
    kill -0 "$o" 2>/dev/null && { echo "$(date '+%F %T') WATCHER_ALREADY_RUNNING pid=$o" >>"$LOG"; exit 0; }
  fi
  ( set -o noclobber; echo "$$" >"$LOCK" ) 2>/dev/null || { echo "$(date '+%F %T') WATCHER_LOCK_RACE" >>"$LOG"; exit 0; }
}
log() { echo "$(date '+%F %T %Z') $*" | tee -a "$LOG"; }
spec_of() { case $1 in p1) echo 63.141.33.138:22113;; p2) echo 194.68.245.32:22065;;
  p3) echo 69.30.85.102:22129;; p4) echo 194.68.245.69:22022;;
  p5) echo 194.68.245.147:22117;; *) return 1;; esac; }
sx() { local spec host port; spec=$(spec_of "$1"); host=${spec%%:*}; port=${spec#*:}; shift
  ssh -n -i "$KEY" -o StrictHostKeyChecking=no -o ConnectTimeout=10 -o BatchMode=yes -p "$port" root@$host "$@"; }

state_of() {  # one line: py folds serial sibling scored
  local spec host port cur; spec=$(spec_of "$1"); host=${spec%%:*}; port=${spec#*:}
  ssh -i "$KEY" -o StrictHostKeyChecking=no -o ConnectTimeout=10 -o BatchMode=yes \
    -p "$port" root@$host 'bash -s' <<'EOS'
py=$(ps -eo args= | grep -cE '^[^ ]*python[^ ]* (/workspace/pod_run_par\.py|c3_r3_pod_run\.py) /workspace/r3_screen/input.csv' || true)
ser=$(ps -eo args= | grep -cE '^bash (/workspace/pod_run\.sh|/workspace/r3_pod_run\.sh|/workspace/r3_pod_run_par\.sh) /workspace/r3_screen/input.csv' || true)
sib=$(ps -eo args= | grep -cE '^(bash /workspace/pod_run\.sh /workspace/lmp|.*protein_mpnn_run$|.*esmfold$)' || true)
fo=$(ps -eo args= | grep -c 'venv/bin/colabfold_batch' || true)
sc=$(ls -d /workspace/r3_screen/out/*/ 2>/dev/null | while read d; do [ -s "$d/scores.json" ] && echo x; done | wc -l)
# A pod whose frozen slice is fully terminal is DONE, not dead. Without this the
# watcher relaunches a driver every cycle; each run prints ALL_DONE and exits, so it
# is harmless but burns an SSH round trip and pollutes the batch records.
dr=$(python3 -c 'import csv,os;r=list(csv.DictReader(open("/workspace/r3_screen/input.csv")));o="/workspace/r3_screen/out";print(len([x for x in r if not os.path.exists(os.path.join(o,x["name"],"scores.json")) and not os.path.exists(os.path.join(o,x["name"],"error.json"))]))' 2>/dev/null || echo unknown)
echo "py=$py serial=$ser sibling=$sib folds=$fo scored=$sc remaining=$dr"
EOS
}

drained() {  # true when the pod has no unfinished design left in its frozen slice
  local rem
  rem=$(echo "$1" | sed -n 's/.*remaining=\([0-9]*\).*/\1/p')
  [ -n "$rem" ] && [ "$rem" = "0" ]
}

restart() {
  local p=$1 cap=2 bid
  bid="r3${p}_w$(date +%H%M%S)"
  sx "$p" "cd /workspace && R3_BATCH_ID=$bid setsid nohup bash /workspace/r3_pod_run_par.sh /workspace/r3_screen/input.csv ALL /workspace/r3_screen/out $cap > /workspace/r3_screen/logs/par_${p}.log 2>&1 </dev/null & disown; sleep 1; echo RESTARTED"
}

once() {
  local p st py sib sc
  local now; now=$(date +%s)
  if [ "$now" -ge "$QUIESCE" ]; then log "QUIESCE reached; watcher idle"; return 2; fi
  for p in p1 p2 p3 p4 p5; do
    st=$(state_of "$p")
    if [ -z "$st" ]; then log "$p ssh_probe_failed"; continue; fi
    py=$(echo "$st" | sed -n 's/.*py=\([0-9]*\).*/\1/p')
    sib=$(echo "$st" | sed -n 's/.*sibling=\([0-9]*\).*/\1/p')
    sc=$(echo "$st" | sed -n 's/.*scored=\([0-9]*\).*/\1/p')
    if [ "${py:-0}" -eq 1 ]; then log "$p ok $st"; continue; fi
    if [ "${py:-0}" -gt 1 ]; then log "$p WARNING python_drivers=$py (not restarting)"; continue; fi
    if [ "${sib:-0}" -gt 0 ]; then log "$p idle_but_sibling_work=$sib (left alone)"; continue; fi
    if [ "$now" -ge "$ADMIT" ]; then log "$p idle past cutoff; no admission"; continue; fi
    # p3's frozen 26-design slice is complete. Its active input.csv is the 53-row
    # unauthorized remainder, which overlaps p1/p2/p4/p5 and re-folds designs those
    # pods own. Astra and Kimi both ruled the frozen slices govern; the remainder is
    # quarantined evidence only. Never restart p3 while that marker exists.
    if [ "$p" = p3 ] && [ -e "$R3/logs/p3_remainder.active" ]; then
      log "$p remainder marker present; not restarting (quarantined evidence)"
      continue
    fi
    if [ "$p" = p3 ] && [ -e "$R3/logs/p3_remainder.quarantined" ]; then
      log "$p remainder quarantined; not restarting"
      continue
    fi
    if drained "$st"; then log "$p drained ($st); no restart"; continue; fi
    log "$p driver_missing ($st) -> restart cap=2"
    restart "$p" >>"$LOG" 2>&1
    sleep 8
    log "$p after_restart $(state_of "$p")"
  done
  bash scripts/c3_r3_screen_pull_20261025.sh >>"$LOG" 2>&1
  log "pull_rc=$?"
  return 0
}

PASSIVE=0; [ "${1:-}" = "--once" ] && PASSIVE=1
[ "$PASSIVE" = 0 ] && acquire
trap '[ "$PASSIVE" = 1 ] || [ "$(cat "$LOCK" 2>/dev/null)" = "$$" ] && rm -f "$LOCK"' EXIT
[ "$PASSIVE" = 1 ] && { once; exit $?; }
log "N2_WATCH_START pid=$$"
while true; do once; rc=$?; [ "$rc" = 2 ] && break; sleep 90; done
log "N2_WATCH_STOP"
