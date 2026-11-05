#!/bin/bash
# R3 screen controller with Astra's N=2 rollout (2026-10-25 00:54 ruling).
#  * a pod is claimed only when it has no AF2M driver of either kind
#  * the FIRST pod claimed after this script starts runs the validation control pair
#    (cap=2, real overlap); it is compared to the p1 pilot truth (0.920 / 0.920)
#  * until validation passes, newly claimed pods run the new runner at cap=1
#  * after a pass, cap=2 everywhere; a failure pins cap=1 and is recorded
#  * never admits after 03:00 ET (guard script owns 03:15/03:30/03:42)
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1
KEY=$HOME/.ssh/runpod_ed25519
R3=results/c3_r3_20261025
LOG=$R3/logs/parallel.log
mkdir -p "$R3/logs"
CUTOFF_EPOCH=${R3_CUTOFF_EPOCH:-1792911600}
VAL_STATE=$R3/validation/state.json
spec_of() { case $1 in p1) echo 63.141.33.138:22113;; p2) echo 194.68.245.32:22065;;
  p3) echo 69.30.85.102:22129;; p4) echo 194.68.245.69:22022;;
  p5) echo 194.68.245.147:22117;; *) return 1;; esac; }
log() { echo "$(date '+%F %T %Z') $*" | tee -a "$LOG"; }
past_cutoff() { [ "$(date +%s)" -ge "$CUTOFF_EPOCH" ]; }

