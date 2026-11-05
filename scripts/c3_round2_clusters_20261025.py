#!/usr/bin/env python3
"""Round-2 backbone clusters: same TM/coverage convention as c3_backbone_clusters_20261025.py.

Inputs: designed RFD4 binder backbones (results/c3_round2_111_20261025/backbone_pdb/*.pdb).
Rule (unchanged): near-identical iff TM >= 0.65 AND coverage >= 0.80; coverage = min of the two.
Clusters are the connected components under that rule.
"""
import json
import pathlib
import sys

import numpy as np
from tmtools import tm_align

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from c3_backbone_clusters_20261025 import one_letter, read_binder  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
BB = ROOT / 'results/c3_round2_111_20261025/backbone_pdb'
OUT = ROOT / 'results/c3_round2_111_20261025/clusters_20261025.json'
TM_MIN, COV_MIN = 0.65, 0.80


def main():
    bb = {}
    for pdb in sorted(BB.glob('*.pdb')):
        keys, residues = read_binder(str(pdb))
        ca = [(k, next((x for x in residues[k] if x[0] == 'CA'), None)) for k in keys]
        ca = [c for c in ca if c[1]]
        names = [c[1][1] for c in ca]
        coords = np.array([c[1][2] for c in ca], dtype=float)
        assert len(coords) >= 20, pdb
        bb[pdb.stem] = (names, coords)
    names = sorted(bb)
    print(f'backbones: {len(names)}')
    pairs, near = {}, []
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            na, ca = bb[a]
            nb, cb = bb[b]
            sa, sb = one_letter(na), one_letter(nb)
            assert 'X' not in sa + sb
            r = tm_align(ca, cb, sa, sb)
            cov = min(sum(c != '-' for c in r.seqxA) / len(sa),
                      sum(c != '-' for c in r.seqyA) / len(sb))
            tm = float(r.tm_norm_chain2)
            pairs.setdefault(a, {})[b] = {'tm': round(tm, 4), 'coverage': round(cov, 4)}
            pairs.setdefault(b, {})[a] = pairs[a][b]
            if tm >= TM_MIN and cov >= COV_MIN:
                near.append({'a': a, 'b': b, 'tm': round(tm, 4), 'coverage': round(cov, 4)})
    # connected components
    parent = {n: n for n in names}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for e in near:
        parent[find(e['a'])] = find(e['b'])
    comps = {}
    for n in names:
        comps.setdefault(find(n), []).append(n)
    cluster_of = {n: 'cl%02d' % i for i, members in enumerate(
        sorted(comps.values(), key=lambda m: (-len(m), m[0]))) for n in members}
    id_map = {n: ('cl%02d' % i) for i, members in enumerate(
        sorted(comps.values(), key=lambda m: (-len(m), m[0]))) for n in members}
    sizes = {}
    for n, c in id_map.items():
        sizes[c] = sizes.get(c, 0) + 1
    out = {'rule': 'identical iff TM>=0.65 AND coverage>=0.80',
           'backbones': len(names),
           'near_identical_pairs': len(near),
           'clusters': sizes,
           'cluster_of': id_map,
           'pairs': pairs}
    OUT.write_text(json.dumps(out, indent=1) + '\n')
    print('near-identical pairs', len(near), 'clusters', len(sizes))
    print('cluster sizes', sorted(sizes.values(), reverse=True))


if __name__ == '__main__':
    main()
