#!/bin/bash
# E3 stage 3: pull MPNN sequences from p4 -> CSV -> ESMFold monomer refold on p3 (validated esmenv).
# Same ESMFold invocation as round 2 (esm_run.sh, esmfold_v1, GPU). Read-only w.r.t. frozen artifacts.
set -uo pipefail
KEY=$HOME/.ssh/runpod_ed25519
P4=194.68.245.69; P4PORT=22022
P3=69.30.85.102; P3PORT=22129
SSHP4="ssh -n -i $KEY -o StrictHostKeyChecking=no -o ConnectTimeout=10 -o BatchMode=yes -p $P4PORT root@$P4"
SSHP3="ssh -n -i $KEY -o StrictHostKeyChecking=no -o ConnectTimeout=10 -o BatchMode=yes -p $P3PORT root@$P3"
OUT=results/c3_e3_111_20261025
mkdir -p "$OUT/mpnn"

# 1) list MPNN outputs and pull the sequence FASTA files
$SSHP4 'find /workspace/e3_mpnn/out -name "seqs/*.fa" | wc -l'
$SSHP4 'cd /workspace/e3_mpnn/out && tar -cf - .' > /tmp/e3_mpnn_out.tar 2>/dev/null || { echo "pull failed"; exit 3; }
tar -xf /tmp/e3_mpnn_out.tar -C "$OUT/mpnn" || { echo "untar failed"; exit 4; }
echo "pulled $(find "$OUT/mpnn" -name '*.fa' | wc -l | tr -d ' ') fasta files"

# 2) build a name,sequence CSV (sample >0 = designed; sample 0 is the native/redesign control)
python3 - <<'PY'
import csv, pathlib, re
root = pathlib.Path("results/c3_e3_111_20261025/mpnn")
rows = []
for fa in sorted(root.glob("**/seqs/*.fa")):
    bb = fa.parent.parent.name
    name, sample = None, None
    for line in fa.read_text().splitlines():
        if line.startswith(">"):
            hdr = line[1:]
            name = hdr.split(",")[0].strip()
            m = re.search(r"sample=(\d+)", hdr)
            sample = m.group(1) if m else None
        elif line:
            # sample 0 is the NATIVE RFD4 sequence; round 2 used only sampled designs.
            if name is None or "T=" not in name or sample is None:
                continue
            rows.append({"name": f"{bb}_s{sample}", "sequence": line.strip()})
out = pathlib.Path("results/c3_e3_111_20261025/e3_mpnn_sequences.csv")
seen, dedup = set(), []
for r in rows:
    if r["name"] in seen:
        continue
    seen.add(r["name"]); dedup.append(r)
with out.open("w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=["name", "sequence"])
    w.writeheader(); w.writerows(dedup)
print(f"{len(dedup)} sequences -> {out}")
PY