busy_count() {
  local spec host port
  spec=$(spec_of "$1") || return 1
  host=${spec%%:*}; port=${spec#*:}
  ssh -n -i "$KEY" -o StrictHostKeyChecking=no -o ConnectTimeout=10 -o BatchMode=yes -p "$port" root@$host \
    "c=\$(ps -eo args= | grep -cE '^(bash /workspace/pod_run\.sh|python3 .*pod_run_par\.py)' || true); echo \${c:-0}" 2>/dev/null
}

slot_of() { grep -o '"validation"\s*:\s*"[a-z]*"' "$VAL_STATE" 2>/dev/null | head -1; }

validation_state() {
  [ -f "$VAL_STATE" ] && python3 -c "import json;print(json.load(open('$VAL_STATE'))['status'])" 2>/dev/null || echo pending
}

run_validation() {
  local p=$1 spec host port
  spec=$(spec_of "$p"); host=${spec%%:*}; port=${spec#*:}
  log "$p VALIDATION_START (cap=2, 2 scored controls)"
  rsync -az -e "ssh -i $KEY -p $port -o StrictHostKeyChecking=no -o ConnectTimeout=15 -o BatchMode=yes" \
    "$R3/validation/val_input.csv" root@$host:/workspace/val_input.csv || { log "$p val_scp_fail"; return 1; }
  ssh -n -i "$KEY" -o StrictHostKeyChecking=no -o ConnectTimeout=15 -p "$port" root@$host \
    "rm -rf /workspace/val_out; mkdir -p /workspace/val_out; cd /workspace && /workspace/af2m/venv/bin/activate && \
     R3_VALIDATION=1 R3_BATCH_ID=val_$(date +%H%M%S) nohup python3 /workspace/pod_run_par.py /workspace/val_input.csv /workspace/val_out 2 \
     > /workspace/val_out/validation.log 2>&1 < /dev/null & echo VAL_PID=\$!" || return 1
  echo "{\"status\":\"running\",\"pod\":\"$p\",\"started\":\"$(date -Is)\"}" > "$VAL_STATE"
}

collect_validation() {
  local p spec host port
  p=$(python3 -c "import json;print(json.load(open('$VAL_STATE'))['pod'])" 2>/dev/null) || return 1
  spec=$(spec_of "$p"); host=${spec%%:*}; port=${spec#*:}
  rsync -az -e "ssh -i $KEY -p $port -o StrictHostKeyChecking=no -o ConnectTimeout=15 -o BatchMode=yes" \
    root@$host:/workspace/val_out/ "$R3/validation/out/" 2>/dev/null
  python3 - "$R3" <<'PY'
import json, pathlib, sys
r3 = pathlib.Path(sys.argv[1]); out = r3 / "validation" / "out"
truth = {"lm0_e3_ctrl_52_64_26103000_s2": 0.920, "lm1_e3_ctrl_52_64_26103000_s2": 0.920}
res, ok = {}, True
for n, t in truth.items():
    f = out / n / "scores.json"
    if not f.exists(): res[n] = {"status": "MISSING"}; ok = False; continue
    d = json.load(open(f)); got = d.get("iptm"); dd = None if got is None else abs(got - t)
    res[n] = {"truth": t, "observed": got, "abs_delta": dd}
    if dd is None or dd > 0.001: ok = False
batch = list((out / "records").glob("batch_*.json"))
res["_batch"] = json.load(open(batch[0])) if batch else None
res["_verdict"] = "PASS" if ok else "FAIL"
print(json.dumps(res, indent=2))
sys.exit(0 if ok else 1)
PY
}

launch_slice() {
  local p=$1 cap=$2 spec host port
  spec=$(spec_of "$p"); host=${spec%%:*}; port=${spec#*:}
  [ -s "$R3/screen_inputs/$p.csv" ] || { log "$p MISSING_POD_CSV"; return 1; }
  rsync -az -e "ssh -i $KEY -p $port -o StrictHostKeyChecking=no -o ConnectTimeout=15 -o BatchMode=yes" \
    "$R3/screen_inputs/$p.csv" root@$host:/workspace/r3_screen/input.csv || { log "$p slice_scp_fail"; return 1; }
  ssh -n -i "$KEY" -o StrictHostKeyChecking=no -o ConnectTimeout=15 -p "$port" root@$host \
    "mkdir -p /workspace/r3_screen/out /workspace/r3_screen/logs; cd /workspace && /workspace/af2m/venv/bin/activate && \
     R3_BATCH_ID=r3_${p}_$(date +%H%M%S) nohup python3 /workspace/pod_run_par.py /workspace/r3_screen/input.csv /workspace/r3_screen/out $cap \
     > /workspace/r3_screen/logs/par_${p}.log 2>&1 < /dev/null & echo LAUNCHED_PID=\$!" || { log "$p launch_ssh_fail"; return 1; }
  log "$p launched cap=$cap"
}

once() {
  local vs; vs=$(validation_state)
  if past_cutoff; then log "CUTOFF; no admissions"; else
    for p in p1 p2 p3 p4 p5; do
      n=$(busy_count "$p" || echo "")
      if [ -z "$n" ]; then log "$p ssh_probe_failed"; continue; fi
      [ "$n" -gt 0 ] && { continue; }
      case "$vs" in
        pending) run_validation "$p" && { echo "{\"status\":\"collecting\",\"pod\":\"$p\"}" > "$VAL_STATE"; return 0; } ;;
        collecting)
          vp=$(python3 -c "import json;print(json.load(open('$VAL_STATE')).get('pod',''))" 2>/dev/null)
          if [ -n "$vp" ]; then
            s2=$(spec_of "$vp"); h=${s2%%:*}; pt=${s2#*:}
            still=$(ssh -n -i "$KEY" -o StrictHostKeyChecking=no -o ConnectTimeout=10 -o BatchMode=yes -p "$pt" root@$h \
              "ps -eo args= | grep -c '[p]od_run_par.py /workspace/val_input.csv' || true" 2>/dev/null)
            if [ "${still:-0}" -gt 0 ]; then log "validation still folding on $vp"; return 0; fi
          fi
          if collect_validation >> "$R3/validation/verdict.json" 2>&1; then
            echo "{\"status\":\"passed\",\"pod\":\"$p\",\"at\":\"$(date -Is)\"}" > "$VAL_STATE"; log "VALIDATION PASS on $p -> cap=2"
            launch_slice "$p" 2
          else
            echo "{\"status\":\"failed\",\"at\":\"$(date -Is)\"}" > "$VAL_STATE"; log "VALIDATION FAIL -> cap pinned to 1"
            launch_slice "$p" 1
          fi
          return 0 ;;
        passed) launch_slice "$p" 2; return 0 ;;
        running) return 0 ;;
        *) launch_slice "$p" 1; return 0 ;;
      esac
    done
  fi
  bash scripts/c3_r3_screen_pull_20261025.sh >>"$LOG" 2>&1
}

log "PARALLEL_CONTROLLER_START pid=$$ validation=$(validation_state)"
while true; do
  once || log "cycle_rc=$?"
  past_cutoff && { log "PARALLEL_CONTROLLER_STOP cutoff"; exit 0; }
  sleep 120
done
