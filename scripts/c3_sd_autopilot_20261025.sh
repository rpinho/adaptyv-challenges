#!/bin/bash
# Sampling-depth arm control loop. Pulls artifacts, verifies with the unchanged gate,
# and restarts a pod's frozen driver only when it has no driver and no in-flight fold.
# Admission stops at the manifest cutoff; quiesce and final verification follow.
# usage: c3_sd_autopilot_20261025.sh [--once]
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1
KEY=$HOME/.ssh/runpod_ed25519
SD=results/c3_sampling_depth_v1_20261025
LOG=$SD/autopilot.log
LOCK=$SD/autopilot.instance.lock
mkdir -p "$SD" "$SD/logs"
ADMIT=$(python3 -c "import json;print(json.load(open('$SD/af2m_manifest.json'))['admission_cutoff_epoch'])")
HARD=$(python3 -c "import json;print(json.load(open('$SD/af2m_manifest.json'))['hard_stop_epoch'])")
QUIESCE=$((ADMIT+120))

log() { echo "$(date '+%F %T %Z') $*" | tee -a "$LOG"; }
spec_of() { case $1 in p1) echo 63.141.33.138:22113;; p2) echo 194.68.245.32:22065;;
  p3) echo 69.30.85.102:22129;; p4) echo 194.68.245.69:22022;;
  p5) echo 194.68.245.147:22117;; *) return 1;; esac; }

acquire() {
  local owner
  if [ -e "$LOCK" ]; then
    owner=$(cat "$LOCK" 2>/dev/null || true)
    if [ -n "$owner" ] && kill -0 "$owner" 2>/dev/null; then log "SD_AUTOPILOT_ALREADY_RUNNING pid=$owner"; exit 0; fi
    rm -f "$LOCK"
  fi
  if ! (set -o noclobber; echo "$$" >"$LOCK") 2>/dev/null; then log "SD_AUTOPILOT_LOCK_RACE"; exit 0; fi
}

