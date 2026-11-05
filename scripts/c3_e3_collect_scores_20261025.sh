#!/bin/bash
# Pull E3 AF2M screen artifacts from all five pods and merge the scores into one NEW file.
# READ-ONLY on the pods. Never touches E2, v8, or any frozen artifact.
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1
KEY=$HOME/.ssh/runpod_ed25519
OUT=results/c3_e3_111_20261025/screen
mkdir -p "$OUT"
for spec in "63.141.33.138:22113:p1" "194.68.245.32:22065:p2" "69.30.85.102:22129:p3" \
            "194.68.245.69:22022:p4" "194.68.245.147:22117:p5"; do
  host=${spec%%:*}; rest=${spec#*:}; port=${rest%%:*}; pod=${rest##*:}
  rsync -az --timeout=120 \
    -e "ssh -i $KEY -p $port -o ConnectTimeout=10 -o StrictHostKeyChecking=no -o BatchMode=yes" \
    "root@$host:/workspace/e3_screen/out/" "$OUT/" || echo "WARN rsync $pod failed"
  echo "$pod pulled"
done
python3 - <<'PY'
import glob, json, pathlib
root = pathlib.Path("results/c3_e3_111_20261025/screen")
rows, missing = {}, []
import csv
want = [r["name"] for r in csv.DictReader(open("results/c3_e3_111_20261025/screen_input_20261025.csv"))]
for name in want:
    p = list(root.glob(f"*/{name}/scores.json")) or list(root.glob(f"{name}/scores.json"))
    if not p:
        missing.append(name); continue
    d = json.load(open(p[0]))
    rows[name] = {"name": name, "iptm": d.get("iptm"), "ptm": d.get("ptm"),
                  "mean_plddt": d.get("mean_plddt"), "model": d.get("model"),
                  "predictor": d.get("predictor"), "num_recycle": d.get("num_recycle"),
                  "num_models": d.get("num_models")}
out = pathlib.Path("results/c3_e3_111_20261025/screen_scores_20261025.json")
out.write_text(json.dumps({"n_scored": len(rows), "n_missing": len(missing),
                           "missing": missing, "scores": rows}, indent=1) + "\n")
print(f"scored {len(rows)}/{len(want)}; missing={missing}")
for n, v in sorted(rows.items(), key=lambda kv: -(kv[1]['iptm'] or 0)):
    print(f"  {n:34s} iptm={v['iptm']:.3f}" if v['iptm'] is not None else f"  {n}: no iptm")
PY
