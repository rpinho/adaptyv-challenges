#!/bin/bash
# Cut a pod over from the serial R3 driver to the validated N=2 driver.
#
# Lossless by construction: the admission freezer waits for the in-flight
# design to persist its scores.json, then stops the driver. No fold is
# discarded and no design is folded twice (design-only claims).
#
# Every step is verified. If the parallel driver does not come up as exactly
# one wrapper + one python, the pod is rolled back to the serial driver so a
# pod can never be left idle.
#
# usage: c3_r3_cutover_par_20261025.sh [--cap N] pod [pod ...]
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1
KEY=$HOME/.ssh/runpod_ed25519
R3=results/c3_r3_20261025
LOG=$R3/logs/cutover.log
mkdir -p "$R3/logs"
CAP=2
if [ "${1:-}" = "--cap" ]; then CAP=$2; shift 2; fi
CUTOFF_EPOCH=${R3_CUTOFF_EPOCH:-1792911600}
FREEZER=scripts/c3_r3_admission_freeze_pod.py
FSHA=$(shasum -a 256 "$FREEZER" | cut -d' ' -f1)

spec_of() { case $1 in p1) echo 63.141.33.138:22113;; p2) echo 194.68.245.32:22065;;
  p3) echo 69.30.85.102:22129;; p4) echo 194.68.245.69:22022;;
  p5) echo 194.68.245.147:22117;; *) return 1;; esac; }
log() { echo "$(date '+%F %T %Z') $*" | tee -a "$LOG"; }

