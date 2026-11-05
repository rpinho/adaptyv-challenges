#!/usr/bin/env python3
"""VERSIONED v2 all-five-robust C3 challenger (evidence only). $0 GPU.

Built on Astra's 10:25 ET ruling: write a NEW, separately versioned v2 robust CSV, preserve
results/c3_challenger_robust_20261025/ byte-for-byte, attach the exact membership, the corrected
predicate, the frozen-rule reproduction control, and a membership-specific aggregation of the
ALREADY ARCHIVED five-model measurements (no new GPU).

Rule fixed BEFORE selection (unchanged from scripts/c3_challenger_robust_assemble_20261025.py except the
near-identical predicate, which is the correction under test):
  1. keep v8's 12 ELIGIBLE rows;
  2. drop the 8 flagged rows; fill 8 seats from the depth-arm pool;
  3. candidate must be all-rules PASS, iPTM >= 0.85, refold PASS AND clash-clean in ALL FIVE models;
  4. candidate must NOT be near-identical to ANY retained row, using v2 (symmetric TM, true paired cov);
  5. at most one design per structural component (components from the v2 edge set);
  6. order by highest iPTM, tie-break lowest name.

Gates:
  * CONTROL: with the frozen predicate, this harness must reproduce the shipped 8 seats exactly.
  * POST-CHECK: all 12 retained + all 8 new rows must be clash-clean in ALL FIVE archived models,
    otherwise the artifact is NOT written.
Writes only results/c3_challenger_robust_v2_20261025/.
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
CROSS = ROOT / 'results/c3_r3_20261025/cross_tm_20261025.json'
SENS = ROOT / 'results/c3_pool_five_model_20261025/per_design.json'
V2 = ROOT / 'results/c3c4_dedup_symmetry_20261025/rule_v2.json'
SHIPPED = ROOT / 'results/c3_challenger_robust_20261025/c3_challenger_all5robust_20261025.csv'
OUT = ROOT / 'results/c3_challenger_robust_v2_20261025'
CSV_OUT = OUT / 'c3_challenger_all5robust_v2_20261025.csv'
TM, COV, FLOOR = 0.65, 0.80, 0.85


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
    return {n: find(n) for n in nodes}, find


def run(edge_set):
    v8rows = list(csv.DictReader(open(V8)))
    elig = {r['name']: r for r in json.loads(ELIG.read_text())['rows']}
    ledger = {r['name']: r for r in json.loads(LEDGER.read_text())['rows']}
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
    label, find = comps(universe, edge_set)
    used = {label[ledger[n]['backbone']] for n in retained_names
            if n in ledger and ledger[n]['backbone'] in label}

    def clashes_retained(bb):
        return any(tuple(sorted((bb, v))) in edge_set for v in retained_names)

    considered, chosen = [], []
    for r in sorted(pool, key=lambda r: (-(r.get('iptm') or 0), r['name'])):
        bb = r['backbone']
        rec = {'name': r['name'], 'backbone': bb, 'iptm': r.get('iptm')}
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
    return {'retained': retained, 'dropped': dropped, 'retained_names': retained_names,
            'chosen': chosen, 'considered': considered, 'n_seats': n_seats}


def main():
    OUT.mkdir(exist_ok=True)

    cross = json.loads(CROSS.read_text())['pairs']
    frozen = set()
    for a, inner in cross.items():
        for b, rec in inner.items():
            if rec.get('tm', 0) >= TM and rec.get('coverage', 0) >= COV:
                frozen.add(tuple(sorted((a, b))))
    v2 = {tuple(sorted(e[:2])) for e in json.loads(V2.read_text())['v2_edges_list']}

    shipped_all = [r['name'] for r in csv.DictReader(open(SHIPPED))]
    ctl = run(frozen)
    shipped_new = shipped_all[len(ctl['retained_names']):]
    ctl_new = [r['name'] for r in ctl['chosen']]
    control_ok = ctl_new == shipped_new
    print(f"CONTROL reproduces shipped 8 seats: {control_ok}")
    if not control_ok:
        print(' shipped:', shipped_new, '\n control:', ctl_new)
        print('HARNESS INVALID — refusing to write an artifact.')
        return 1

    res = run(v2)
    new = [r['name'] for r in res['chosen']]
    if len(new) != res['n_seats']:
        print(f'INCOMPLETE: {len(new)}/{res["n_seats"]} seats — refusing to write.')
        return 1

    sens = {r['name']: r for r in json.loads(SENS.read_text())}
    seqs = {r['name']: r['sequence'] for r in csv.DictReader(open(SEQ))}

    # Membership-specific five-model evidence, aggregated offline from the archive.
    rows = []
    for r in res['retained']:
        rows.append({'name': r['name'], 'role': 'retained v8', 'in_archive': r['name'] in sens})
    for r in res['chosen']:
        s = sens.get(r['name'])
        rows.append({'name': r['name'], 'role': 'new seat', 'in_archive': s is not None,
                     'n_models': s.get('n_models') if s else None,
                     'rank1_iptm': s.get('rank1_iptm') if s else None,
                     'rank1_clash_clean': s.get('rank1_clash_clean') if s else None,
                     'n_alt_clashing': s.get('n_alt_clashing') if s else None,
                     'all_models_clash_clean': s.get('all_models_clash_clean') if s else None})
    new_rows = [x for x in rows if x['role'] == 'new seat']
    n_new_ok = sum(1 for x in new_rows if x['all_models_clash_clean'] is True)
    total_alt = sum(x['n_alt_clashing'] or 0 for x in new_rows)
    if n_new_ok != len(new_rows):
        print(f'POST-CHECK FAILED: only {n_new_ok}/{len(new_rows)} new seats all-five clean — not writing.')
        return 1

    with open(CSV_OUT, 'w', newline='') as fh:
        w = csv.writer(fh)
        w.writerow(['name', 'sequence', 'molecule_class'])
        for r in res['retained']:
            w.writerow([r['name'], r['sequence'], r['molecule_class']])
        for r in res['chosen']:
            w.writerow([r['name'], seqs[r['name']], 'single_chain'])

    payload = {
        'artifact': 'VERSIONED v2 CHALLENGER — EVIDENCE ONLY, not a submission',
        'built_on': "Astra ruling 2026-10-25 10:25 ET (new separately versioned v2 robust CSV)",
        'control': {'frozen_edges': len(frozen), 'reproduced_shipped_8_seats': control_ok,
                    'shipped_new_seats': shipped_new},
        'predicate': 'v2 symmetric: TM = max(tm_ab, tm_ba); coverage = max(paired)/max(len)',
        'v2_edges': len(v2),
        'seats_filled': len(new), 'seats_needed': res['n_seats'],
        'retained_v8_rows': res['retained_names'],
        'new_seats': new,
        'changed_vs_shipped': {'added': [n for n in new if n not in shipped_new],
                               'dropped': [n for n in shipped_new if n not in new]},
        'five_model_evidence': {
            'new_seats_all5_clean': f'{n_new_ok}/{len(new_rows)}',
            'new_seats_total_clashing_alternates': total_alt,
            'per_seat': new_rows,
            'retained_rows_in_pool_archive': f"{sum(1 for x in rows if x['role']=='retained v8' and x['in_archive'])}/12",
            'note': ('retained v8 rows are not in the depth-arm five-model archive; their all-five status '
                     'is therefore NOT re-measured here and must not be described as five-model clean'),
        },
        'csv': str(CSV_OUT.relative_to(ROOT)),
        'shipped_artifact_unchanged': 'results/c3_challenger_robust_20261025/c3_challenger_all5robust_20261025.csv',
        'caveats': [
            'structural screening only; no affinity or agonism evidence',
            'new seats only are all-five clean; the 12 retained v8 rows are not five-model archived',
            'selection was made after the predicate defect was found: a disclosed post-hoc correction, not a preregistration',
            'Astra: the swap improves the ranking score under a preserved gate; "strictly better biologically" is unsupported',
        ],
    }
    (OUT / 'assemble.json').write_text(json.dumps(payload, indent=1) + '\n')
    print(f'wrote {CSV_OUT.relative_to(ROOT)}  seats {len(new)}/{res["n_seats"]}  '
          f'new seats all-5 clean {n_new_ok}/{len(new_rows)}  clashing alternates {total_alt}')
    print('  added  :', payload['changed_vs_shipped']['added'])
    print('  dropped:', payload['changed_vs_shipped']['dropped'])
    return 0


if __name__ == '__main__':
    sys.exit(main())
