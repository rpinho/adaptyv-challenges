#!/usr/bin/env python3
"""Round-2 <-> round-1 backbone cluster crosswalk (Kimi v8 ruling §4).

A local round-2 cluster label must NOT be assumed equal to a round-1 label. This computes
TM/coverage between EVERY round-2 candidate binder backbone and EVERY round-1 backbone
(the 20 v6 rows + 24 shortlist rows), using the same tmtools call and the same
identical-iff-(TM>=0.65 AND coverage>=0.80) rule, then assigns round-2 backbones to
round-1-anchored components under a shared namespace.

Output: results/c3_round2_111_20261025/cluster_crosswalk_20261025.json
  {'round1_clusters': {name: label}, 'round2_clusters': {name: label},
   'pairs': {a: {b: {tm, coverage}}}, 'identical_edges': [...], 'notes': ...}
Labels are global components over the union graph, so equal labels mean "near-identical"
in one namespace; distinct labels mean independent.
"""
import glob
import json
import pathlib
import sys

import numpy as np
from tmtools import tm_align

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from c3_backbone_clusters_20261025 import one_letter, read_binder  # noqa: E402

R1_DIR = ROOT / 'results/c3_pod_artifacts_20261025'
R2_DIR = ROOT / 'results/c3_round2_111_20261025/backbone_pdb'
OUT = ROOT / 'results/c3_round2_111_20261025/cluster_crosswalk_20261025.json'
TM_MIN, COV_MIN = 0.65, 0.80


def load(path, name):
    keys, residues = read_binder(str(path))
    ca = [(k, next((x for x in residues[k] if x[0] == 'CA'), None)) for k in keys]
    ca = [c for c in ca if c[1]]
    if len(ca) < 20:
        return None
    return (name, [c[1][1] for c in ca], np.array([c[1][2] for c in ca], dtype=float))


def compare(a, b):
    _, na, ca = a
    _, nb, cb = b
    sa, sb = one_letter(na), one_letter(nb)
    if 'X' in sa + sb:
        return None
    r = tm_align(ca, cb, sa, sb)
    cov = min(sum(c != '-' for c in r.seqxA) / len(sa),
              sum(c != '-' for c in r.seqyA) / len(sb))
    return {'tm': round(float(r.tm_norm_chain2), 4), 'coverage': round(cov, 4)}


def main():
    r1 = {}
    for pdb in sorted(glob.glob(str(R1_DIR / '*_complex.pdb'))):
        name = pathlib.Path(pdb).name[:-len('_complex.pdb')]
        rec = load(pdb, name)
        if rec:
            r1[name] = rec
    r2 = {}
    for pdb in sorted(R2_DIR.glob('*.pdb')):
        rec = load(pdb, pdb.stem)
        if rec:
            r2[pdb.stem] = rec
    print(f'round1 backbones {len(r1)}, round2 backbones {len(r2)}')

    pairs, edges = {}, []
    # round-1 internal pairs (needed for the retained-set independence count)
    names = sorted(r1)
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            c = compare(r1[a], r1[b])
            if c is None:
                c = {'tm': 0.0, 'coverage': 0.0, 'skipped': 'non-standard residue'}
            pairs.setdefault(a, {})[b] = c
            pairs.setdefault(b, {})[a] = c
            if c.get('tm', 0) >= TM_MIN and c.get('coverage', 0) >= COV_MIN:
                edges.append((a, b))
    # cross pairs
    for a in sorted(r2):
        for b in sorted(r1):
            c = compare(r2[a], r1[b])
            if c is None:
                c = {'tm': 0.0, 'coverage': 0.0, 'skipped': 'non-standard residue'}
            pairs.setdefault(a, {})[b] = c
            pairs.setdefault(b, {})[a] = c
            if c.get('tm', 0) >= TM_MIN and c.get('coverage', 0) >= COV_MIN:
                edges.append((a, b))
    # round-2 internal pairs (for the launch-set cluster count)
    n2 = sorted(r2)
    for i, a in enumerate(n2):
        for b in n2[i + 1:]:
            c = compare(r2[a], r2[b])
            if c is None:
                c = {'tm': 0.0, 'coverage': 0.0, 'skipped': 'non-standard residue'}
            pairs.setdefault(a, {})[b] = c
            pairs.setdefault(b, {})[a] = c
            if c.get('tm', 0) >= TM_MIN and c.get('coverage', 0) >= COV_MIN:
                edges.append((a, b))

    parent = {n: n for n in list(r1) + list(r2)}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for a, b in edges:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb
    groups = {}
    for n in parent:
        groups.setdefault(find(n), []).append(n)
    comps = sorted(groups.values(), key=lambda m: (-min(len(m), 999), sorted(m)[0]))
    # label components that contain round-1 rows first, so round-1 labels stay stable
    label = {}
    for i, m in enumerate(comps):
        for n in m:
            label[n] = 'X%03d' % i
    r1_clusters = {n: label[n] for n in r1}
    r2_clusters = {n: label[n] for n in r2}
    cross = {a: {b: pairs[a][b] for b in r1 if b in pairs.get(a, {})} for a in r2}
    merged_with = {a: sorted(b for b, c in cross[a].items()
                            if c.get('tm', 0) >= TM_MIN and c.get('coverage', 0) >= COV_MIN)
                   for a in r2}
    out = {'rule': 'identical iff TM>=0.65 AND coverage>=0.80 (shared namespace)',
           'round1_backbones': len(r1), 'round2_backbones': len(r2),
           'round1_clusters': r1_clusters, 'round2_clusters': r2_clusters,
           'round2_merged_with_round1': {k: v for k, v in merged_with.items() if v},
           'pairs': pairs,
           'note': ('Global connected components over round-1 + round-2 binder backbones. '
                    'Equal labels => near-identical; distinct => independent. Computed by '
                    'scripts/c3_round2_cluster_crosswalk_20261025.py.')}
    OUT.write_text(json.dumps(out, indent=1) + '\n')
    n_merge = sum(1 for v in merged_with.values() if v)
    print(f'round-2 backbones merged with a round-1 backbone: {n_merge}/{len(r2)}')
    print(f'round-2 distinct labels: {len(set(r2_clusters.values()))}')
    print(f'wrote {OUT}')


if __name__ == '__main__':
    main()