sx() { local p=$1; shift; local spec host port
  spec=$(spec_of "$p"); host=${spec%%:*}; port=${spec#*:}
  ssh -n -i "$KEY" -o StrictHostKeyChecking=no -o ConnectTimeout=15 -o BatchMode=yes \
    -p "$port" root@$host "$@"; }

drivers() {  # shell roots only (one healthy driver == one root)
  sx "$1" "ps -eo args= | awk '\$1==\"bash\" && (\$2==\"/workspace/pod_run.sh\" || \$2==\"/workspace/r3_pod_run.sh\" || \$2==\"/workspace/r3_pod_run_par.sh\") && \$3==\"/workspace/r3_screen/input.csv\" {n++} END{print n+0}'"
}
any_python() {  # serial or parallel python driver for the R3 input
  sx "$1" "ps -eo args= | awk '\$1 ~ /python/ && (\$2 ~ /\/c3_r3_pod_run\.py$/ || \$2 ~ /\/pod_run_par[[:alnum:]_]*\.py$/ || \$2==\"-\") && \$3==\"/workspace/r3_screen/input.csv\" {n++} END{print n+0}'"
}
par_wrappers() { sx "$1" "ps -eo args= | awk '\$1==\"bash\" && \$2==\"/workspace/r3_pod_run_par.sh\" && \$3==\"/workspace/r3_screen/input.csv\" {n++} END{print n+0}'"; }
par_pythons()  { sx "$1" "ps -eo args= | awk '\$1 ~ /python/ && \$2 ~ /\/pod_run_par[[:alnum:]_]*\.py$/ && \$3==\"/workspace/r3_screen/input.csv\" {n++} END{print n+0}'"; }
colabfolds()   { sx "$1" "ps -eo args= | awk '\$2 ~ /\/colabfold_batch$/ {n++} END{print n+0}'"; }
sibling()      { sx "$1" "ps -eo args= | awk '(\$1==\"bash\" && \$2==\"/workspace/pod_run.sh\" && \$3!=\"/workspace/r3_screen/input.csv\") || \$1 ~ /\/protein_mpnn_run$/ || \$1 ~ /\/esmfold$/ {n++} END{print n+0}'"; }
scored()       { sx "$1" "ls -d /workspace/r3_screen/out/*/ 2>/dev/null | while read d; do [ -s \"\$d/scores.json\" ] && echo x; done | wc -l" | tr -d ' '; }

launch_par() {
  local p=$1 bid
  bid="r3${p}_$(date +%H%M%S)"
  sx "$p" "cd /workspace && R3_BATCH_ID=$bid setsid nohup bash /workspace/r3_pod_run_par.sh /workspace/r3_screen/input.csv ALL /workspace/r3_screen/out $CAP > /workspace/r3_screen/logs/par_${p}.log 2>&1 < /dev/null & disown; sleep 1; echo PAR_LAUNCHED"
}

launch_serial() {  # rollback path
  local p=$1
  sx "$p" "cd /workspace && setsid nohup bash /workspace/r3_pod_run.sh /workspace/r3_screen/input.csv ALL /workspace/r3_screen/out > /workspace/r3_screen/logs/screen_${p}.log 2>&1 < /dev/null & disown; sleep 1; echo SERIAL_ROLLBACK"
}

# Cross-session claim: two orchestrators are live tonight, so a pod may only be
# cut over by whoever creates its claim file first (noclobber is atomic).
claim_pod() {
  local p=$1 f=$R3/logs/cutover.claim.$p
  mkdir -p "$R3/logs"
  if ! ( set -o noclobber; echo "$$ $(date -Is)" >"$f" ) 2>/dev/null; then
    log "$p SKIP already_claimed_by $(cat "$f" 2>/dev/null)"
    return 1
  fi
  return 0
}

cutover_pod() {
  local p=$1 spec host port n s before after
  claim_pod "$p" || return 1
  spec=$(spec_of "$p") || { log "$p UNKNOWN_POD"; return 1; }
  host=${spec%%:*}; port=${spec#*:}
  [ "$(date +%s)" -ge "$CUTOFF_EPOCH" ] && { log "$p REFUSE past cutoff"; return 1; }
  s=$(sibling "$p"); if [ -z "$s" ]; then log "$p ABORT ssh_probe_failed"; return 1; fi
  if [ "$s" -gt 0 ]; then log "$p ABORT sibling_lane_work=$s"; return 1; fi
  before=$(scored "$p")
  n=$(drivers "$p")
  if [ -z "$n" ]; then log "$p ABORT ssh_probe_failed"; return 1; fi
  if [ "$n" -gt 1 ]; then log "$p ABORT roots=$n (already duplicated; not touching)"; return 1; fi
  local apy; apy=$(any_python "$p")
  if [ -n "$apy" ] && [ "$apy" -gt 1 ]; then log "$p ABORT pythons=$apy (already duplicated; not touching)"; return 1; fi

  # Stage the (patched) freezer and check its hash.
  rsync -az -e "ssh -i $KEY -p $port -o StrictHostKeyChecking=no -o ConnectTimeout=15 -o BatchMode=yes" \
    "$FREEZER" root@$host:/workspace/r3_screen/c3_r3_admission_freeze_pod.py || { log "$p ABORT freezer_scp"; return 1; }
  local fsha; fsha=$(sx "$p" "sha256sum /workspace/r3_screen/c3_r3_admission_freeze_pod.py | cut -d' ' -f1")
  [ "$fsha" = "$FSHA" ] || { log "$p ABORT freezer_sha"; return 1; }

  if [ "$n" -gt 0 ]; then
    # Replace any freezer already holding the lock (it was armed for 03:00).
    sx "$p" "pkill -f 'c3_r3_admission_freeze_pod.py --at 1792911600' || true" >/dev/null 2>&1
    sleep 1
    log "$p freezing at design boundary (scored_before=$before)"
    local out; out=$(timeout 900 ssh -n -i "$KEY" -o StrictHostKeyChecking=no -o ConnectTimeout=15 \
    -o BatchMode=yes -p "$port" root@$host \
    "cd /workspace && python3 -u /workspace/r3_screen/c3_r3_admission_freeze_pod.py --at 1" 2>&1)
    log "$p freeze: $out"
    case "$out" in *FREEZE_DONE*) ;; *) log "$p ABORT freeze_failed"; return 1;; esac
    sleep 2
    n=$(drivers "$p"); apy=$(any_python "$p")
    if { [ -n "$n" ] && [ "$n" -gt 0 ]; } || { [ -n "$apy" ] && [ "$apy" -gt 0 ]; }; then
      log "$p ABORT driver_survived_freeze roots=$n python=$apy"; return 1
    fi
  fi

  log "$p launching parallel cap=$CAP"
  local lo; lo=$(launch_par "$p"); log "$p $lo"
  sleep 12
  local w py cf
  w=$(par_wrappers "$p"); py=$(par_pythons "$p"); cf=$(colabfolds "$p")
  if [ "${w:-0}" != "1" ] || [ "${py:-0}" != "1" ]; then
    log "$p VERIFY_FAIL wrappers=$w python=$py -> ROLLBACK to serial"
    sx "$p" "pkill -f '^bash /workspace/r3_pod_run_par.sh' || true; pkill -f '/workspace/pod_run_par.py' || true" >/dev/null 2>&1
    launch_serial "$p" >/dev/null
    sleep 6
    log "$p rollback roots=$(drivers "$p") python=$(any_python "$p")"
    return 1
  fi
  after=$(scored "$p")
  log "$p CUTOVER_OK wrappers=$w python=$py colabfold=$cf scored=$before->$after cap=$CAP"

  # Re-arm the admission freezer for the new (parallel) driver.
  sx "$p" "cd /workspace && setsid nohup python3 -u /workspace/r3_screen/c3_r3_admission_freeze_pod.py --at $CUTOFF_EPOCH > /workspace/r3_screen/logs/freeze_${p}.log 2>&1 < /dev/null & disown; sleep 1; echo FREEZE_REARMED" >/dev/null
  return 0
}

rc=0
for p in "$@"; do cutover_pod "$p" || rc=1; done
exit $rc
