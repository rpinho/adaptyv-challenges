#!/bin/bash
# Pull sampling-depth arm MPNN output and AF2M results. READ-ONLY on the pods.
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1
KEY=$HOME/.ssh/runpod_ed25519
OUT=results/c3_sampling_depth_v1_20261025
LOG=$OUT/pull.log
mkdir -p "$OUT"
echo "=== $(date '+%F %T %Z') SD pull" >> "$LOG"
for spec in "p1:63.141.33.138:22113" "p2:194.68.245.32:22065" "p3:69.30.85.102:22129" \
            "p4:194.68.245.69:22022" "p5:194.68.245.147:22117"; do
  pod=${spec%%:*}; rest=${spec#*:}; host=${rest%%:*}; port=${rest##*:}
  mkdir -p "$OUT/mpnn/$pod" "$OUT/out/$pod"
  rsync -az --timeout=120 -e "ssh -i $KEY -p $port -o ConnectTimeout=10 -o StrictHostKeyChecking=no -o BatchMode=yes" \
    "root@$host:/workspace/sd1/mpnn/" "$OUT/mpnn/$pod/" >>"$LOG" 2>&1
  rc1=$?
  rsync -az --timeout=180 -e "ssh -i $KEY -p $port -o ConnectTimeout=10 -o StrictHostKeyChecking=no -o BatchMode=yes" \
    "root@$host:/workspace/sd1/out/" "$OUT/out/$pod/" >>"$LOG" 2>&1
  rc2=$?
  rsync -az --timeout=60 -e "ssh -i $KEY -p $port -o ConnectTimeout=10 -o StrictHostKeyChecking=no -o BatchMode=yes" \
    "root@$host:/workspace/sd1/logs/" "$OUT/logs/$pod/" >>"$LOG" 2>&1
  n=$(find "$OUT/out/$pod" -name scores.json 2>/dev/null | wc -l | tr -d ' ')
  f=$(find "$OUT/mpnn/$pod" -name '*.fa' 2>/dev/null | wc -l | tr -d ' ')
  echo "  $pod mpnn_rc=$rc1 out_rc=$rc2 fastas=$f scored=$n" >>"$LOG"
  echo "$pod fastas=$f scored=$n"
done