# prints: drivers=N folds=N gpu=NN keepalive=epoch
probe() {
  # drivers/folds/scored PLUS terminal-completion evidence. A completed slice leaves no
  # driver behind, so "drivers==0" alone must never be read as "dead" (that bug relaunched
  # finished R3 pods every cycle). alldone counts ONLY the driver's own par_*.log line
  # '^ALL_DONE$'; a loose grep matched ESM_ALL_DONE and would have masked a real dead pod.
  local spec host port
  spec=$(spec_of "$1") || return 1; host=${spec%%:*}; port=${spec#*:}
  ssh -n -i "$KEY" -o StrictHostKeyChecking=no -o ConnectTimeout=12 -o BatchMode=yes -p "$port" root@$host \
    "d=\$(ps -eo args= | awk '\$1==\"bash\" && \$2==\"/workspace/sd1/sd_pod_run_par.sh\" {n++} END{print n+0}'); f=\$(ps -eo args= | awk '{for(i=1;i<=NF;i++) if (\$i ~ /\\/colabfold_batch\$/) {n++; break}} END{print n+0}'); g=\$(nvidia-smi --query-gpu=utilization.gpu --format=csv,noheader,nounits 2>/dev/null | head -1 | tr -d ' '); k=\$(stat -c %Y /root/keepalive 2>/dev/null || echo 0); s=\$(find /workspace/sd1/out -name scores.json 2>/dev/null | wc -l | tr -d ' '); e=\$(find /workspace/sd1/out -name error.json 2>/dev/null | wc -l | tr -d ' '); a=\$(grep -l '^ALL_DONE$' /workspace/sd1/logs/par_*.log 2>/dev/null | wc -l | tr -d ' '); se=\$(ps -eo args= | awk '\$1 ~ /python/ && \$2==\"/workspace/pod_run_seed.py\" {n++} END{print n+0}'); echo \"drivers=\$d folds=\$f gpu=\${g:-0} keepalive=\$k scored=\$s errors=\$e alldone=\$a seeds=\$se\"" 2>/dev/null
}

restart() {
  # Use the frozen, hash-checking launch script: it re-stages the pod slice and runner,
  # verifies local/pod SHA equality, and refuses to launch if a driver already exists.
  bash scripts/c3_sd_screen_launch_20261025.sh "$1"
}

terminate_arm_driver() {
  # Hard-stop guard: terminate only this arm's own process group on the pod.
  local spec host port
  spec=$(spec_of "$1") || return 1; host=${spec%%:*}; port=${spec#*:}
  ssh -n -i "$KEY" -o StrictHostKeyChecking=no -o ConnectTimeout=12 -o BatchMode=yes -p "$port" root@$host \
    "pg=\$(ps -eo pid=,args= | awk '\$2==\"bash\" && \$3==\"/workspace/sd1/sd_pod_run_par.sh\" {print \$1; exit}'); if [ -n \"\$pg\" ]; then kill -TERM -\$pg 2>/dev/null || kill -TERM \$pg 2>/dev/null; echo SD_TERM_$1 pid=\$pg; else echo SD_NO_DRIVER_$1; fi" 2>/dev/null
}

all_slices_done() {
  # 1 only if all five pods printed ALL_DONE and no driver/fold is in flight.
  local p st d f a n=0
  for p in p1 p2 p3 p4 p5; do
    st=$(probe "$p") || return 1
    [ -z "$st" ] && return 1
    d=$(sed -n 's/.*drivers=\([0-9]*\).*/\1/p' <<<"$st")
    f=$(sed -n 's/.*folds=\([0-9]*\).*/\1/p' <<<"$st")
    a=$(sed -n 's/.*alldone=\([0-9]*\).*/\1/p' <<<"$st")
    [ "${d:-0}" -eq 0 ] || return 1
    [ "${f:-0}" -eq 0 ] || return 1
    [ "${a:-0}" -ge 1 ] || return 1
    n=$((n+1))
  done
  [ "$n" -eq 5 ]
}

once() {
  local now p st d f g k s
  now=$(date +%s)
  if [ "$now" -lt "$ADMIT" ]; then
    for p in p1 p2 p3 p4 p5; do
      st=$(probe "$p")
      if [ -z "$st" ]; then log "$p ssh_probe_failed"; continue; fi
      d=$(sed -n 's/.*drivers=\([0-9]*\).*/\1/p' <<<"$st")
      f=$(sed -n 's/.*folds=\([0-9]*\).*/\1/p' <<<"$st")
      s=$(sed -n 's/.*scored=\([0-9]*\).*/\1/p' <<<"$st")
      a=$(sed -n 's/.*alldone=\([0-9]*\).*/\1/p' <<<"$st")
      if [ "${d:-0}" -eq 1 ]; then log "$p ok drivers=1 folds=${f:-0} scored=${s:-0}"; continue; fi
      if [ "${d:-0}" -gt 1 ]; then log "$p WARNING drivers=$d; not restarting"; continue; fi
      if [ "${f:-0}" -gt 0 ]; then log "$p no_driver_but_inflight_folds=$f; waiting"; continue; fi
      se=$(sed -n 's/.*seeds=\([0-9]*\).*/\1/p' <<<"$st")
      # Cross-arm guard: once the seed-replication arm owns this GPU, the screen arm must not
      # reclaim it. A finished screen slice never needs a relaunch anyway; this only protects
      # a pod that died mid-slice after the screen had released it.
      if [ "${se:-0}" -gt 0 ]; then log "$p seed_arm_active seeds=$se; NOT relaunching screen"; continue; fi
      if [ "${a:-0}" -ge 1 ]; then log "$p slice_complete_alldone scored=${s:-0}; NOT restarting"; continue; fi
      log "$p driver_missing; restarting frozen slice"
      restart "$p" >>"$LOG" 2>&1
      sleep 4
      log "$p after_restart $(probe "$p")"
    done
    bash scripts/c3_sd_pull_20261025.sh >>"$LOG" 2>&1
    log "pull_rc=$?"
    python3 scripts/c3_sd_verify_20261025.py >>"$LOG" 2>&1
    log "verify_rc=$?"
    return 0
  fi
  # Pre-quiesce: normally just let in-flight folds finish. BUT if every slice is already
  # terminal (ALL_DONE on all five pods) and nothing is in flight, finalize immediately
  # instead of idling the pods until 06:13.
  if [ "$now" -lt "$QUIESCE" ]; then
    local early=0
    early=$(all_slices_done)
    if [ "$early" = 1 ]; then log "SD_ALL_SLICES_COMPLETE; finalizing before cutoff"; else
      log "admission cutoff reached; no new launches, letting in-flight folds finish"; return 0; fi
  fi
  if [ ! -e "$SD/.finalized" ]; then
    local alive=0 all_done=1 slices=0 expected=5
    for p in p1 p2 p3 p4 p5; do
      st=$(probe "$p"); [ -z "$st" ] && { log "$p ssh_probe_failed_at_final"; all_done=0; continue; }
      d=$(sed -n 's/.*drivers=\([0-9]*\).*/\1/p' <<<"$st")
      f=$(sed -n 's/.*folds=\([0-9]*\).*/\1/p' <<<"$st")
      a=$(sed -n 's/.*alldone=\([0-9]*\).*/\1/p' <<<"$st")
      alive=$((alive+${d:-0}))
      [ "${a:-0}" -ge 1 ] && slices=$((slices+1))
      [ "${a:-0}" -ge 1 ] || all_done=0
    done
    # Finalization waits for THIS ARM's driver only. Seed-replication folds can be running on
    # the same GPUs after the screen releases them; counting them would block the screen's
    # freeze past 06:31. terminate_arm_driver kills the screen's process group, so an in-flight
    # screen fold dies with its driver.
    if [ "$alive" -gt 0 ] && [ "$now" -ge "$HARD" ]; then
      log "SD_HARD_STOP reached active=$alive; terminating only this arm's drivers"
      for p in p1 p2 p3 p4 p5; do terminate_arm_driver "$p" >>"$LOG" 2>&1; done
      sleep 5
      alive=0
      for p in p1 p2 p3 p4 p5; do
        st=$(probe "$p"); [ -z "$st" ] && continue
        d=$(sed -n 's/.*drivers=\([0-9]*\).*/\1/p' <<<"$st")
        alive=$((alive+${d:-0}))
      done
    fi
    if [ "$alive" -gt 0 ]; then log "SD_FINALIZE_BLOCKED active=$alive now=$now"; return 1; fi
    log "SD_FINALIZE_START"
    bash scripts/c3_sd_snapshot_20261025.sh --force >>"$LOG" 2>&1; log "snapshot_rc=$?"
    bash scripts/c3_sd_pull_20261025.sh >>"$LOG" 2>&1; log "pull_rc=$?"
    python3 scripts/c3_sd_verify_20261025.py >>"$LOG" 2>&1; local vrc=$?; log "verify_rc=$vrc"
    if [ "$vrc" = 0 ]; then
      python3 scripts/c3_sd_finalize_20261025.py --force >>"$LOG" 2>&1; local frc=$?; log "finalize_rc=$frc"
      python3 scripts/c3_sd_deltab_20261025.py >>"$LOG" 2>&1; log "deltab_rc=$?"
      if [ "$frc" = 0 ]; then
        # SUMS lists repo-relative paths, so the check MUST run from the repo root.
        # Running it from "$SD" made every finalize report a false failure.
        local src=0
        shasum -a 256 -c "$SD/SHA256SUMS.evidence" >>"$LOG" 2>&1; src=$?; log "sha_verify_rc=$src"
        if [ "$src" = 0 ]; then
          touch "$SD/.finalized"
          log "SD_FINALIZED verify_rc=0 finalize_rc=0 sha_verify_rc=0"
          return 0
        fi
        touch "$SD/finalize.SHA_FAILED"
        log "SD_FINALIZE_SHA_FAILED rc=$src; NOT touching .finalized"
        return "$src"
      fi
      touch "$SD/finalize.FAILED"
      log "SD_FINALIZE_FAILED rc=$frc"
      return "$frc"
    fi
    touch "$SD/verify.FAILED"
    log "SD_VERIFY_FAILED rc=$vrc"
    return "$vrc"
  fi
  return 0
}

PASSIVE=0; [ "${1:-}" = "--once" ] && PASSIVE=1
[ "$PASSIVE" = 0 ] && acquire
release_lock() { [ "$PASSIVE" = 0 ] && [ "$(cat "$LOCK" 2>/dev/null)" = "$$" ] && rm -f "$LOCK"; }
trap release_lock EXIT
if [ "$PASSIVE" = 1 ]; then once; exit $?; fi
log "SD_AUTOPILOT_START pid=$$ admit=$ADMIT hard=$HARD"
while true; do
  once; rc=$?
  [ -e "$SD/.finalized" ] && break
  sleep 120
done
log "SD_AUTOPILOT_STOP"
