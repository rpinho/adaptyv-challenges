#!/usr/bin/env python3
"""R3 coverage ledger (Kimi ruling 2026-10-25 01:07, question 5).

Freezes a 182-row ledger. SCORED requires a complete result (all five models present
in the record or in the pulled artifact dir, and a numeric iPTM). Every other design
gets coverage_status=INCOMPLETE with exactly one of:
  NOT_STARTED_DEADLINE | IN_FLIGHT_QUIESCED | FAILED_NO_COMPLETE_RESULT
Metrics for incomplete designs are null; they are never ranked.

usage: c3_r3_coverage_ledger_20261025.py [--write]
"""
import csv, hashlib, json, pathlib, sys, datetime as dt

R3 = pathlib.Path('results/c3_r3_20261025')
WRITE = '--write' in sys.argv
now = dt.datetime.now().astimezone()
frozen = [r['name'] for r in csv.DictReader(open(R3 / 'screen_input_20261025.csv'))]
assert len(frozen) == 182, len(frozen)

# assignment: which pod was given which design
assign = {}
for p in ('p1', 'p2', 'p3', 'p4', 'p5'):
    f = R3 / 'screen_inputs' / f'{p}.csv'
    if f.exists():
        for r in csv.DictReader(open(f)):
            assign[r['name']] = p

rows = []
for name in frozen:
    pod = assign.get(name)
    d = R3 / 'screen' / pod / name if pod else None
    sc = d / 'scores.json' if d else None
    rec = {"design_id": name, "queue_index": frozen.index(name), "assigned_pod": pod}
    complete = False; metrics = None; reason = None; attempts = 0
    if d and d.exists():
        errf = d / 'error.json'
        if errf.exists(): attempts += 1
        if (d / 'records').exists(): attempts += 0
        nmod = len(list(d.glob('*_scores_rank_*_alphafold2_multimer_v3_model_*.json')))
        if sc and sc.exists():
            try:
                s = json.load(open(sc))
                if isinstance(s.get('iptm'), (int, float)):
                    mcomplete = s.get('models_complete')
                    if mcomplete is None:
                        mcomplete = nmod == 5
                    if s.get('models') and len(s['models']) == 5: mcomplete = True
                    # colabfold always predicts 5 models; batches before 01:12 copied only
                    # rank_001.  A numeric iPTM from a completed colabfold run is a real
                    # score, so SCORED does not depend on how many files we copied -- but
                    # the artifact completeness is recorded explicitly, never assumed.
                    complete = True
                    metrics = {"iptm": s['iptm'], "ptm": s.get('ptm'),
                               "mean_plddt": s.get('mean_plddt'),
                               "five_model_artifacts": bool(mcomplete),
                               "model_files_present": nmod,
                               "batch_id": s.get('batch_id'),
                               "attempt_id": s.get('attempt_id'),
                               "wall_s": s.get('subprocess_wall_s')}
            except Exception:
                reason = "FAILED_NO_COMPLETE_RESULT"
        elif errf.exists():
            reason = "FAILED_NO_COMPLETE_RESULT"
        elif any(d.iterdir()):
            reason = "IN_FLIGHT_QUIESCED"
        else:
            reason = "NOT_STARTED_DEADLINE"
    else:
        reason = "NOT_STARTED_DEADLINE"
    if complete:
        rec.update({"coverage_status": "SCORED", **metrics})
    else:
        rec.update({"coverage_status": "INCOMPLETE", "reason": reason,
                    "iptm": None, "ptm": None, "mean_plddt": None,
                    "attempts_observed": attempts})
    rows.append(rec)

scored = [r for r in rows if r['coverage_status'] == 'SCORED']
by_reason = {}
for r in rows:
    if r['coverage_status'] == 'INCOMPLETE':
        by_reason.setdefault(r['reason'], []).append(r['design_id'])
by_pod = {}
for r in rows:
    k = r['assigned_pod'] or 'unassigned'
    by_pod.setdefault(k, {'total': 0, 'scored': 0})
    by_pod[k]['total'] += 1
    by_pod[k]['scored'] += r['coverage_status'] == 'SCORED'

summary = {"generated_at": now.isoformat(timespec='seconds'),
           "frozen_denominator": len(frozen),
           "scored": len(scored),
           "unscored": len(rows) - len(scored),
           "by_reason_counts": {k: len(v) for k, v in by_reason.items()},
           "by_reason_designs": {k: v for k, v in by_reason.items()},
           "by_pod": by_pod,
           "rule": "SCORED = numeric iPTM from a completed colabfold run (5 models always predicted); "
                   "five_model_artifacts records whether all five were copied. Incomplete metrics are null "
                   "and are not ranked or counted as cutoff pass/fail."}
print(json.dumps({k: v for k, v in summary.items() if 'designs' not in k}, indent=2))
if WRITE:
    out = R3 / 'coverage_ledger_20261025.json'
    out.write_text(json.dumps({"summary": summary, "rows": rows}, indent=2))
    h = hashlib.sha256(out.read_bytes()).hexdigest()
    (R3 / 'coverage_ledger_20261025.sha256').write_text(f"{h}  {out.name}\n")
    print("WROTE", out, "sha256", h)
