#!/usr/bin/env python3
"""$0 sensitivity: robust-v2 selection with FULL-UNIVERSE components and correct retained bookkeeping.

Two implementation issues were found in the shipped selectors (Astra):
  (a) components are labelled on the 25-node selection subgraph, not the 200-node measured universe;
  (b) the "components already represented" seed set is built from retained v8 rows looked up in the
      depth-arm ledger -- and 0/12 retained rows are in that ledger, so the seed set is EMPTY.
      Direct near-identical comparisons against retained rows do still run (that test uses design names).

This reruns the identical rule with:
  * components on the full 200-node universe (with B_26102611_s1 -> B_26102611 identity resolved),
  * retained rows' backbones resolved through their own identity, so their components are marked occupied.
Everything else is unchanged: retained set, seat budget, all-rules PASS, iPTM>=0.85, refold PASS,
all-five clash-clean, iPTM-desc order, lowest-name tie-break.

CONTROL: with subgraph labels and the (buggy) empty seed, it must reproduce the shipped 8 seats.
Sensitivity only; writes no CSV.
"""
import csv
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
V8 = ROOT / 'results/c3_submission_v8_20261025.csv'
ELIG = ROOT / 'results/c3_v8_eligibility_20261025/eligibility.json'
LEDGER = ROOT / 'results/c3_sampling_depth_v1_20261025/coverage_ledger.json'
SENS = ROOT / 'results/c3_pool_five_model_20261025/per_design.json'
V2 = ROOT / 'results/c3c4_dedup_symmetry_20261025/rule_v2.json'
CROSS = ROOT / 'results/c3_r3_20261025/cross_tm_20261025.json'
SHIPPED = ROOT / 'results/c3_challenger_robust_v2_20261025/c3_challenger_all5robust_v2_20261025.csv'
OUT = ROOT / 'results/c3_robust_v2_global_component_20261025'
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


def resolve(n):
    return ALIAS.get(n, n)


def run(mode):
    v8rows = list(csv.DictReader(open(V8)))
    elig = {r['name']: r for r in json.loads(ELIG.read_text())['rows']}
    led = {r['name']: r for r in json.loads(LEDGER.read_text())['rows']}
    sens = {r['name']: r for r in json.loads(SENS.read_text())}
    edges = [tuple(e[:2]) for e in json.loads(V2.read_text())['v2_edges_list']]
    edge_set = {tuple(sorted(e)) for e in edges}
    cross = json.loads(CROSS.read_text())['pairs']
    allnodes = sorted({a for a in cross} | {b for a in cross for b in cross[a]} | set(ALIAS.values()))

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
                       | {r['backbone'] for r in pool})
        label = comps(nodes, edge_set)
        # reproduce the shipped (buggy) seed: only retained rows present in the ledger count
        used = {label[led[n]['backbone']] for n in rnames if n in led and led[n]['backbone'] in label}
    else:
        label = comps(allnodes, edge_set)
        used = {label[resolve(n)] for n in rnames if resolve(n) in label}

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
    return [r['name'] for r in chosen], used, label, rnames


def main():
    OUT.mkdir(exist_ok=True)
    shipped = [r['name'] for r in csv.DictReader(open(SHIPPED))][12:]
    ctl, _, _, _ = run('control')
    ok = ctl == shipped
    print(f'CONTROL reproduces shipped: {ok}')
    if not ok:
        print(' shipped:', shipped)
        print(' control:', ctl)
        print('HARNESS INVALID — no sensitivity conclusion.')
        (OUT / 'sensitivity.json').write_text(json.dumps(
            {'control_ok': False, 'shipped': shipped, 'control': ctl}, indent=1) + '\n')
        return 1

    glob_seats, used, label, rnames = run('global')
    payload = {
        'artifact': 'SENSITIVITY ONLY — full-universe components + correct retained bookkeeping',
        'why': ('shipped selector labelled components on a 25-node subgraph and seeded "used" from retained '
                'rows looked up in the depth-arm ledger, which contains 0/12 of them'),
        'control': {'reproduced_shipped': ok, 'shipped_seats': shipped},
        'global_rule_seats': glob_seats,
        'added_vs_shipped': [n for n in glob_seats if n not in shipped],
        'dropped_vs_shipped': [n for n in shipped if n not in glob_seats],
        'identity_alias_applied': ALIAS,
        'note': 'No CSV written. Enforcing the global rule over all 20 rows would also require reconsidering retained seats.',
    }
    (OUT / 'sensitivity.json').write_text(json.dumps(payload, indent=1) + '\n')
    print('global seats:', glob_seats)
    print('added  :', payload['added_vs_shipped'])
    print('dropped:', payload['dropped_vs_shipped'])
    return 0


if __name__ == '__main__':
    sys.exit(main())
