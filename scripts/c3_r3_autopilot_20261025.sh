#!/bin/bash
# R3 AF2M autopilot: fill each pod as soon as its current (sibling) job clears,
# pull artifacts continuously, and stop admitting new designs at the mission cutoff.
#
# It never kills another lane's work: a pod is only claimed when it has no
# pod_run/colabfold/MPNN/ESM work. An already-running R3 driver is health-checked
# instead of counted as foreign work. The launch script is idempotent and
# hash-checks the frozen input on every call. All five pods are covered,
# including p3, so an early death of the first R3 driver is recoverable.
#
# usage: c3_r3_autopilot_20261025.sh [--once]
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1
KEY=$HOME/.ssh/runpod_ed25519
R3=results/c3_r3_20261025
LOG=$R3/logs/autopilot.log
mkdir -p "$R3/logs"
LOCK=$R3/logs/autopilot.instance.lock
VALIDATION_HOLD=$R3/logs/validation.hold

acquire_lock() {
  local owner
  if [ -e "$LOCK" ]; then
    owner=$(cat "$LOCK" 2>/dev/null || true)
    if [ -n "$owner" ] && kill -0 "$owner" 2>/dev/null; then
      echo "$(date '+%F %T %Z') AUTOPILOT_ALREADY_RUNNING pid=$owner" >>"$LOG"
      exit 0
    fi
    rm -f "$LOCK"
  fi
  if ! ( set -o noclobber; echo "$$" >"$LOCK" ) 2>/dev/null; then
    echo "$(date '+%F %T %Z') AUTOPILOT_LOCK_RACE pid=$(cat "$LOCK" 2>/dev/null)" >>"$LOG"
    exit 0
  fi
}

spec_of() { case $1 in p1) echo 63.141.33.138:22113;; p2) echo 194.68.245.32:22065;;
  p3) echo 69.30.85.102:22129;; p4) echo 194.68.245.69:22022;;
  p5) echo 194.68.245.147:22117;; *) return 1;; esac; }

log() { echo "$(date '+%F %T %Z') $*" | tee -a "$LOG"; }

