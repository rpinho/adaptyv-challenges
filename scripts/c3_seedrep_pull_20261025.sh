#!/bin/bash
# Pull seed-replication artifacts from each pod. Idempotent; never touches the arm's tree.
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1
SR=results/c3_seed_replication_v1_20261025
KEY=$HOME/.ssh/runpod_ed25519
spec_of() { case $1 in p1) echo 63.141.33.138:22113;; p2) echo 194.68.245.32:22065;;
  p3) echo 69.30.85.102:22129;; p4) echo 194.68.245.69:22022;;
  p5) echo 194.68.245.147:22117;; esac; }
for p in p1 p2 p3 p4 p5; do
  s=$(spec_of "$p"); h=${s%%:*}; po=${s#*:}
  mkdir -p "$SR/out/$p"
  rsync -az --timeout=180 -e "ssh -i $KEY -p $po -o StrictHostKeyChecking=no -o ConnectTimeout=15" \
    root@"$h":/workspace/seedrep/out/ "$SR/out/$p/" 2>/dev/null
  echo "$p scored=$(ls "$SR/out/$p" 2>/dev/null | grep -vc -e '^\.' -e records -e queue -e failures || true)"
done
