#!/bin/bash
# R3 clock guard. Enforces the Kimi/Astra cutoff without touching another lane:
#   * no new R3 design after 03:00 ET (the driver itself checks this per design);
#   * 03:15 ET: terminate only the R3 AF2M driver's own process group
#     (serial, R3-wrapper, or the parallel wrapper/python driver);
#   * 03:30 ET: pull, verify, structurally check and hash the R3 record.
#
# usage: c3_r3_guard_20261025.sh [--once]
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1
KEY=$HOME/.ssh/runpod_ed25519
R3=results/c3_r3_20261025
LOG=$R3/logs/guard.log
mkdir -p "$R3/logs"
LOCK=$R3/logs/guard.instance.lock

acquire_lock() {
  local owner
  if [ -e "$LOCK" ]; then
    owner=$(cat "$LOCK" 2>/dev/null || true)
    if [ -n "$owner" ] && kill -0 "$owner" 2>/dev/null; then
      echo "$(date '+%F %T %Z') GUARD_ALREADY_RUNNING pid=$owner" >>"$LOG"
      exit 0
    fi
    rm -f "$LOCK"
  fi
  if ! ( set -o noclobber; echo "$$" >"$LOCK" ) 2>/dev/null; then
    echo "$(date '+%F %T %Z') GUARD_LOCK_RACE pid=$(cat "$LOCK" 2>/dev/null)" >>"$LOG"
    exit 0
  fi
}

ADMIT_EPOCH=${R3_ADMIT_EPOCH:-1792911600}   # 2026-10-25 03:00:00-04:00
QUIESCE_EPOCH=${R3_QUIESCE_EPOCH:-1792912500} # 2026-10-25 03:15:00-04:00
FINAL_EPOCH=${R3_FINAL_EPOCH:-1792913400}    # 2026-10-25 03:30:00-04:00

spec_of() { case $1 in p1) echo 63.141.33.138:22113;; p2) echo 194.68.245.32:22065;;
  p3) echo 69.30.85.102:22129;; p4) echo 194.68.245.69:22022;;
  p5) echo 194.68.245.147:22117;; *) return 1;; esac; }

log() { echo "$(date '+%F %T %Z') $*" | tee -a "$LOG"; }
now() { date +%s; }

