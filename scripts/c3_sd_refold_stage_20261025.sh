#!/bin/bash
# Stage the sampling-depth arm's eligible sequences to p3's validated ESMFold env and run the
# refold filter. Mirrors the R3 refold path exactly; read-only w.r.t. frozen artifacts.
set -euo pipefail
cd "$(dirname "$0")/.." || exit 1
KEY=$HOME/.ssh/runpod_ed25519
HOST=69.30.85.102; PORT=22129
SD=results/c3_sampling_depth_v1_20261025
SSH="ssh -n -i $KEY -o StrictHostKeyChecking=no -o ConnectTimeout=15 -o BatchMode=yes -p $PORT root@$HOST"
[ -s "$SD/sequences.csv" ] || { echo MISSING_SD_SEQUENCES; exit 4; }
python3 - "$SD/sequences.csv" <<'PY'
import csv,sys
rows=list(csv.DictReader(open(sys.argv[1])))
elig=[r for r in rows if r['eligible']=='True']
print(f'SD_REFOLD_INPUT eligible={len(elig)} of {len(rows)}')
assert elig, 'no eligible designs'
PY
$SSH 'mkdir -p /workspace/sd1/esm /workspace/sd1/logs; test -x /workspace/esmenv/bin/python; test -s /workspace/esm_run.sh'
# ESMFold consumes (name, sequence); eligibility already applied by the builder.
python3 - "$SD/sequences.csv" "$SD/refold_input.csv" <<'PY'
import csv,sys
rows=[r for r in csv.DictReader(open(sys.argv[1])) if r['eligible']=='True']
with open(sys.argv[2],'w',newline='') as fh:
    w=csv.DictWriter(fh,fieldnames=['name','sequence']); w.writeheader()
    for r in rows: w.writerow({'name':r['name'],'sequence':r['sequence']})
print(f'SD_REFOLD_CSV {len(rows)} rows')
PY
rsync -az -e "ssh -i $KEY -p $PORT -o StrictHostKeyChecking=no -o ConnectTimeout=15 -o BatchMode=yes" \
  "$SD/refold_input.csv" root@$HOST:/workspace/sd1/refold_input.csv
$SSH "if ps -eo pid=,args= | awk '\$2==\"bash\" && \$3==\"/workspace/esm_run.sh\" && \$4==\"/workspace/sd1/refold_input.csv\" {found=1} END{exit !found}'; then echo SD_REFOLD_ALREADY_RUNNING; else touch /root/keepalive; setsid nohup bash /workspace/esm_run.sh /workspace/sd1/refold_input.csv ALL /workspace/sd1/esm > /workspace/sd1/logs/esm_sd.log 2>&1 < /dev/null & echo LAUNCHED_SD_REFOLD; fi"
