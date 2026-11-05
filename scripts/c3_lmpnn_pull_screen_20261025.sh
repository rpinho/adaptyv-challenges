#!/bin/bash
# Pull the LigandMPNN pilot AF2M artifacts from p1/p2/p4/p5 (READ-ONLY on pods).
# Writes to ONE flat directory per pod so no design name can be silently shadowed
# (the E3 duplicate-artifact lesson). Never touches frozen v6/v7/v8.
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1
KEY=$HOME/.ssh/runpod_ed25519
OUT=results/c3_e3_ligandmpnn_20261025/screen
LOG=results/c3_e3_ligandmpnn_20261025/pull.log
mkdir -p "$OUT"
: >"$LOG"
for spec in "p1:63.141.33.138:22113" "p2:194.68.245.32:22065" \
            "p4:194.68.245.69:22022" "p5:194.68.245.147:22117"; do
  pod=${spec%%:*}; rest=${spec#*:}; host=${rest%%:*}; port=${rest##*:}
  mkdir -p "$OUT/$pod"
  rsync -az --timeout=90 \
    -e "ssh -i $KEY -p $port -o ConnectTimeout=10 -o StrictHostKeyChecking=no -o BatchMode=yes" \
    "root@$host:/workspace/lmp_screen_out/" "$OUT/$pod/" >>"$LOG" 2>&1
  rc=$?
  n=$(find "$OUT/$pod" -name scores.json 2>/dev/null | wc -l | tr -d ' ')
  e=$(find "$OUT/$pod" -name error.json 2>/dev/null | wc -l | tr -d ' ')
  echo "$pod rsync_rc=$rc scored=$n errors=$e" >>"$LOG"
done
echo "pilot pull: $(find "$OUT" -name scores.json | wc -l | tr -d ' ')/24 scored"
