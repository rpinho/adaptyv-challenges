#!/usr/bin/env bash
# Positive pod evidence of which designs had STARTED, captured around quiesce.
# A design counts as started if any of: an output dir exists, a .claims entry names it, or a
# records/*.json names it. Read-only on the pods.
# Writes results/c3_sampling_depth_v1_20261025/cutoff_snapshot.json (needs --force to replace).
set -euo pipefail
cd "$(dirname "$0")/.."
SD=results/c3_sampling_depth_v1_20261025
OUT=$SD/cutoff_snapshot.json
if [ -e "$OUT" ] && [ "${1:-}" != "--force" ]; then echo "snapshot exists: $OUT (use --force)"; exit 0; fi
pairs="p1:63.141.33.138:22113 p2:194.68.245.32:22065 p3:69.30.85.102:22129 p4:194.68.245.69:22022 p5:194.68.245.147:22117"

REMOTE='
import json, os, pathlib
base = pathlib.Path("/workspace/sd1/out")
names = set()
for p in base.iterdir():
    if p.is_dir() and not p.name.startswith(".") and p.name not in ("queue", "records", "failures"):
        names.add(p.name)
for p in (base / ".claims").glob("*"):
    try:
        names.add(json.loads(p.read_text()).get("name"))
    except Exception:
        pass
for p in (base / "records").glob("*.json"):
    try:
        d = json.loads(p.read_text())
        names.add(d.get("design_id") or d.get("name"))
    except Exception:
        pass
names.discard(None)
print(json.dumps(sorted(names)))
'

tmp=$(mktemp -d); trap 'rm -rf "$tmp"' EXIT
for x in $pairs; do
  name=${x%%:*}; rest=${x#*:}; ip=${rest%%:*}; port=${rest#*:}
  if ! timeout 60 ssh -i ~/.ssh/runpod_ed25519 -p "$port" -o StrictHostKeyChecking=no \
       -o ConnectTimeout=15 root@"$ip" "python3 -c '$REMOTE'" > "$tmp/$name.json" 2>"$tmp/$name.err"; then
    echo "SSH FAILED $name"; cat "$tmp/$name.err"; exit 4
  fi
  echo "$name started=$(python3 -c "import json,sys;print(len(json.load(open('$tmp/$name.json'))))")"
done

python3 - "$tmp" "$OUT" <<'PY'
import json, pathlib, sys, datetime
tmp, out = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
pods = {}
for p in sorted(tmp.glob('p*.json')):
    pods[p.stem] = {'started': json.loads(p.read_text())}
doc = {'generated_at': datetime.datetime.now().astimezone().isoformat(timespec='seconds'),
       'rule': 'started = output dir OR .claims entry OR records/*.json entry, read on the pod',
       'pods': pods}
out.write_text(json.dumps(doc, indent=1) + '\n')
print('wrote', out, {k: len(v['started']) for k, v in pods.items()})
PY
