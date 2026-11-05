#!/bin/bash
# Pipeline the seed-replication arm pod-by-pod as each pod finishes its sampling-depth slice.
# Astra 04:11: "start after the sampling-depth arm releases capacity, without preemption."
# Never touches a pod still folding the arm. Enforces the 07:30 hard stop from inside the loop.
# usage: nohup bash scripts/c3_seedrep_pipeline_20261025.sh > results/c3_seed_replication_v1_20261025/pipeline.log 2>&1 &
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1
SR=results/c3_seed_replication_v1_20261025
KEY=$HOME/.ssh/runpod_ed25519
CUTOFF=1792926000      # 07:00 ET admissions
HARD=1792927800        # 07:30 ET hard stop
mkdir -p "$SR"
spec_of() { case $1 in p1) echo 63.141.33.138:22113;; p2) echo 194.68.245.32:22065;;
  p3) echo 69.30.85.102:22129;; p4) echo 194.68.245.69:22022;;
  p5) echo 194.68.245.147:22117;; esac; }
done_marker() { echo "$SR/.started_$1"; }

echo "$(date +%FT%TZ) PIPELINE_START cutoff=$CUTOFF hard=$HARD"
while :; do
  now=$(date +%s)
  if [ "$now" -ge "$HARD" ]; then
    echo "$(date +%FT%TZ) PIPELINE_HARD_STOP"
    for p in p1 p2 p3 p4 p5; do
      s=$(spec_of "$p"); h=${s%%:*}; po=${s#*:}
      ssh -n -i "$KEY" -o StrictHostKeyChecking=no -o ConnectTimeout=15 -p "$po" root@"$h" \
        "pkill -f 'pod_run_seed.py' && echo QUIESCED_$p || echo QUIET_$p" 2>/dev/null
    done
    break
  fi
  all=1
  for p in p1 p2 p3 p4 p5; do
    [ -e "$(done_marker "$p")" ] && continue
    all=0
    s=$(spec_of "$p"); h=${s%%:*}; po=${s#*:}
    st=$(timeout 30 ssh -n -i "$KEY" -o StrictHostKeyChecking=no -o ConnectTimeout=15 -p "$po" root@"$h" \
      'python3 - <<PY
import os
a=c=sd=0
for pid in filter(str.isdigit, os.listdir("/proc")):
    try: cmd=open(f"/proc/{pid}/cmdline","rb").read().replace(b"\0",b" ").decode("utf-8","replace")
    except Exception: continue
    # The screen driver is a BASH wrapper; its python child is "python3 /workspace/pod_run_par.py".
    # Match both so the screen is never mistaken for idle (this pattern was wrong and would
    # have launched the seed arm on top of five live screen drivers).
    if "sd_pod_run_par.sh" in cmd or "pod_run_par.py" in cmd: a+=1
    if "bin/colabfold_batch" in cmd: c+=1
    if "pod_run_seed.py" in cmd: sd+=1
print(f"arm={a} cf={c} seed={sd}")
PY' 2>/dev/null)
    arm=${st#arm=}; arm=${arm%% *}; rest=${st##* }
    cf=$(sed -n 's/.*cf=\([0-9]*\).*/\1/p' <<<"$st")
    seed=$(sed -n 's/.*seed=\([0-9]*\).*/\1/p' <<<"$st")
    if [ "${seed:-0}" -gt 0 ]; then echo "$(date +%FT%TZ) SEEDREP_ALREADY_RUNNING_$p"; continue; fi
    case "${arm:-1}:${cf:-1}" in
      0:0)
        if bash scripts/c3_seedrep_launch_20261025.sh "$p" >> "$SR/pipeline.log" 2>&1; then
          touch "$(done_marker "$p")"
          echo "$(date +%FT%TZ) REPLICATION_STARTED_$p"
        else
          echo "$(date +%FT%TZ) REPLICATION_LAUNCH_FAILED_$p"
        fi ;;
      *) ;;
    esac
  done
  [ "$all" = 1 ] && { echo "$(date +%FT%TZ) ALL_PODS_REPLICATING"; break; }
  sleep 60
done
echo "$(date +%FT%TZ) PIPELINE_EXIT"
