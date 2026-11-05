#!/bin/bash
# Pull R3 AF2M screen artifacts. READ-ONLY on the pods. Never touches frozen files.
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1
KEY=$HOME/.ssh/runpod_ed25519
OUT=results/c3_r3_20261025/screen
LOG=results/c3_r3_20261025/screen_pull.log
mkdir -p "$OUT"
echo "=== $(date '+%F %T %Z') R3 pull" >> "$LOG"
for spec in "p1:63.141.33.138:22113" "p2:194.68.245.32:22065" \
            "p3:69.30.85.102:22129" "p4:194.68.245.69:22022" \
            "p5:194.68.245.147:22117"; do
  pod=${spec%%:*}; rest=${spec#*:}; host=${rest%%:*}; port=${rest##*:}
  mkdir -p "$OUT/$pod"
  rsync -az --timeout=120 -e "ssh -i $KEY -p $port -o ConnectTimeout=10 -o StrictHostKeyChecking=no -o BatchMode=yes" \
    "root@$host:/workspace/r3_screen/out/" "$OUT/$pod/" >>"$LOG" 2>&1
  rc=$?
  n=$(find "$OUT/$pod" -name scores.json 2>/dev/null | wc -l | tr -d ' ')
  e=$(find "$OUT/$pod" -name error.json 2>/dev/null | wc -l | tr -d ' ')
  echo "  $pod rsync_rc=$rc scored=$n errors=$e" >>"$LOG"
done
python3 - <<'PY'
import csv, json, pathlib
root = pathlib.Path('results/c3_r3_20261025')
want = {r['name'] for r in csv.DictReader(open(root / 'screen_input_20261025.csv'))}
found, dup = {}, []
for sp in (root / 'screen').rglob('scores.json'):
    n = sp.parent.name
    if n in want:
        found.setdefault(n, []).append(str(sp))
raw_dup = {k: v for k, v in found.items() if len(v) > 1}
# A design can legitimately be folded twice (rebalance onto an idle pod while it was
# still in flight elsewhere). Identical iPTM is corroboration; a differing iPTM is a
# real conflict that must stop the pull. Never silently pick one.
def _iptm(path):
    try:
        return json.load(open(path)).get('iptm')
    except Exception:
        return None
dup = {}
for k, v in raw_dup.items():
    vals = [_iptm(x) for x in v]
    if len(set(vals)) == 1 and vals[0] is not None:
        continue
    dup[k] = list(zip(v, vals))
missing = sorted(want - set(found))
agree = len(raw_dup) - len(dup)
print(f'R3 pull: {len(found)}/{len(want)} scored, missing={len(missing)}, '
      f'duplicate_agreeing={agree}, duplicate_conflicting={len(dup)}')
if missing: print('  missing:', missing[:12])
for k, v in list(dup.items())[:6]: print('  CONFLICT', k, v)
if agree: print('  corroborated (identical iPTM, kept once):', sorted(set(raw_dup) - set(dup))[:6])
raise SystemExit(4 if dup else 0)
PY
