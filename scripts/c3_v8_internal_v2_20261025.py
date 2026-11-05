#!/usr/bin/env python3
"""v8's INTERNAL structural redundancy under the symmetric v2 rule vs the frozen rule ($0).

The shipped v8 diversity claim ("1 near-identical pair, 19 components", tm_max 0.7144) was measured with
the frozen predicate whose coverage clause is dead (returns 1.0000). This re-measures all 190 v8-vs-v8
pairs under v2 and reports both, so the primary artifact's diversity statement is either confirmed or
corrected.

Control: the frozen recomputation must reproduce the shipped summary (1 pair / 19 components) exactly.
Writes results/c3_v8_internal_v2_20261025/.
"""
import csv
import importlib.util
import itertools
import json
import pathlib
import sys

from tmtools import tm_align

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from c3_backbone_clusters_20261025 import one_letter  # noqa: E402

V8 = ROOT / 'results/c3_submission_v8_20261025.csv'
BASE = ROOT / 'results/c3_v8_internal_tm_20261025'
OUT = ROOT / 'results/c3_v8_internal_v2_20261025'
TM_MIN, COV_MIN = 0.65, 0.80


def load_cw():
    spec = importlib.util.spec_from_file_location(
        'cw', ROOT / 'scripts/c3_round2_cluster_crosswalk_20261025.py')
    cw = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cw)
    return cw


def structure(n, cw):
    for d, suf in ((ROOT / 'results/c3_pod_artifacts_20261025', '_complex.pdb'),
                   (ROOT / 'results/c3_round2_111_20261025/backbone_pdb', '.pdb'),
                   (ROOT / 'results/c3_round2_111_20261025/esm72', '.pdb')):
        p = d / f'{n}{suf}'
        if p.exists():
            r = cw.load(str(p), n)
            if r:
                return r
    return None


def comps(nodes, edges):
    parent = {n: n for n in nodes}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    for a, b in edges:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra
    return len({find(n) for n in nodes})


def main():
    OUT.mkdir(exist_ok=True)
    cw = load_cw()
    names = [r['name'] for r in csv.DictReader(open(V8))]
    recs = {n: structure(n, cw) for n in names}
    missing = [n for n, r in recs.items() if r is None]
    if missing:
        sys.exit(f'missing structures: {missing}')
    if len(names) != 20:
        sys.exit('unexpected v8 row count')

    frozen_edges, v2_edges, tms = [], [], []
    for a, b in itertools.combinations(names, 2):
        _, na, ca = recs[a]
        _, nb, cb = recs[b]
        sa, sb = one_letter(na), one_letter(nb)
        if 'X' in sa + sb:
            sys.exit(f'non-standard residue in {a} x {b}')
        # frozen: chain-2 TM + per-sequence non-gap coverage (the shipped definition)
        fc = cw.compare(recs[a], recs[b])
        if fc and fc['tm'] >= TM_MIN and fc['coverage'] >= COV_MIN:
            frozen_edges.append([a, b, fc['tm'], fc['coverage']])
        # v2: symmetric
        r = tm_align(ca, cb, sa, sb)
        r2 = tm_align(cb, ca, sb, sa)
        p1 = sum(1 for u, v in zip(r.seqxA, r.seqyA) if u != '-' and v != '-')
        p2 = sum(1 for u, v in zip(r2.seqxA, r2.seqyA) if u != '-' and v != '-')
        tm = max(r.tm_norm_chain2, r2.tm_norm_chain2)
        cov = max(p1, p2) / max(len(sa), len(sb))
        tms.append(float(tm))
        if tm >= TM_MIN and cov >= COV_MIN:
            v2_edges.append([a, b, round(float(tm), 4), round(float(cov), 4)])

    shipped = json.loads((BASE / 'summary.json').read_text())
    control_ok = (len(frozen_edges) == shipped['near_identical_pairs']
                  and comps(names, [(a, b) for a, b, _, _ in frozen_edges]) == shipped['structural_components'])

    payload = {
        'artifact': 'v8 internal redundancy under v2 — READ-ONLY on all artifacts',
        'control': {'recomputed_frozen_pairs': len(frozen_edges),
                    'shipped_pairs': shipped['near_identical_pairs'],
                    'recomputed_frozen_components': comps(names, [(a, b) for a, b, _, _ in frozen_edges]),
                    'shipped_components': shipped['structural_components'],
                    'reproduced_shipped': control_ok},
        'v2': {'near_identical_pairs': len(v2_edges),
               'structural_components': comps(names, [(a, b) for a, b, _, _ in v2_edges]),
               'edges': v2_edges},
        'tm': {'min': round(min(tms), 4), 'median': round(sorted(tms)[len(tms) // 2], 4),
               'max': round(max(tms), 4), 'shipped_max': shipped['tm_max']},
        'frozen_pair_set': [tuple(sorted((e['a'], e['b']))) for e in shipped['near_identical_pair_list']],
        'v2_pair_set': [tuple(sorted((e[0], e[1]))) for e in v2_edges],
        'same_pair_set': (sorted(tuple(sorted((e['a'], e['b'])))
                                 for e in shipped['near_identical_pair_list'])
                          == sorted(tuple(sorted((e[0], e[1]))) for e in v2_edges)),
        # NOTE: "no edges" would also have read as "invariant" - the very tautology this repo already
        # got caught by. Compare the PAIR SETS, not emptiness.
        'verdict': None,
    }
    payload['verdict'] = ('v8 internal diversity is INVARIANT to the corrected rule: same pair set'
                          if payload['same_pair_set']
                          else 'v8 internal diversity CHANGES under the corrected rule')
    (OUT / 'summary.json').write_text(json.dumps(payload, indent=1) + '\n')
    print(json.dumps(payload, indent=1))
    if not control_ok:
        print('CONTROL FAILED — no v2 conclusion.')
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
