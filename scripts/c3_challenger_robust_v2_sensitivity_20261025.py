#!/usr/bin/env python3
"""SENSITIVITY ANALYSIS (versioned, evidence only): does the all-five-robust challenger survive the
corrected, fully symmetric near-identical rule?

Astra's guidance: rerun as a SEPARATELY VERSIONED sensitivity analysis, never as an in-place change. The
shipped artifact at results/c3_challenger_robust_20261025/ is read-only here and is NOT modified.

Only one thing changes vs scripts/c3_challenger_robust_assemble_20261025.py: the near-identical predicate.
  shipped : frozen cross-TM matrix, chain-2 TM, per-sequence coverage (dead clause -> 1.0)
  v2      : symmetric TM AND coverage = max(paired_cols_ab, paired_cols_ba) / max(len_a, len_b)
            (edge set from scripts/dedup_rule_v2_symmetric_20261025.py, 209 edges, verified symmetric
             by construction)

Everything else is held fixed: the 12 retained v8 rows, the 8 flagged drops, the all-rules/iPTM>=0.85/
refold/5-model-clash-clean gates, the one-per-component rule and the iPTM-desc ordering.

Writes ONLY results/c3_challenger_robust_v2_20261025/ (new directory). No CSV is written unless the
selection succeeds; nothing is submitted or promoted.
"""
import csv
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
V8 = ROOT / 'results/c3_submission_v8_20261025.csv'
ELIG = ROOT / 'results/c3_v8_eligibility_20261025/eligibility.json'
LEDGER = ROOT / 'results/c3_sampling_depth_v1_20261025/coverage_ledger.json'
SEQ = ROOT / 'results/c3_sampling_depth_v1_20261025/sequences.csv'
SENS = ROOT / 'results/c3_pool_five_model_20261025/per_design.json'
V2 = ROOT / 'results/c3c4_dedup_symmetry_20261025/rule_v2.json'
SHIPPED = ROOT / 'results/c3_challenger_robust_20261025/c3_challenger_all5robust_20261025.csv'
OUT = ROOT / 'results/c3_challenger_robust_v2_20261025'
FLOOR = 0.85


def comps(nodes, edges):
    parent = {n: n for n in nodes}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    for a, b in edges:
        if a in parent and b in parent:
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[rb] = ra
    return {n: find(n) for n in nodes}


def main():
    OUT.mkdir(exist_ok=True)
    v2 = json.loads(V2.read_text())
    edges = [tuple(e[:2]) for e in v2['v2_edges_list']]
    edge_set = {tuple(sorted(e)) for e in edges}

    v8rows = list(csv.DictReader(open(V8)))
    elig = {r['name']: r for r in json.loads(ELIG.read_text())['rows']}
    ledger = {r['name']: r for r in json.loads(LEDGER.read_text())['rows']}
    seqs = {r['name']: r['sequence'] for r in csv.DictReader(open(SEQ))}
    sens = {r['name']: r for r in json.loads(SENS.read_text())}

    retained = [r for r in v8rows if elig[r['name']]['disposition_PROPOSED'] == 'ELIGIBLE']
    dropped = [r for r in v8rows if elig[r['name']]['disposition_PROPOSED'] != 'ELIGIBLE']
    n_seats = len(dropped)
    retained_names = [r['name'] for r in retained]

    pool = [r for r in ledger.values()
            if r.get('status') == 'PASS' and isinstance(r.get('iptm'), (int, float))
            and r['iptm'] >= FLOOR and r.get('refold_pass') is True
            and sens.get(r['name'], {}).get('all_models_clash_clean') is True]

    universe = sorted({ledger[r['name']]['backbone'] for r in retained if r['name'] in ledger}
                      | {r['backbone'] for r in pool})
    label = comps(universe, edge_set)
    used = {label[ledger[n]['backbone']] for n in retained_names
            if n in ledger and ledger[n]['backbone'] in label}

    def clashes_retained(bb):
        # NOTE: no `if v in label` guard here. Retained v8 rows are DESIGN names, and many are not keys
        # of the backbone universe; adding that guard silently skipped most retained rows and made the
        # rejection test almost inert. (Caught by replaying the shipped selection as a control.)
        return any(tuple(sorted((bb, v))) in edge_set for v in retained_names)

    considered, chosen = [], []
    for r in sorted(pool, key=lambda r: (-(r.get('iptm') or 0), r['name'])):
        bb = r['backbone']
        rec = {'name': r['name'], 'backbone': bb, 'iptm': r.get('iptm'),
               'decision': None}
        if clashes_retained(bb):
            rec['decision'] = 'reject: near-identical to a retained v8 row'
        elif label.get(bb) in used:
            rec['decision'] = 'reject: component already represented'
        else:
            rec['decision'] = 'TAKE'
            used.add(label.get(bb))
            chosen.append(r)
        considered.append(rec)
        if len(chosen) == n_seats:
            break

    shipped = [r['name'] for r in csv.DictReader(open(SHIPPED))][len(retained):]
    new_names = [r['name'] for r in chosen]

    payload = {
        'artifact': 'SENSITIVITY ANALYSIS — evidence only; shipped artifact untouched',
        'rule': 'v2 symmetric near-identical predicate; all other gates held fixed',
        'seats_needed': n_seats, 'seats_filled': len(chosen),
        'status': 'COMPLETE' if len(chosen) == n_seats else 'INCOMPLETE',
        'retained_v8_rows': retained_names,
        'shipped_new_seats': shipped,
        'v2_new_seats': new_names,
        'selection_identical': shipped == new_names,
        'seats_added_vs_shipped': [n for n in new_names if n not in shipped],
        'seats_dropped_vs_shipped': [n for n in shipped if n not in new_names],
        'considered': considered,
        'note': ('If the selection is identical, the shipped artifact is invariant to the corrected rule. '
                 'If not, this is a DIFFERENT artifact and its clash measurements would need re-deriving; '
                 'no CSV is written in that case.'),
    }
    (OUT / 'sensitivity.json').write_text(json.dumps(payload, indent=1) + '\n')

    print(f"seats {len(chosen)}/{n_seats}; selection identical to shipped: {payload['selection_identical']}")
    print(f"added: {payload['seats_added_vs_shipped']}")
    print(f"dropped: {payload['seats_dropped_vs_shipped']}")
    for c in considered:
        if c['decision'] != 'TAKE':
            print(f"  {c['decision']:48s} {c['name']} (iPTM {c['iptm']})")
    return 0


if __name__ == '__main__':
    sys.exit(main())
