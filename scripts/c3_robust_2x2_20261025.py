#!/usr/bin/env python3
"""Symmetric 2x2 decomposition for the ROBUST family: rule (frozen vs v2-symmetric) x
universe (selection subgraph vs full measured graph).

The filtered family already has this decomposition. This does the same for the robust arm so
"which artifact" can be compared like-for-like.

CONTROLS (all must hold before anything is reported):
  frozen/subgraph  -> reproduces robust v1's 8 seats
  v2/subgraph      -> reproduces robust v2's 8 seats
  v2/full          -> reproduces robust v3's 8 seats
Writes results/c3_robust_2x2_20261025/sensitivity.json. No new CSV.
"""
import csv, json, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
V8 = ROOT/'results/c3_submission_v8_20261025.csv'
ELIG = ROOT/'results/c3_v8_eligibility_20261025/eligibility.json'
LEDGER = ROOT/'results/c3_sampling_depth_v1_20261025/coverage_ledger.json'
V2 = ROOT/'results/c3c4_dedup_symmetry_20261025/rule_v2.json'
CROSS = ROOT/'results/c3_r3_20261025/cross_tm_20261025.json'
SENS = ROOT/'results/c3_pool_five_model_20261025/per_design.json'
SHIPPED = {
    'v1': ROOT/'results/c3_challenger_robust_20261025/c3_challenger_all5robust_20261025.csv',
    'v2': ROOT/'results/c3_challenger_robust_v2_20261025/c3_challenger_all5robust_v2_20261025.csv',
    'v3': ROOT/'results/c3_challenger_robust_v3_20261025/c3_challenger_all5robust_v3_20261025.csv',
}
OUT = ROOT/'results/c3_robust_2x2_20261025'
FLOOR = 0.85
ALIAS = {'B_26102611_s1': 'B_26102611'}


def comps(nodes, edges):
    parent = {n: n for n in nodes}
    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]; x = parent[x]
        return x
    for a, b in edges:
        if a in parent and b in parent:
            ra, rb = find(a), find(b)
            if ra != rb: parent[rb] = ra
    return {n: find(n) for n in nodes}


def frozen_edges(directional=False):
    """Frozen near-identical rule (TM>=0.65, coverage>=0.80).

    v1 iterated only pairs.get(a, {}) for a in universe, so a near pair counted only if the
    candidate happened to be the OUTER key. That asymmetry is part of v1's rule, not a detail:
    reproducing v1 requires it. v2 iterates the undirected edge set."""
    cross = json.loads(CROSS.read_text())['pairs']
    out = set()
    for a, inner in cross.items():
        for b, rec in inner.items():
            if rec.get('tm', 0) >= 0.65 and rec.get('coverage', 0) >= 0.80:
                out.add((a, b) if directional else tuple(sorted((a, b))))
    return out


