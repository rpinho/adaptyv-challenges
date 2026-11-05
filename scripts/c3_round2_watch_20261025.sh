#!/bin/bash
# Repeat the pull+verify every 5 minutes until the C3 cutoff, so incoming pod results are
# continuously and INDEPENDENTLY verified. Read-only on pods; writes only R2 artifacts.
LOG=results/c3_round2_111_20261025/watch.log
END=$(date -j -f "%Y-%m-%d %H:%M" "2026-10-25 12:00" +%s 2>/dev/null || echo $(( $(date +%s) + 43200 )))
while [ "$(date +%s)" -lt "$END" ]; do
  ./scripts/c3_round2_pull_verify_20261025.sh >/dev/null 2>&1
  python3 - <<'PY' >>"$LOG" 2>&1
import json, pathlib
p = pathlib.Path("results/c3_round2_111_20261025/round2_verify_independent.json")
d = json.loads(p.read_text())
recs = d["records"]
done = [r for r in recs if r["status"] != "incomplete"]
print(f"[{__import__('datetime').datetime.now():%H:%M:%S}] verified {len(done)}/24, "
      f"PASS {sum(1 for r in recs if r['status']=='PASS')}, "
      f"fail {sum(1 for r in recs if r['status']=='fail')}")
PY
  sleep 300
done
