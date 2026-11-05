#!/bin/bash
# E3 stage 2: ProteinMPNN 2 seq/backbone on every recovered E3 backbone, on p4.
# Identical MPNN settings to round 2 (v_48_020, temp 0.1, seed 20261028, batch 1, chain A).
# Writes ONLY under /workspace/e3_mpnn on the pod. Read-only w.r.t. every frozen artifact.
set -uo pipefail
KEY=$HOME/.ssh/runpod_ed25519
HOST=194.68.245.69; PORT=22022
SSH="ssh -n -i $KEY -o StrictHostKeyChecking=no -o ConnectTimeout=10 -o BatchMode=yes -p $PORT root@$HOST"
SCP="scp -q -i $KEY -o StrictHostKeyChecking=no -o ConnectTimeout=10 -P $PORT"

$SSH 'mkdir -p /workspace/e3_mpnn/in /workspace/e3_mpnn/out /workspace/e3_mpnn/logs' || exit 2
# Recover every pulled backbone first. RFD4 nests its CIF under
# <backbone>/inference_samples/<tag>/..., so the backbone name is the directory
# directly below the pod root, not the CIF's parent directory.
python3 - <<'PY'
import pathlib, re, shutil, sys
root = pathlib.Path("results/c3_e3_111_20261025/pulled")
out = pathlib.Path("results/c3_e3_111_20261025/backbone_pdb")
out.mkdir(parents=True, exist_ok=True)
seen, conflicts = {}, []
for cif in sorted(root.rglob("*_generated.cif")):
    parts = [p for p in cif.relative_to(root).parts if re.match(r"e3_(ctrl|subA|subB)_", p)]
    if len(parts) != 1:
        print(f"UNRECOGNISED {cif}", file=sys.stderr)
        sys.exit(5)
    bb = parts[0]
    if bb in seen:
        conflicts.append((bb, seen[bb], cif))
        continue
    seen[bb] = cif
if conflicts:
    for row in conflicts:
        print("CONFLICT", row, file=sys.stderr)
    sys.exit(6)
for bb, cif in sorted(seen.items()):
    dst = out / f"{bb}.cif"
    if not dst.exists() or dst.stat().st_size != cif.stat().st_size:
        shutil.copy2(cif, dst)
print(f"synced {len(seen)} backbones -> {out}")
PY
[ $? -eq 0 ] || exit 7
# CIF -> PDB is already available on p4 as cif_to_pdb_20261025.py (Bio.PDB, heavy atoms only)
for f in results/c3_e3_111_20261025/backbone_pdb/*.cif; do
  [ -e "$f" ] || continue
  $SCP "$f" root@$HOST:/workspace/e3_mpnn/in/ || { echo "scp FAIL $f"; exit 3; }
done
$SSH 'cd /workspace/e3_mpnn/in && for c in *.cif; do b=${c%.cif}; [ -f /workspace/e3_mpnn/$b.pdb ] || /workspace/af2m/venv/bin/python /workspace/cif_to_pdb_20261025.py "$c" "/workspace/e3_mpnn/$b.pdb" >/dev/null 2>&1; done; ls /workspace/e3_mpnn/*.pdb 2>/dev/null | wc -l'
$SSH 'cat > /workspace/e3_mpnn/run_all.sh <<"EOS"
set -uo pipefail
cd /workspace/e3_mpnn
for p in *.pdb; do
  b=${p%.pdb}
  [ -d "out/$b" ] && { echo "$(date -Is) SKIP $b" >> logs/manifest.txt; continue; }
  t0=$(date +%s)
  bash /workspace/mpnn_run.sh "$PWD/$p" "$PWD/out/$b" > "logs/$b.log" 2>&1
  rc=$?
  echo "$(date -Is) $b rc=$rc elapsed_s=$(( $(date +%s) - t0 ))" >> logs/manifest.txt
done
echo "$(date -Is) MPNN_DONE" >> logs/manifest.txt
EOS
chmod +x /workspace/e3_mpnn/run_all.sh; echo staged'
