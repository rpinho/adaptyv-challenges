#!/bin/bash
# Sampling-depth arm stage 1 dispatcher: stage each pod's own 24 backbones + runner, verify every
# hash, then launch the two extra MPNN draws. Read-only w.r.t. frozen artifacts.
# usage: c3_sd_stage_20261025.sh [p1 ... p5]
set -euo pipefail
cd "$(dirname "$0")/.." || exit 1
KEY=$HOME/.ssh/runpod_ed25519
SD=results/c3_sampling_depth_v1_20261025
BB=results/c3_r3_20261025/backbone_pdb
MAN=$SD/manifest.json
PODRUN=$PWD/scripts/c3_sd_mpnn_pod_20261025.sh
MPNNRUN=$PWD/scripts/c3_sd_mpnn_run_20261025.sh
spec_of() { case $1 in p1) echo 63.141.33.138:22113;; p2) echo 194.68.245.32:22065;;
  p3) echo 69.30.85.102:22129;; p4) echo 194.68.245.69:22022;;
  p5) echo 194.68.245.147:22117;; *) return 1;; esac; }
pods=("$@"); [ ${#pods[@]} -gt 0 ] || pods=(p1 p2 p3 p4 p5)
[ -s "$MAN" ] || { echo MISSING_MANIFEST; exit 4; }

python3 - "$MAN" <<'PY'
import json,sys
m=json.load(open(sys.argv[1]))
assert m['n_backbones']==120 and m['draws_per_backbone']==2, 'manifest shape'
assert m['n_slots_max']==240, 'slot count'
assert m['mpnn']['seed']==20261029, 'seed'
assert m['af2m']['unchanged'] and m['gate']['unchanged'], 'unchanged settings'
assert m['caps']['max_af2m_admissions']==240, 'cap'
print('MANIFEST_OK', m['slots_sha256'][:12])
PY

for p in "${pods[@]}"; do
  spec=$(spec_of "$p")
  host=${spec%%:*}; port=${spec#*:}
  RSYNC=(rsync -az -e "ssh -i $KEY -p $port -o StrictHostKeyChecking=no -o ConnectTimeout=15 -o BatchMode=yes")
  ssh -n -i "$KEY" -o StrictHostKeyChecking=no -o ConnectTimeout=15 -p "$port" root@$host \
    'mkdir -p /workspace/sd1/pdb /workspace/sd1/mpnn /workspace/sd1/logs' || exit 5
  "${RSYNC[@]}" "$PODRUN" root@$host:/workspace/sd1/mpnn_pod_sd.sh || exit 5
  "${RSYNC[@]}" "$MPNNRUN" root@$host:/workspace/sd1/mpnn_run_sd.sh || exit 5
  for pair in "$PODRUN:/workspace/sd1/mpnn_pod_sd.sh" "$MPNNRUN:/workspace/sd1/mpnn_run_sd.sh"; do
    l=${pair%%:*}; r=${pair#*:}
    rsha=$(ssh -n -i "$KEY" -o StrictHostKeyChecking=no -o ConnectTimeout=15 -p "$port" root@$host \
      "sha256sum $r | cut -d' ' -f1")
    [ "$rsha" = "$(sha256sum "$l" | cut -d' ' -f1)" ] || { echo "SD_SCRIPT_SHA_MISMATCH $p $r"; exit 5; }
  done

  FILES="$SD/stage_files_$p.txt"
  python3 - "$MAN" "$p" "$BB" > "$FILES" <<'PY'
import json,sys,pathlib
m=json.load(open(sys.argv[1])); pod=sys.argv[2]; bbroot=pathlib.Path(sys.argv[3])
for b in sorted({s['backbone'] for s in m['slots'] if s['pod']==pod}):
    p=bbroot/f'{b}.pdb'
    if not p.exists():
        sys.exit(f'missing {p}')
    print(p)
PY
  nfiles=$(wc -l < "$FILES" | tr -d ' ')
  echo "$p backbones=$nfiles"
  [ "$nfiles" = 24 ] || { echo "SD_EXPECTED_24_BACKBONES $p"; exit 4; }
  files=(); while IFS= read -r line; do files+=("$line"); done < "$FILES"
  [ ${#files[@]} = 24 ] || { echo "SD_FILE_ARRAY_BAD $p ${#files[@]}"; exit 4; }
  "${RSYNC[@]}" "${files[@]}" root@$host:/workspace/sd1/pdb/ || exit 5

  python3 - "$MAN" "$p" "$host" "$port" "$KEY" <<'PY'
import json,sys,subprocess
man,pod,host,port,key=sys.argv[1:6]
m=json.load(open(man))
want={s['backbone']:s['backbone_pdb_sha256'] for s in m['slots'] if s['pod']==pod}
cmd=['ssh','-n','-i',key,'-o','StrictHostKeyChecking=no','-o','ConnectTimeout=15','-p',port,
     f'root@{host}','cd /workspace/sd1/pdb && sha256sum *.pdb']
out=subprocess.run(cmd,capture_output=True,text=True)
if out.returncode!=0:
    print('SD_HASH_SSH_FAIL',out.stderr[-300:]); sys.exit(5)
got={l.split()[1].removesuffix('.pdb'):l.split()[0] for l in out.stdout.splitlines() if l.strip()}
bad=[b for b,h in want.items() if got.get(b)!=h]
print(f'  {pod} pod_hashes={len(got)}/{len(want)} mismatched={len(bad)} {bad[:3]}')
sys.exit(5 if bad or len(got)!=len(want) else 0)
PY
done

for p in "${pods[@]}"; do
  spec=$(spec_of "$p"); host=${spec%%:*}; port=${spec#*:}
  ssh -n -i "$KEY" -o StrictHostKeyChecking=no -o ConnectTimeout=15 -p "$port" root@$host \
    "if ps -eo pid=,args= | awk -v p='$p' '\$2==\"bash\" && \$3==\"/workspace/sd1/mpnn_pod_sd.sh\" && \$4==p {found=1} END{exit !found}'; then echo SD_MPNN_ALREADY_RUNNING_$p; else touch /root/keepalive; setsid nohup bash /workspace/sd1/mpnn_pod_sd.sh $p > /workspace/sd1/logs/mpnn_${p}.out 2>&1 < /dev/null & echo LAUNCHED_SD_MPNN_${p}; fi"
done