def run(rule, universe):
    """rule: 'frozen' (v1: directional frozen near-identical test) or 'v2' (symmetric v2 predicate).
    universe: 'subgraph' (v1/v2 as implemented: ledger lookups, empty retained seed) or 'full'
    (measured 200-node graph, correct retained-name seed).

    NOTE: changing the universe also repairs the empty-seed defect, so 'universe alone' is really
    'universe + seed repair'. Both are reported separately via seed_components."""
    v8rows = list(csv.DictReader(open(V8)))
    elig = {r['name']: r for r in json.loads(ELIG.read_text())['rows']}
    led = {r['name']: r for r in json.loads(LEDGER.read_text())['rows']}
    sens = {r['name']: r for r in json.loads(SENS.read_text())}

    if rule == 'frozen':
        edge_list = frozen_edges(directional=True)
        edge_set = {tuple(sorted(e)) for e in edge_list}
        def linked(a, b): return (a, b) in edge_list
    elif rule == 'v2':
        edge_set = {tuple(sorted(e[:2])) for e in json.loads(V2.read_text())['v2_edges_list']}
        def linked(a, b): return tuple(sorted((a, b))) in edge_set
    else:
        raise ValueError(rule)

    retained = [r for r in v8rows if elig[r['name']]['disposition_PROPOSED'] == 'ELIGIBLE']
    n_seats = len(v8rows) - len(retained)
    rnames = [r['name'] for r in retained]
    pool = [r for r in led.values()
            if r.get('status') == 'PASS' and isinstance(r.get('iptm'), (int, float))
            and r['iptm'] >= FLOOR and r.get('refold_pass') is True
            and sens.get(r['name'], {}).get('all_models_clash_clean') is True]

    if universe == 'subgraph':
        nodes = sorted({led[n]['backbone'] for n in rnames if n in led}
                       | {r['backbone'] for r in pool})
        seed = {led[n]['backbone'] for n in rnames if n in led}
        seed_note = 'retained rows looked up in the depth-arm ledger (v1/v2 as implemented)'
    else:
        cross = json.loads(CROSS.read_text())['pairs']
        nodes = sorted({a for a in cross} | {b for a in cross for b in cross[a]}
                       | {r['backbone'] for r in pool} | set(ALIAS.values()))
        seed = {ALIAS.get(n, n) for n in rnames if ALIAS.get(n, n) in nodes}
        seed_note = 'correct retained-name lookup over the full measured graph'

    label = comps(nodes, edge_set)
    used = {label[s] for s in seed if s in label}
    seed_n = len(used)

    chosen = []
    for r in sorted(pool, key=lambda r: (-(r.get('iptm') or 0), r['name'])):
        bb = r['backbone']
        direct = any(linked(bb, v) or linked(v, bb) for v in rnames)
        if direct: continue
        if label.get(bb) in used: continue
        used.add(label.get(bb))
        chosen.append(r)
        if len(chosen) == n_seats: break
    return [r['name'] for r in chosen], seed_n, seed_note


def main():
    OUT.mkdir(exist_ok=True)
    shipped = {k: [r['name'] for r in csv.DictReader(open(p))][12:] for k, p in SHIPPED.items()}
    cells = {}
    for rule in ('frozen', 'v2'):
        for universe in ('subgraph', 'full'):
            seats, seed_n, note = run(rule, universe)
            cells[f'{rule}/{universe}'] = {'seats': seats, 'seed_components': seed_n, 'seed_note': note}
            print(f'{rule:6s}/{universe:8s} seed_comp={seed_n:2d}  seats={seats}')

    checks = {
        'frozen/subgraph == v1': cells['frozen/subgraph']['seats'] == shipped['v1'],
        'v2/subgraph == v2': cells['v2/subgraph']['seats'] == shipped['v2'],
        'v2/full == v3': cells['v2/full']['seats'] == shipped['v3'],
    }
    print()
    for k, v in checks.items(): print(f'{k}: {v}')
    if not all(checks.values()):
        print('\nHARNESS INVALID — not reporting decompositions.')
        (OUT/'sensitivity.json').write_text(json.dumps({'controls': checks, 'cells': cells}, indent=1)+'\n')
        return 1

    def diff(a, b):
        return {'added': [x for x in cells[b]['seats'] if x not in cells[a]['seats']],
                'dropped': [x for x in cells[a]['seats'] if x not in cells[b]['seats']],
                'n_changed': len(set(cells[a]['seats']) ^ set(cells[b]['seats'])) // 2}

    payload = {
        'artifact': 'SENSITIVITY ONLY — 2x2 rule x universe for the robust family',
        'controls': checks,
        'shipped': shipped,
        'cells': cells,
        'effect_of_universe_alone': diff('frozen/subgraph', 'frozen/full'),
        'effect_of_rule_alone': diff('frozen/subgraph', 'v2/subgraph'),
        'effect_of_both': diff('frozen/subgraph', 'v2/full'),
        'seed_component_counts': {k: v['seed_components'] for k, v in cells.items()},
        'note': 'seed_components = how many retained seats actually seeded a component. Under the '
                'subgraph cells the seed is small because retained rows are looked up in the '
                'depth-arm ledger, where 0/12 of them exist.',
    }
    (OUT/'sensitivity.json').write_text(json.dumps(payload, indent=1)+'\n')
    print('\nuniverse alone:', payload['effect_of_universe_alone'])
    print('rule alone    :', payload['effect_of_rule_alone'])
    return 0


if __name__ == '__main__':
    sys.exit(main())
