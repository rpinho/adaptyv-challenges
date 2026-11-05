#!/bin/bash
# Launch the sampling-depth arm's frozen AF2M screen, one slice per pod, N=2 per pod.
# Refuses unless the arm manifest, the final input and each pod's slice all match hashes.
# usage: c3_sd_screen_launch_20261025.sh [--dry-run] [p1 ...]
set -euo pipefail
cd "$(dirname "$0")/.." || exit 1
KEY=$HOME/.ssh/runpod_ed25519
SD=results/c3_sampling_depth_v1_20261025
RUNNER=scripts/pod_run_par_20261025.py
WRAPPER=$PWD/scripts/c3_sd_pod_run_par.sh
CAP=2
DRY=0; [ "${1:-}" = "--dry-run" ] && { DRY=1; shift; }
pods=("$@"); [ ${#pods[@]} -gt 0 ] || pods=(p1 p2 p3 p4 p5)
spec_of() { case $1 in p1) echo 63.141.33.138:22113;; p2) echo 194.68.245.32:22065;;
  p3) echo 69.30.85.102:22129;; p4) echo 194.68.245.69:22022;;
  p5) echo 194.68.245.147:22117;; *) return 1;; esac; }

CUTOFF=$(python3 -c "import json;print(json.load(open('$SD/af2m_manifest.json'))['admission_cutoff_epoch'])")
HARD=$(python3 -c "import json;print(json.load(open('$SD/af2m_manifest.json'))['hard_stop_epoch'])")
NOW=$(date +%s)
[ "$NOW" -lt "$CUTOFF" ] || { echo "SD_PAST_ADMISSION_CUTOFF now=$NOW cutoff=$CUTOFF"; exit 4; }
echo "SD_LAUNCH cutoff=$CUTOFF hard=$HARD now=$NOW remaining=$(( CUTOFF - NOW ))s"
python3 - "$SD" <<'PY'
import hashlib,json,pathlib,sys
sd=pathlib.Path(sys.argv[1])
m=json.loads((sd/'af2m_manifest.json').read_text())
h=hashlib.sha256((sd/'af2m_input.csv').read_bytes()).hexdigest()
assert h==m['input_sha256'], 'final input changed since manifest'
assert m['n_eligible']<=240, 'cap'
print('SD_INPUT_OK', h[:12], m['n_eligible'])
PY

for p in "${pods[@]}"; do
  spec=$(spec_of "$p"); host=${spec%%:*}; port=${spec#*:}
  [ -s "$SD/af2m_inputs/$p.csv" ] || { echo "SD_MISSING_POD_CSV $p"; exit 4; }
  RSYNC=(rsync -az -e "ssh -i $KEY -p $port -o StrictHostKeyChecking=no -o ConnectTimeout=15 -o BatchMode=yes")
  ssh -n -i "$KEY" -o StrictHostKeyChecking=no -o ConnectTimeout=15 -p "$port" root@$host \
    'mkdir -p /workspace/sd1/out /workspace/sd1/logs' || exit 5
  if [ "$DRY" = 1 ]; then echo "DRY $p $(wc -l < "$SD/af2m_inputs/$p.csv") rows"; continue; fi
  "${RSYNC[@]}" "$SD/af2m_inputs/$p.csv" root@$host:/workspace/sd1/input.csv || exit 5
  "${RSYNC[@]}" "$RUNNER" root@$host:/workspace/pod_run_par.py || exit 5
  "${RSYNC[@]}" "$WRAPPER" root@$host:/workspace/sd1/sd_pod_run_par.sh || exit 5
  ssh -n -i "$KEY" -o StrictHostKeyChecking=no -o ConnectTimeout=15 -p "$port" root@$host \
    'chmod +x /workspace/sd1/sd_pod_run_par.sh' || exit 5
  lsha=$(shasum -a 256 "$SD/af2m_inputs/$p.csv" | cut -d' ' -f1)
  rsha=$(ssh -n -i "$KEY" -o StrictHostKeyChecking=no -o ConnectTimeout=15 -p "$port" root@$host \
    'sha256sum /workspace/sd1/input.csv | cut -d" " -f1') || exit 5
  [ "$lsha" = "$rsha" ] || { echo "SD_INPUT_SHA_MISMATCH $p"; exit 5; }
  for pair in "$RUNNER:/workspace/pod_run_par.py" "$WRAPPER:/workspace/sd1/sd_pod_run_par.sh"; do
    l=${pair%%:*}; r=${pair#*:}
    rsha=$(ssh -n -i "$KEY" -o StrictHostKeyChecking=no -o ConnectTimeout=15 -p "$port" root@$host \
      "sha256sum $r | cut -d' ' -f1") || exit 5
    [ "$rsha" = "$(shasum -a 256 "$l" | cut -d' ' -f1)" ] || { echo "SD_RUNNER_SHA_MISMATCH $p $r"; exit 5; }
  done
  echo "SD_STAGED $p rows=$(($(wc -l < "$SD/af2m_inputs/$p.csv") - 1))"
done
[ "$DRY" = 1 ] && exit 0

for p in "${pods[@]}"; do
  spec=$(spec_of "$p"); host=${spec%%:*}; port=${spec#*:}
  ssh -n -i "$KEY" -o StrictHostKeyChecking=no -o ConnectTimeout=20 -p "$port" root@$host \
    "if ps -eo pid=,args= | awk '\$2==\"bash\" && \$3==\"/workspace/sd1/sd_pod_run_par.sh\" {f=1} END{exit !f}'; then echo SD_ALREADY_RUNNING_$p; else touch /root/keepalive; setsid nohup bash /workspace/sd1/sd_pod_run_par.sh /workspace/sd1/input.csv ALL /workspace/sd1/out $CAP $CUTOFF > /workspace/sd1/logs/par_${p}.log 2>&1 < /dev/null & echo SD_LAUNCHED_${p}; fi" || exit 5
done
