#!/usr/bin/env python3
"""SENSITIVITY ANALYSIS (evidence only): does the FILTERED challenger survive the symmetric v2 rule?

Same question as scripts/c3_challenger_robust_v2_sensitivity_20261025.py, applied to the other challenger.
The all-five-robust one swapped exactly one seat; the filtered one was built with the SAME frozen
predicate and the same 8-seat budget, so it must be tested rather than assumed.

Reproduces scripts/c3_challenger_assemble_20261025.py exactly (same pool, same gates, same ordering,
same component rule) and changes ONLY the near-identical predicate:
  frozen : cross_tm_20261025.json, tm = tm_norm_chain2, coverage = non-gap columns per sequence (dead)
  v2     : max(TM both ways), coverage = max(paired cols) / max(len_a, len_b)  [rule_v2.json]

A frozen-edge CONTROL run is executed first and must reproduce the shipped 8 seats, otherwise the
harness is wrong and no conclusion is drawn. Shipped artifacts are read-only; no CSV is written.
Writes results/c3_challenger_filtered_v2_20261025/.
"""
import csv
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / 'results/c3_challenger_filtered_v2_20261025'
V8 = ROOT / 'results/c3_submission_v8_20261025.csv'
ELIG = ROOT / 'results/c3_v8_eligibility_20261025/eligibility.json'
LEDGER = ROOT / 'results/c3_sampling_depth_v1_20261025/coverage_ledger.json'
CROSS = ROOT / 'results/c3_r3_20261025/cross_tm_20261025.json'
V2 = ROOT / 'results/c3c4_dedup_symmetry_20261025/rule_v2.json'
SHIPPED = OUT.parent / 'c3_challenger_20261025/c3_challenger_filtered_20261025.csv'
TM_MIN, COV_MIN = 0.65, 0.80
IPTM_FLOOR = 0.85


def run(edge_set):
    v8rows = list(csv.DictReader(open(V8)))
    elig = {r['name']: r for r in json.loads(ELIG.read_text())['rows']}
    ledger = json.loads(LEDGER.read_text())['rows']

    retained = [r for r in v8rows if elig[r['name']]['disposition_PROPOSED'] == 'ELIGIBLE']
    dropped = [r for r in v8rows if elig[r['name']]['disposition_PROPOSED'] != 'ELIGIBLE']
    n_seats = len(dropped)
    retained_names = [r['name'] for r in retained]

    pool = [r for r in ledger
            if r.get('status') == 'PASS' and isinstance(r.get('iptm'), (int, float))
            and r['iptm'] >= IPTM_FLOOR and r.get('refold_pass') is True]
    pool = [r for r in {r['name']: r for r in pool}.values()]

    universe = sorted(set(retained_names) | {r['backbone'] for r in pool})
    parent = {n: n for n in universe}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for a, b in edge_set:
        if a in parent and b in parent:
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[rb] = ra

    retained_comps = {find(n) for n in retained_names if n in parent}

    def clashes_retained(bb):
        # No `if v in label` guard: retained v8 rows are DESIGN names and many are not backbone keys.
        # Adding that guard silently skipped most retained rows (the bug caught in the robust harness).
        return any(tuple(sorted((bb, v))) in edge_set for v in retained_names)

    considered, chosen = [], []
    used_comps = set(retained_comps)
    for r in sorted(pool, key=lambda r: (-(r.get('iptm') or 0), r['name'])):
        bb = r['backbone']
        rec = {'name': r['name'], 'backbone': bb, 'iptm': r.get('iptm'),
               'plddt': r.get('binder_mean_plddt'), 'clashes': r.get('clashes_lt2A')}
        if clashes_retained(bb):
            rec['decision'] = 'reject: near-identical to a retained v8 row'
        elif find(bb) in used_comps:
            rec['decision'] = 'reject: component already represented in the challenger'
        else:
            rec['decision'] = 'TAKE'
            used_comps.add(find(bb))
            chosen.append(r)
        considered.append(rec)
        if len(chosen) == n_seats:
            break

    return {
        'retained': retained_names, 'seats_needed': n_seats,
        'chosen': [r['name'] for r in chosen],
        'considered': considered, 'status': 'COMPLETE' if len(chosen) == n_seats else 'INCOMPLETE',
    }


def main():
    OUT.mkdir(exist_ok=True)

    cross = json.loads(CROSS.read_text())['pairs']
    frozen_edges = set()
    for a, inner in cross.items():
        for b, rec in inner.items():
            if rec.get('tm', 0) >= TM_MIN and rec.get('coverage', 0) >= COV_MIN:
                frozen_edges.add(tuple(sorted((a, b))))
    v2_edges = {tuple(sorted(e[:2])) for e in json.loads(V2.read_text())['v2_edges_list']}

    shipped_all = [r['name'] for r in csv.DictReader(open(SHIPPED))]
    control = run(frozen_edges)
    shipped_new = shipped_all[len(control['retained']):]
    control_ok = control['chosen'] == shipped_new

    v2 = run(v2_edges)

    payload = {
        'artifact': 'SENSITIVITY ANALYSIS — evidence only; shipped filtered challenger untouched',
        'rule': 'v2 symmetric near-identical predicate; every other gate held fixed',
        'control': {
            'frozen_edges': len(frozen_edges),
            'reproduced_shipped_selection': control_ok,
            'shipped_new_seats': shipped_new,
            'control_new_seats': control['chosen'],
        },
        'v2': {
            'v2_edges': len(v2_edges),
            'seats_needed': v2['seats_needed'], 'seats_filled': len(v2['chosen']),
            'status': v2['status'], 'new_seats': v2['chosen'],
            'selection_identical': v2['chosen'] == shipped_new,
            'seats_added_vs_shipped': [n for n in v2['chosen'] if n not in shipped_new],
            'seats_dropped_vs_shipped': [n for n in shipped_new if n not in v2['chosen']],
        },
        'considered_v2': v2['considered'],
        'note': ('A different seat set is a DIFFERENT artifact and its evidence would need re-deriving. '
                 'No CSV is written here in either case.'),
    }
    (OUT / 'sensitivity.json').write_text(json.dumps(payload, indent=1) + '\n')

    print(f"CONTROL reproduced shipped: {control_ok} (frozen edges {len(frozen_edges)})")
    if not control_ok:
        print('  shipped:', shipped_new)
        print('  control:', control['chosen'])
        print('HARNESS INVALID — no v2 conclusion drawn.')
        return 1
    print(f"v2 seats {len(v2['chosen'])}/{v2['seats_needed']} status={v2['status']}")
    print(f"v2 identical to shipped: {payload['v2']['selection_identical']}")
    print(f"  added  : {payload['v2']['seats_added_vs_shipped']}")
    print(f"  dropped: {payload['v2']['seats_dropped_vs_shipped']}")
    for c in v2['considered']:
        if c['decision'] != 'TAKE':
            print(f"  {c['decision']:52s} {c['name']} (iPTM {c['iptm']})")
    return 0


if __name__ == '__main__':
    sys.exit(main())
