#!/usr/bin/env python3
"""VERSIONED v3 all-five-robust C3 challenger: FULL-UNIVERSE components + correct retained bookkeeping.

$0. Evidence only; nothing submitted.

Two defects were found in the v2/shipped selectors (Astra, confirmed independently):
  (a) components were labelled on the 25-node selection subgraph, not the 200-node measured universe;
  (b) the "components already represented" seed was built from retained v8 rows looked up in the
      depth-arm ledger, which contains 0/12 of them -> the seed was EMPTY, so transitive component
      exclusion against the 12 retained seats never ran. Direct near-identical tests did run.
Also: B_26102611_s1 (in v8) is absent from the measured matrix, which has B_26102611; aliased.

Gate structure:
  CONTROL (subgraph labels + empty seed, i.e. v2 as implemented) must reproduce the v2 file's 8 seats.
  TARGET  (full-universe labels + correct seed) produces the v3 seats.
Nothing else changes: retained set, budget, all-rules PASS, iPTM>=0.85, refold PASS, all-five clash-clean,
iPTM-desc order, lowest-name tie-break. Writes a CSV ONLY if the control passes and all 8 new seats are
all-five-model clash-clean.
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
CROSS = ROOT / 'results/c3_r3_20261025/cross_tm_20261025.json'
V2CSV = ROOT / 'results/c3_challenger_robust_v2_20261025/c3_challenger_all5robust_v2_20261025.csv'
OUT = ROOT / 'results/c3_challenger_robust_v3_20261025'
CSV_OUT = OUT / 'c3_challenger_all5robust_v3_20261025.csv'
FLOOR = 0.85
ALIAS = {'B_26102611_s1': 'B_26102611'}


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


def run(mode):
    v8rows = list(csv.DictReader(open(V8)))
    elig = {r['name']: r for r in json.loads(ELIG.read_text())['rows']}
    led = {r['name']: r for r in json.loads(LEDGER.read_text())['rows']}
    sens = {r['name']: r for r in json.loads(SENS.read_text())}
    edge_set = {tuple(sorted(e[:2])) for e in json.loads(V2.read_text())['v2_edges_list']}

    retained = [r for r in v8rows if elig[r['name']]['disposition_PROPOSED'] == 'ELIGIBLE']
    dropped = [r for r in v8rows if elig[r['name']]['disposition_PROPOSED'] != 'ELIGIBLE']
    n_seats = len(dropped)
    rnames = [r['name'] for r in retained]

    pool = [r for r in led.values()
            if r.get('status') == 'PASS' and isinstance(r.get('iptm'), (int, float))
            and r['iptm'] >= FLOOR and r.get('refold_pass') is True
            and sens.get(r['name'], {}).get('all_models_clash_clean') is True]

    if mode == 'control':
        nodes = sorted({(led[n]['backbone'] if n in led else n) for n in rnames}
                       | {r['backbone'] for r in pool}
                       | set(ALIAS.values()))
        label = comps(nodes, edge_set)
        used = {label[led[n]['backbone']] for n in rnames if n in led and led[n]['backbone'] in label}
    else:
        cross = json.loads(CROSS.read_text())['pairs']
        allnodes = sorted({a for a in cross} | {b for a in cross for b in cross[a]} | set(ALIAS.values()))
        label = comps(allnodes, edge_set)
        used = {label[ALIAS.get(n, n)] for n in rnames if ALIAS.get(n, n) in label}

    chosen = []
    for r in sorted(pool, key=lambda r: (-(r.get('iptm') or 0), r['name'])):
        bb = r['backbone']
        if any(tuple(sorted((bb, v))) in edge_set for v in rnames):
            continue
        if label.get(bb) in used:
            continue
        used.add(label.get(bb))
        chosen.append(r)
        if len(chosen) == n_seats:
            break
    return retained, rnames, chosen, n_seats


def main():
    OUT.mkdir(exist_ok=True)
    expected = [r['name'] for r in csv.DictReader(open(V2CSV))][12:]
    _, rnames, ctl, n_seats = run('control')
    ctl_names = [r['name'] for r in ctl]
    control_ok = ctl_names == expected
    print(f'CONTROL (v2 as implemented) reproduces v2 file: {control_ok}')
    if not control_ok:
        print(' expected:', expected)
        print(' control :', ctl_names)
        print('HARNESS INVALID — refusing to write an artifact.')
        return 1

    retained, _, chosen, n_seats = run('global')
    new = [r['name'] for r in chosen]
    if len(new) != n_seats:
        print(f'INCOMPLETE {len(new)}/{n_seats} — refusing to write.')
        return 1

    sens = {r['name']: r for r in json.loads(SENS.read_text())}
    new_ev = [{'name': n, 'iptm': sens[n]['rank1_iptm'],
               'all_models_clash_clean': sens[n]['all_models_clash_clean'],
               'n_alt_clashing': sens[n]['n_alt_clashing']} for n in new]
    n_ok = sum(1 for e in new_ev if e['all_models_clash_clean'])
    if n_ok != len(new_ev):
        print(f'POST-CHECK FAILED: {n_ok}/{len(new_ev)} all-five clean — not writing.')
        return 1

    seqs = {r['name']: r['sequence'] for r in csv.DictReader(open(SEQ))}
    with open(CSV_OUT, 'w', newline='') as fh:
        w = csv.writer(fh)
        w.writerow(['name', 'sequence', 'molecule_class'])
        for r in retained:
            w.writerow([r['name'], r['sequence'], r['molecule_class']])
        for r in chosen:
            w.writerow([r['name'], seqs[r['name']], 'single_chain'])

    payload = {
        'artifact': 'VERSIONED v3 CHALLENGER — EVIDENCE ONLY, not a submission',
        'built_on': 'Astra 11:35 ET ruling: full-universe components + correct retained bookkeeping',
        'defects_fixed_vs_v2': [
            'components labelled on the 200-node measured universe, not the 25-node selection subgraph',
            'retained-row components actually marked occupied (v2 seeded an EMPTY set: 0/12 in ledger)',
            'B_26102611_s1 aliased to B_26102611 (absent from the measured matrix)',
        ],
        'control': {'described': 'v2 as implemented', 'reproduced_v2_file': control_ok,
                    'v2_seats': expected},
        'seats_filled': len(new), 'new_seats': new,
        'five_model_evidence': {'new_seats_all5_clean': f'{n_ok}/{len(new_ev)}',
                                'total_clashing_alternates': sum(e['n_alt_clashing'] for e in new_ev),
                                'per_seat': new_ev},
        'changed_vs_v2': {'added': [n for n in new if n not in expected],
                          'dropped': [n for n in expected if n not in new]},
        'csv': str(CSV_OUT.relative_to(ROOT)),
        'caveats': [
            'structural screening only; no affinity or agonism evidence',
            'new seats only are all-five clean; the 12 retained v8 rows are NOT five-model archived',
            'disclosed post-hoc correction, not a preregistration',
            'single-linkage connectivity is not a count of biologically independent opportunities',
        ],
    }
    (OUT / 'assemble.json').write_text(json.dumps(payload, indent=1) + '\n')
    print(f'wrote {CSV_OUT.relative_to(ROOT)} seats {len(new)}/{n_seats} all5clean {n_ok}/{len(new_ev)}')
    print(' added  :', payload['changed_vs_v2']['added'])
    print(' dropped:', payload['changed_vs_v2']['dropped'])
    return 0


if __name__ == '__main__':
    sys.exit(main())
