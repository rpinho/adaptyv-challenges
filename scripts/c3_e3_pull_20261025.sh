#!/bin/bash
# Pull E3 pilot backbones to the Mini. READ-ONLY on the pods: rsync/scp pulls only.
# Never launches or stops compute. Safe to run repeatedly; skips nothing, overwrites locally only
# under results/c3_e3_111_20261025/ (never touches E2, v6/v7/v8, or the other lane's artifacts).
# Usage: ./scripts/c3_e3_pull_20261025.sh            (one pass)
#        ./scripts/c3_e3_pull_20261025.sh --watch    (poll every 5 min; log + exit at completion)
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1
KEY=$HOME/.ssh/runpod_ed25519
OUT=results/c3_e3_111_20261025/pulled
LOG=results/c3_e3_111_20261025/pull.log
mkdir -p "$OUT"
one_pass() {
  local t0; t0=$(date '+%F %T %Z')
  echo "=== $t0 pull start" >>"$LOG"
  for spec in "63.141.33.138:22113:p1" "194.68.245.32:22065:p2" "69.30.85.102:22129:p3"; do
    host=${spec%%:*}; rest=${spec#*:}; port=${rest%%:*}; pod=${rest##*:}
    mkdir -p "$OUT/$pod"
    rsync -az --timeout=60 \
      -e "ssh -i $KEY -p $port -o ConnectTimeout=10 -o StrictHostKeyChecking=no -o BatchMode=yes" \
      "root@$host:/workspace/e3/out/" "$OUT/$pod/" >>"$LOG" 2>&1
    rsync -az --timeout=30 \
      -e "ssh -i $KEY -p $port -o ConnectTimeout=10 -o StrictHostKeyChecking=no -o BatchMode=yes" \
      "root@$host:/workspace/e3/logs/" "$OUT/$pod/logs/" >>"$LOG" 2>&1
    echo "  $pod rsync_rc=$? dirs=$(find "$OUT/$pod" -maxdepth 1 -type d 2>/dev/null | wc -l | tr -d ' ')" >>"$LOG"
  done
  local n; n=$(find "$OUT" -name '*generated.cif' 2>/dev/null | wc -l | tr -d ' ')
  echo "  total generated.cif on Mini: $n" >>"$LOG"
  echo "$n"
}
if [ "${1:-}" = "--watch" ]; then
  for i in $(seq 1 40); do
    n=$(one_pass)
    echo "$(date '+%F %T') pass=$i cif=$n"
    # 3 arms x 24 backbones = 72
    if [ "$n" -ge 72 ]; then echo "COMPLETE: $n generated.cif"; exit 0; fi
    sleep 300
  done
  echo "WATCH ENDED without 72 (last count $n)"; exit 1
fi
n=$(one_pass)
echo "pull done: $n generated.cif; log: $LOG"
# Self-terminate the launchd job once the full pilot is local, so it cannot poll forever.
if [ "$n" -ge 72 ] && [ "${1:-}" != "--watch" ]; then
  PLIST=$HOME/Library/LaunchAgents/com.ricardo.adaptyv-c3-e3-pull.plist
  if [ -f "$PLIST" ]; then
    launchctl unload "$PLIST" 2>/dev/null || true
    echo "$(date '+%F %T') COMPLETE at $n backbones; unloaded $PLIST" >>"$LOG"
  fi
fi