busy_count() {
  local spec host port
  spec=$(spec_of "$1") || return 1
  host=${spec%%:*}; port=${spec#*:}
  ssh -n -i "$KEY" -o StrictHostKeyChecking=no -o ConnectTimeout=10 -o BatchMode=yes \
    -p "$port" root@$host \
    "ps -eo args= | awk '(\$1==\"bash\" && (\$2==\"/workspace/pod_run.sh\" || \$2==\"/workspace/r3_pod_run_par.sh\")) || (\$2 !~ /\\/r3_pod_run.sh$/ && \$2 ~ /\\/colabfold_batch$/) || \$1 ~ /\\/protein_mpnn_run$/ || \$1 ~ /\\/esmfold$/ {n++} END{print n+0}'" 2>/dev/null
}

r3_driver_count() {
  local spec host port
  spec=$(spec_of "$1") || return 1
  host=${spec%%:*}; port=${spec#*:}
  ssh -n -i "$KEY" -o StrictHostKeyChecking=no -o ConnectTimeout=10 -o BatchMode=yes \
    -p "$port" root@$host \
    "ps -eo args= | awk '\$1==\"bash\" && (\$2==\"/workspace/pod_run.sh\" || \$2==\"/workspace/r3_pod_run.sh\" || \$2==\"/workspace/r3_pod_run_par.sh\") && \$3==\"/workspace/r3_screen/input.csv\" {n++} END{print n+0}'" 2>/dev/null
}

r3_par_count() {
  local spec host port
  spec=$(spec_of "$1") || return 1
  host=${spec%%:*}; port=${spec#*:}
  ssh -n -i "$KEY" -o StrictHostKeyChecking=no -o ConnectTimeout=10 -o BatchMode=yes \
    -p "$port" root@$host \
    "ps -eo args= | awk '\$1 ~ /python/ && \$2 ~ /\\/pod_run_par[[:alnum:]_]*\\.py$/ && \$3==\"/workspace/r3_screen/input.csv\" && \$4==\"/workspace/r3_screen/out\" {n++} END{print n+0}'" 2>/dev/null
}

# 2026-10-25 03:00 America/New_York. Fixed epoch avoids both timezone drift on
# a UTC host and bash's octal parsing of a leading-zero HHMM value.
CUTOFF_EPOCH=${R3_CUTOFF_EPOCH:-1792911600}

past_cutoff() {
  [ "$(date +%s)" -ge "$CUTOFF_EPOCH" ]
}

once() {
  local p n r
  past_cutoff && { log "CUTOFF 03:00 reached; no new admissions"; return 2; }
  for p in p1 p2 p3 p4 p5; do
    if [ -e "$VALIDATION_HOLD" ] && [ "$p" = "$(cat "$VALIDATION_HOLD" 2>/dev/null)" ]; then
      log "$p held for N=2 validation"
      continue
    fi
    r=$(r3_driver_count "$p")
    if [ -n "$r" ] && [ "$r" -gt 0 ]; then log "$p r3_running drivers=$r (health-check only)"; continue; fi
    # p3's frozen slice was completed; its active queue is the 53-row remainder.
    # The generic launcher only knows screen_inputs/p3.csv and would recopy the
    # completed 26-row slice, yielding ALL_DONE and losing the remainder again.
    if [ "$p" = p3 ]; then
      if [ -e "$R3/logs/p3_remainder.active" ]; then
        log "p3 remainder active but no driver; leaving for remainder-specific recovery"
        continue
      fi
    fi
    r=$(r3_par_count "$p")
    if [ -n "$r" ] && [ "$r" -gt 0 ]; then log "$p r3_parallel running par=$r (health-check only)"; continue; fi
    # A completed slice is terminal, not a dead driver. Without this, a pod whose
    # queue is fully scored but whose driver has exited is relaunched every cycle:
    # each run prints ALL_DONE and burns SSH while its GPU sits idle. Require BOTH
    # a terminal marker in this pod's run log AND full local coverage of its own
    # frozen CSV before treating "no driver" as done. A pod that died mid-queue has
    # no ALL_DONE, so it is still restarted as intended.
    if [ "$p" = p5 ] && [ -e "$R3/logs/p5_slice.complete" ]; then
      log "p5 slice complete; no relaunch"; continue
    fi
    n=$(busy_count "$p")
    if [ -z "$n" ]; then log "$p ssh_probe_failed"; continue; fi
    if [ "$n" -gt 0 ]; then log "$p busy pod_run=$n (left to owning lane)"; continue; fi
    if bash scripts/c3_r3_screen_launch_20261025.sh "$p" >>"$LOG" 2>&1; then
      log "$p r3_launch_ok"
    else
      log "$p r3_launch_rc=$?"
    fi
  done
  for p in p1 p2 p3 p4 p5; do
    n=$(r3_driver_count "$p")
    if [ -n "$n" ] && [ "$n" -gt 1 ]; then log "WARNING $p has $n R3 drivers"; fi
  done
  bash scripts/c3_r3_screen_pull_20261025.sh >>"$LOG" 2>&1
  log "pull_rc=$?"
  return 0
}

PASSIVE=0
[ "${1:-}" = "--once" ] && PASSIVE=1
[ "$PASSIVE" = 0 ] && acquire_lock
trap '[ "$PASSIVE" = 1 ] || [ "$(cat "$LOCK" 2>/dev/null)" = "$$" ] && rm -f "$LOCK"' EXIT

if [ "$PASSIVE" = 1 ]; then
  once
  exit $?
fi

log "AUTOPILOT_START pid=$$"
while true; do
  once
  rc=$?
  [ "$rc" = 2 ] && break
  sleep 120
done
log "AUTOPILOT_STOP cutoff_now=$(date +%H:%M)"
