#!/bin/bash
# Stage all 240 R3 designed sequences and run ESMFold on p3's validated esmenv.
# Usage: c3_r3_esm_stage_20261025.sh [--pull-only]
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1
KEY=$HOME/.ssh/runpod_ed25519
HOST=69.30.85.102; PORT=22129
R3=results/c3_r3_20261025
SSH="ssh -n -i $KEY -o StrictHostKeyChecking=no -o ConnectTimeout=15 -o BatchMode=yes -p $PORT root@$HOST"
[ -s "$R3/mpnn_sequences.csv" ] || { echo MISSING_MPNN_SEQUENCES; exit 4; }
[ "$(wc -l < "$R3/mpnn_sequences.csv" | tr -d ' ')" = 241 ] || { echo "EXPECTED_240_DESIGNS"; exit 4; }
$SSH 'mkdir -p /workspace/r3/esm /workspace/r3/logs; test -x /workspace/esmenv/bin/python; test -s /workspace/esm_run.sh' || exit 5
rsync -az -e "ssh -i $KEY -p $PORT -o StrictHostKeyChecking=no -o ConnectTimeout=15 -o BatchMode=yes" \
  "$R3/mpnn_sequences.csv" root@$HOST:/workspace/r3/r3_mpnn_sequences.csv || exit 5
if [ "${1:-}" != "--pull-only" ]; then
  # Match only the exact worker argv; the enclosing ssh/bash wrapper contains the
  # same path text and would otherwise self-match as ALREADY_RUNNING.
  $SSH "if ps -eo pid=,args= | awk '\$2==\"bash\" && \$3==\"/workspace/esm_run.sh\" && \$4==\"/workspace/r3/r3_mpnn_sequences.csv\" {found=1} END{exit !found}'; then echo ESM_ALREADY_RUNNING; else setsid nohup bash /workspace/esm_run.sh /workspace/r3/r3_mpnn_sequences.csv ALL /workspace/r3/esm > /workspace/r3/logs/esm_r3.log 2>&1 < /dev/null & echo LAUNCHED_ESM_PID=\$!; fi" || exit 5
fi
if [ "${1:-}" = "--pull-only" ]; then
  while true; do
    n=$($SSH 'find /workspace/r3/esm -name "*.pdb" -size +0c 2>/dev/null | wc -l' | tr -d ' ')
    echo "$(date '+%H:%M:%S') ESM $n/240"
    [ "${n:-0}" -ge 240 ] && break
    sleep 30
  done
  mkdir -p "$R3/esm"
  rsync -az --timeout=120 -e "ssh -i $KEY -p $PORT -o ConnectTimeout=15 -o BatchMode=yes" \
    root@$HOST:/workspace/r3/esm/ "$R3/esm/" || exit 5
  echo "pulled $(find "$R3/esm" -name '*.pdb' | wc -l | tr -d ' ') ESM PDBs"
fi
