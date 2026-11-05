#!/bin/bash
# Launch the frozen R3 AF2M screen on each pod's own slice. READ-ONLY on the pods.
# Refuses to launch unless the frozen input matches its manifest and every pod has
# exactly one driver. Usage: c3_r3_screen_launch_20261025.sh [--dry-run] [p1 ...]
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1
KEY=$HOME/.ssh/runpod_ed25519
R3=results/c3_r3_20261025
WRAPPER=/workspace/r3_pod_run.sh
RUNNER=/workspace/r3_screen/c3_r3_pod_run.py
DRY=0; [ "${1:-}" = "--dry-run" ] && { DRY=1; shift; }
pods=("$@"); [ ${#pods[@]} -gt 0 ] || pods=(p1 p2 p3 p4 p5)
spec_of() { case $1 in p1) echo 63.141.33.138:22113;; p2) echo 194.68.245.32:22065;;
  p3) echo 69.30.85.102:22129;; p4) echo 194.68.245.69:22022;;
  p5) echo 194.68.245.147:22117;; *) return 1;; esac; }

[ -s "$R3/screen_input_20261025.csv" ] || { echo MISSING_SCREEN_INPUT; exit 4; }
python3 - "$R3" <<'PY' || exit 4
import hashlib, json, pathlib, sys
r3 = pathlib.Path(sys.argv[1])
m = json.loads((r3 / 'screen_input_manifest_20261025.json').read_text())
b = (r3 / 'screen_input_20261025.csv').read_bytes()
assert hashlib.sha256(b).hexdigest() == m['input_sha256'], 'screen input changed since build'
print('SCREEN_INPUT_OK', m['input_sha256'])
PY

for p in "${pods[@]}"; do
  spec=$(spec_of "$p") || { echo "UNKNOWN_POD $p"; exit 4; }
  host=${spec%%:*}; port=${spec#*:}
  [ -s "$R3/screen_inputs/$p.csv" ] || { echo "MISSING_POD_CSV $p"; exit 4; }
  # grep -c exits 1 when the count is zero; that is a healthy "not running" answer,
  # not an SSH failure. Keep genuine SSH errors fatal.
  n=$(ssh -n -i "$KEY" -o StrictHostKeyChecking=no -o ConnectTimeout=15 -p "$port" root@$host \
      "mkdir -p /workspace/r3_screen/out /workspace/r3_screen/logs; c=\$(ps -eo args= | grep -Ec '^bash (/workspace/pod_run.sh|/workspace/r3_pod_run.sh|/workspace/r3_pod_run_par.sh) /workspace/r3_screen/input.csv' || true); c2=\$(ps -eo args= | grep -Ec '^[^ ]*python[^ ]* .*/pod_run_par[[:alnum:]_]*\\.py /workspace/r3_screen/input.csv' || true); echo \$((c+c2))" 2>/dev/null) || exit 5
  if [ "${n:-0}" -gt 0 ]; then echo "SCREEN_ALREADY_RUNNING $p"; continue; fi
  if [ "$DRY" = 1 ]; then echo "DRY $p $(wc -l < "$R3/screen_inputs/$p.csv") rows"; continue; fi
  RSYNC=(rsync -az -e "ssh -i $KEY -p $port -o StrictHostKeyChecking=no -o ConnectTimeout=15 -o BatchMode=yes")
  "${RSYNC[@]}" "$R3/screen_inputs/$p.csv" root@$host:/workspace/r3_screen/input.csv || exit 5
  "${RSYNC[@]}" scripts/c3_r3_pod_run.py root@$host:"$RUNNER" || exit 5
  "${RSYNC[@]}" scripts/c3_r3_pod_run.sh root@$host:"$WRAPPER" || exit 5
  rsha=$(ssh -n -i "$KEY" -o StrictHostKeyChecking=no -o ConnectTimeout=15 -p "$port" root@$host \
    "sha256sum /workspace/r3_screen/input.csv | cut -d' ' -f1") || exit 5
  lsha=$(sha256sum "$R3/screen_inputs/$p.csv" | cut -d' ' -f1)
  [ "$rsha" = "$lsha" ] || { echo "SCREEN_INPUT_SHA_MISMATCH $p"; exit 5; }
  for pair in "scripts/c3_r3_pod_run.py:$RUNNER" "scripts/c3_r3_pod_run.sh:$WRAPPER"; do
    l=${pair%%:*}; r=${pair#*:}
    rsha=$(ssh -n -i "$KEY" -o StrictHostKeyChecking=no -o ConnectTimeout=15 -p "$port" root@$host \
      "sha256sum $r | cut -d' ' -f1") || exit 5
    [ "$rsha" = "$(sha256sum "$l" | cut -d' ' -f1)" ] || { echo "R3_RUNNER_SHA_MISMATCH $p $r"; exit 5; }
  done
  ssh -n -i "$KEY" -o StrictHostKeyChecking=no -o ConnectTimeout=15 -p "$port" root@$host \
    "chmod +x $WRAPPER; setsid nohup bash $WRAPPER /workspace/r3_screen/input.csv ALL /workspace/r3_screen/out > /workspace/r3_screen/logs/screen_${p}.log 2>&1 < /dev/null & echo LAUNCHED_R3_SCREEN_${p}_PID=\$!" || exit 5
done