# Count any surviving R3 driver of any form. Used after quiesce to prove the
# pod is actually quiet before the final pull/verify runs.
r3_alive() {
  # Count DRIVERS, not processes: a wrapper and its python child are one driver,
  # and a bare python launch counts as one. Counting logic is unit-tested in
  # scripts/c3_r3_driver_count_pod.py so it cannot silently drift.
  local p=$1 spec host port
  spec=$(spec_of "$p") || return 1
  host=${spec%%:*}; port=${spec#*:}
  # NOTE: do NOT pass -n here. -n discards stdin, so 'python3 -' would read EOF,
  # print nothing, and the guard would treat "empty" as "no drivers" -> a silent
  # quiesce that kills nothing. Verified bug, fixed 2026-10-25 02:24.
  ssh -i "$KEY" -o StrictHostKeyChecking=no -o ConnectTimeout=10 \
    -o BatchMode=yes -p "$port" root@$host 'python3 -' \
    < scripts/c3_r3_driver_count_pod.py 2>/dev/null
}

quiesce_pod() {
  local p=$1 spec host port
  spec=$(spec_of "$p") || return 1
  host=${spec%%:*}; port=${spec#*:}
  ssh -i "$KEY" -o StrictHostKeyChecking=no -o ConnectTimeout=10 \
    -o BatchMode=yes -p "$port" root@$host 'python3 -' < scripts/c3_r3_quiesce_pod.py 2>>"$LOG"
}

once() {
  local t; t=$(now)
  if [ "$t" -ge "$ADMIT_EPOCH" ] && [ "$t" -lt "$QUIESCE_EPOCH" ]; then
    log "no-new-admissions window (in-flight designs may finish)"
  fi
  if [ "$t" -lt "$QUIESCE_EPOCH" ]; then
    log "guard open until 03:15"
    return 0
  fi
  if [ "$t" -lt "$FINAL_EPOCH" ]; then
    local p
    local alive=0
    for p in p1 p2 p3 p4 p5; do
      log "quiesce $p: $(quiesce_pod "$p" 2>&1)"
      local r; r=$(r3_alive "$p")
      if [ -n "$r" ] && [ "$r" -gt 0 ]; then
        log "WARNING $p still has $r R3 driver(s) after quiesce"
        alive=$((alive+r))
      fi
    done
    if [ "$alive" -gt 0 ]; then
      log "QUIESCE_INCOMPLETE drivers=$alive (retrying next cycle; no finalize)"
      return 1
    fi
    if [ ! -e "$R3/cutoff_snapshot_20261025.json" ]; then
      python3 scripts/c3_r3_cutoff_snapshot_20261025.py >>"$LOG" 2>&1
      log "cutoff_snapshot_rc=$?"
    fi
    # Kimi ruling Q5: freeze the 182-row coverage ledger at quiesce.
    # NOTE: this must NOT be skipped just because an older ledger exists. An earlier
    # version used `[ ! -e ... ]` and a 01:58 partial ledger (82/182) silently blocked
    # the 03:15 freeze. Always re-freeze at quiesce.
    if true; then
      bash scripts/c3_r3_screen_pull_20261025.sh >>"$LOG" 2>&1
      python3 scripts/c3_r3_coverage_ledger_20261025.py --write >>"$LOG" 2>&1
      log "coverage_ledger_rc=$?"
    fi
    return 0
  fi
  if [ ! -e "$R3/.finalized" ]; then
    local p2 alive=0
    for p2 in p1 p2 p3 p4 p5; do
      local r2; r2=$(r3_alive "$p2")
      [ -n "$r2" ] && [ "$r2" -gt 0 ] && alive=$((alive+r2))
    done
    if [ "$alive" -gt 0 ]; then
      log "FINALIZE_BLOCKED drivers=$alive (quiesce not complete)"
      return 1
    fi
    log "FINALIZE_START"
    if [ ! -e "$R3/cutoff_snapshot_20261025.json" ]; then
      python3 scripts/c3_r3_cutoff_snapshot_20261025.py >>"$LOG" 2>&1
      log "cutoff_snapshot_rc=$?"
    fi
    bash scripts/c3_r3_screen_pull_20261025.sh >>"$LOG" 2>&1
    log "pull_rc=$?"
    python3 scripts/c3_r3_coverage_ledger_20261025.py --write >>"$LOG" 2>&1
    log "coverage_ledger_rc=$?"
    python3 scripts/c3_r3_verify_20261025.py >>"$LOG" 2>&1
    log "verify_rc=$?"
    python3 scripts/c3_r3_structural_20261025.py >>"$LOG" 2>&1
    log "structural_rc=$?"
    python3 scripts/c3_r3_finalize_20261025.py >>"$LOG" 2>&1
    local frc=$?
    log "finalize_rc=$frc"
    if [ "$frc" = 0 ]; then
      # Kimi's ledger also requires generated/valid/screened/clash/eligible and
      # crosswalked-independent counts, which the finalizer does not emit.
      # Read-only, fail-closed; it never writes a CSV or changes a status.
      python3 scripts/c3_r3_report_20261025.py >>"$LOG" 2>&1
      local rrc=$?
      log "report_rc=$rrc"
      # The report is read-only, so a failure cannot damage the frozen evidence.
      # Make it unmistakable instead of letting a missing report look like a
      # complete chain; .finalized still records that the CUTOFF chain ran.
      if [ "$rrc" != 0 ]; then
        : >"$R3/report_20261025.FAILED"
      fi
      touch "$R3/.finalized"
    fi
    return "$frc"
  fi
  return 0
}

PASSIVE=0
[ "${1:-}" = "--once" ] && PASSIVE=1
[ "$PASSIVE" = 0 ] && acquire_lock
trap '[ "$PASSIVE" = 1 ] || [ "$(cat "$LOCK" 2>/dev/null)" = "$$" ] && rm -f "$LOCK"' EXIT

if [ "$PASSIVE" = 1 ]; then once; exit $?; fi
log "R3_GUARD_START pid=$$ admit=$ADMIT_EPOCH quiesce=$QUIESCE_EPOCH final=$FINAL_EPOCH"
while true; do
  once; rc=$?
  [ "$rc" = 0 ] && [ -e "$R3/.finalized" ] && break
  sleep 60
done
log "R3_GUARD_STOP"
