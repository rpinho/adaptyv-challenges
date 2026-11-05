#!/bin/bash
# Pull E3 AF2M screen artifacts from all five pods. READ-ONLY on the pods.
# Never overwrites selected_20261025.json, screen_input_20261025.csv, novelty, refold,
# admission, bb_pdb, backbone_pdb, esm, mpnn, or any v6/v7/v8/E2 artifact.
# Usage: c3_e3_pull_screen_20261025.sh [--repeat N]
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1
KEY=$HOME/.ssh/runpod_ed25519
OUT=results/c3_e3_111_20261025/screen
LOG=results/c3_e3_111_20261025/screen_pull.log
mkdir -p "$OUT"
one_pass() {
  echo "=== $(date '+%F %T %Z') pull start" >>"$LOG"
  for spec in "p1:63.141.33.138:22113" "p2:194.68.245.32:22065" \
              "p3:69.30.85.102:22129" "p4:194.68.245.69:22022" \
              "p5:194.68.245.147:22117"; do
    pod=${spec%%:*}; rest=${spec#*:}; host=${rest%%:*}; port=${rest##*:}
    mkdir -p "$OUT/$pod"
    rsync -az --timeout=60 \
      -e "ssh -i $KEY -p $port -o ConnectTimeout=10 -o StrictHostKeyChecking=no -o BatchMode=yes" \
      "root@$host:/workspace/e3_screen/out/" "$OUT/$pod/" >>"$LOG" 2>&1
    rc=$?
    n=$(find "$OUT/$pod" -name scores.json 2>/dev/null | wc -l | tr -d ' ')
    e=$(find "$OUT/$pod" -name error.json 2>/dev/null | wc -l | tr -d ' ')
    echo "  $pod rsync_rc=$rc scored=$n errors=$e" >>"$LOG"
  done
  find "$OUT" -name scores.json 2>/dev/null | wc -l | tr -d ' '
}
if [ "${1:-}" = "--repeat" ]; then
  for i in $(seq 1 "${2:-24}"); do
    n=$(one_pass)
    echo "$(date '+%F %T') pass=$i scored=$n"
    [ "${n:-0}" -ge 24 ] && exit 0
    sleep 120
  done
  exit 2
fi
n=$(one_pass)
echo "screen pull done: $n/24 scored; log $LOG"
