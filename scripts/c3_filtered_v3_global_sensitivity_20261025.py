#!/usr/bin/env python3
"""$0 sensitivity: filtered challenger with FULL-UNIVERSE components (and correct retained bookkeeping).

The filtered selector (scripts/c3_challenger_assemble_20261025.py) seeds retained components from
retained NAMES directly (not the depth-arm ledger), so it does NOT have the empty-seed defect. It does
still label components on a selection subgraph rather than the measured universe. This tests whether that
alone changes its selection.

CONTROL: subgraph labels must reproduce the shipped filtered 8 seats.
Writes results/c3_filtered_v3_global_20261025/sensitivity.json. No CSV.
"""
import csv
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
V8 = ROOT / 'results/c3_submission_v8_20261025.csv'
ELIG = ROOT / 'results/c3_v8_eligibility_20261025/eligibility.json'
LEDGER = ROOT / 'results/c3_sampling_depth_v1_20261025/coverage_ledger.json'
V2 = ROOT / 'results/c3c4_dedup_symmetry_20261025/rule_v2.json'
CROSS = ROOT / 'results/c3_r3_20261025/cross_tm_20261025.json'
SHIPPED = ROOT / 'results/c3_challenger_20261025/c3_challenger_filtered_20261025.csv'
OUT = ROOT / 'results/c3_filtered_v3_global_20261025'
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


def frozen_edges():
    cross = json.loads(CROSS.read_text())['pairs']
    return {tuple(sorted((a, b))) for a, inner in cross.items() for b, rec in inner.items()
            if rec.get('tm', 0) >= 0.65 and rec.get('coverage', 0) >= 0.80}


def run(mode):
    v8rows = list(csv.DictReader(open(V8)))
    elig = {r['name']: r for r in json.loads(ELIG.read_text())['rows']}
    led = {r['name']: r for r in json.loads(LEDGER.read_text())['rows']}
    # the shipped filtered file was built with the FROZEN rule, so the control must use frozen edges;
    # the global run uses v2. Anything else compares across two changes at once.
    edge_set = frozen_edges() if mode == 'control' else {tuple(sorted(e[:2])) for e in json.loads(V2.read_text())['v2_edges_list']}

    retained = [r for r in v8rows if elig[r['name']]['disposition_PROPOSED'] == 'ELIGIBLE']
    dropped = [r for r in v8rows if elig[r['name']]['disposition_PROPOSED'] != 'ELIGIBLE']
    n_seats = len(dropped)
    rnames = [r['name'] for r in retained]

    pool = [r for r in led.values()
            if r.get('status') == 'PASS' and isinstance(r.get('iptm'), (int, float))
            and r['iptm'] >= FLOOR and r.get('refold_pass') is True]

    if mode == 'control':
        nodes = sorted(set(rnames) | {r['backbone'] for r in pool} | set(ALIAS.values()))
    else:
        cross = json.loads(CROSS.read_text())['pairs']
        nodes = sorted({a for a in cross} | {b for a in cross for b in cross[a]} | set(ALIAS.values()))
    label = comps(nodes, edge_set)
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
    return rnames, [r['name'] for r in chosen], n_seats


def main():
    OUT.mkdir(exist_ok=True)
    shipped = [r['name'] for r in csv.DictReader(open(SHIPPED))][12:]
    rnames, ctl, n_seats = run('control')
    ok = ctl == shipped
    print(f'CONTROL reproduces shipped filtered seats: {ok}')
    if not ok:
        print(' shipped:', shipped)
        print(' control:', ctl)
        print('HARNESS INVALID.')
        (OUT / 'sensitivity.json').write_text(json.dumps({'control_ok': False}, indent=1) + '\n')
        return 1
    _, glob_seats, _ = run('global')
    payload = {
        'artifact': 'SENSITIVITY ONLY — filtered challenger, full-universe components',
        'control_rule': 'frozen (the shipped file was built with it)',
        'global_rule': 'v2 symmetric',
        'note': 'the filtered selector does NOT have the empty-seed defect (it uses retained names directly)',
        'control': {'reproduced_shipped': ok},
        'shipped_seats': shipped,
        'global_component_seats': glob_seats,
        'added': [n for n in glob_seats if n not in shipped],
        'dropped': [n for n in shipped if n not in glob_seats],
    }
    (OUT / 'sensitivity.json').write_text(json.dumps(payload, indent=1) + '\n')
    print('global seats:', glob_seats)
    print('added  :', payload['added'])
    print('dropped:', payload['dropped'])
    return 0


if __name__ == '__main__':
    sys.exit(main())
