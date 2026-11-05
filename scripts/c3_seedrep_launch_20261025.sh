#!/bin/bash
# Launch the outcome-blind seed-replication arm (Astra 03:52/04:08 ruling).
# Refuses unless the manifest, input, per-pod slices and runner all match their hashes,
# and refuses before the arm's own 07:00 ET admission stop.
# usage: c3_seedrep_launch_20261025.sh [--dry-run] [p1 ...]
set -euo pipefail
cd "$(dirname "$0")/.." || exit 1
KEY=$HOME/.ssh/runpod_ed25519
SR=results/c3_seed_replication_v1_20261025
RUNNER=$SR/pod/pod_run_seed.py
WRAPPER=$PWD/scripts/c3_seedrep_pod_run.sh
CAP=2
ADMIT=1792926000     # 07:00 ET 2026-10-25
DRY=0; [ "${1:-}" = "--dry-run" ] && { DRY=1; shift; }
# Two launchers (pipeline + autopilot) must never stage/launch the same pod concurrently.
# Portable atomic mkdir lock; released on any exit. A stale lock older than 15 min is broken.
LAUNCH_LOCK=/tmp/seedrep_launch.lock.d
if ! mkdir "$LAUNCH_LOCK" 2>/dev/null; then
  if [ -n "$(find "$LAUNCH_LOCK" -maxdepth 0 -mmin +15 2>/dev/null)" ]; then
    rm -rf "$LAUNCH_LOCK"; mkdir "$LAUNCH_LOCK" 2>/dev/null || { echo "SEEDREP_LAUNCH_LOCK_BUSY"; exit 0; }
  else
    echo "SEEDREP_LAUNCH_LOCK_BUSY"; exit 0
  fi
fi
trap 'rm -rf "$LAUNCH_LOCK"' EXIT INT TERM
pods=("$@"); [ ${#pods[@]} -gt 0 ] || pods=(p1 p2 p3 p4 p5)
spec_of() { case $1 in p1) echo 63.141.33.138:22113;; p2) echo 194.68.245.32:22065;;
  p3) echo 69.30.85.102:22129;; p4) echo 194.68.245.69:22022;;
  p5) echo 194.68.245.147:22117;; *) return 1;; esac; }

NOW=$(date +%s)
[ "$NOW" -lt "$ADMIT" ] || { echo "SEEDREP_PAST_ADMISSION_CUTOFF now=$NOW cutoff=$ADMIT"; exit 4; }
echo "SEEDREP_LAUNCH admit=$ADMIT now=$NOW remaining=$(( ADMIT - NOW ))s"

python3 - "$SR" <<'PY'
import hashlib, json, pathlib, sys
sr = pathlib.Path(sys.argv[1])
m = json.loads((sr / 'manifest.json').read_text())
assert m['arm'] == 'c3_seed_replication_v1_20261025', 'wrong arm'
assert m['selection_is_outcome_blind'] is True, 'cohort not outcome-blind'
assert m['n_jobs'] == 160 and m['cap_invocations'] == 160 and m['retries'] == 0, 'cap/retry mismatch'
assert len(m['cohort']) == 80 and len(set(m['cohort'])) == 80, 'cohort size'
# cohort hash must match the frozen ruling
h = hashlib.sha256('\n'.join(m['cohort']).encode()).hexdigest()
assert h == m['cohort_sha256'], 'cohort hash drifted'
assert h == 'dd4abef292b3fdc61f9e3e1864cacac4c59f730bb580cec0bc941c99d08e007c', 'cohort != ruling'
# every job must carry a real seed; both seeds must appear 80 times each
seeds = {}
for j in m['jobs']:
    seeds[str(j['seed'])] = seeds.get(str(j['seed']), 0) + 1
assert seeds == {'20261030': 80, '20261031': 80}, f'seed counts {seeds}'
print('SEEDREP_MANIFEST_OK cohort=%d jobs=%d seeds=%s' % (len(m['cohort']), m['n_jobs'], seeds))
PY

for p in "${pods[@]}"; do
  spec=$(spec_of "$p"); host=${spec%%:*}; port=${spec#*:}
  [ -s "$SR/per_pod/$p.csv" ] || { echo "SEEDREP_MISSING_POD_CSV $p"; exit 4; }
  RSYNC=(rsync -az -e "ssh -i $KEY -p $port -o StrictHostKeyChecking=no -o ConnectTimeout=15 -o BatchMode=yes")
  ssh -n -i "$KEY" -o StrictHostKeyChecking=no -o ConnectTimeout=15 -p "$port" root@$host \
    'mkdir -p /workspace/seedrep/out /workspace/seedrep/logs' || exit 5
  if [ "$DRY" = 1 ]; then echo "DRY $p rows=$(($(wc -l < "$SR/per_pod/$p.csv") - 1))"; continue; fi
  "${RSYNC[@]}" "$SR/per_pod/$p.csv" root@$host:/workspace/seedrep/input.csv || exit 5
  "${RSYNC[@]}" "$RUNNER" root@$host:/workspace/pod_run_seed.py || exit 5
  "${RSYNC[@]}" "$WRAPPER" root@$host:/workspace/seedrep/seedrep_pod_run.sh || exit 5
  ssh -n -i "$KEY" -o StrictHostKeyChecking=no -o ConnectTimeout=15 -p "$port" root@$host \
    'chmod +x /workspace/seedrep/seedrep_pod_run.sh' || exit 5
  lsha=$(shasum -a 256 "$SR/per_pod/$p.csv" | cut -d' ' -f1)
  rsha=$(ssh -n -i "$KEY" -o StrictHostKeyChecking=no -o ConnectTimeout=15 -p "$port" root@$host \
    'sha256sum /workspace/seedrep/input.csv | cut -d" " -f1') || exit 5
  [ "$lsha" = "$rsha" ] || { echo "SEEDREP_INPUT_SHA_MISMATCH $p"; exit 5; }
  for pair in "$RUNNER:/workspace/pod_run_seed.py" "$WRAPPER:/workspace/seedrep/seedrep_pod_run.sh"; do
    l=${pair%%:*}; r=${pair#*:}
    rsha=$(ssh -n -i "$KEY" -o StrictHostKeyChecking=no -o ConnectTimeout=15 -p "$port" root@$host \
      "sha256sum $r | cut -d' ' -f1") || exit 5
    [ "$rsha" = "$(shasum -a 256 "$l" | cut -d' ' -f1)" ] || { echo "SEEDREP_RUNNER_SHA_MISMATCH $p $r"; exit 5; }
  done
  echo "SEEDREP_STAGED $p rows=$(($(wc -l < "$SR/per_pod/$p.csv") - 1))"
done
[ "$DRY" = 1 ] && exit 0

for p in "${pods[@]}"; do
  spec=$(spec_of "$p"); host=${spec%%:*}; port=${spec#*:}
  ssh -n -i "$KEY" -o StrictHostKeyChecking=no -o ConnectTimeout=20 -p "$port" root@$host \
    "if ps -eo pid=,args= | awk '\$2==\"bash\" && \$3==\"/workspace/seedrep/seedrep_pod_run.sh\" {f=1} END{exit !f}'; then echo SEEDREP_ALREADY_RUNNING_$p; else touch /root/keepalive; setsid nohup bash /workspace/seedrep/seedrep_pod_run.sh /workspace/seedrep/input.csv ALL /workspace/seedrep/out $CAP $ADMIT > /workspace/seedrep/logs/par_${p}.log 2>&1 < /dev/null & echo SEEDREP_LAUNCHED_${p}; fi" || exit 5
done
