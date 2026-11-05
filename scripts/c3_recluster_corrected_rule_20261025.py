#!/usr/bin/env python3
"""How much does the corrected near-identical rule change C3 backbone clustering? ($0, CPU, read-only)

The frozen cross-TM table (results/c3_r3_20261025/cross_tm_20261025.json) stores ONE TM per pair with
coverage == 1.0 for all 33,480 entries. Both are defective (see
results/c3c4_dedup_symmetry_20261025/FINDING.md):
  - the stored TM is in alphabetical argument order, so it is direction-dependent;
  - the coverage gate never fires.

This recomputes EVERY pair over the 200-node backbone universe with symmetric TM and TRUE paired
alignment coverage, then compares the resulting connected components with the frozen graph.

Writes only results/c3c4_dedup_symmetry_20261025/c3_recluster.json.
"""
import glob
import importlib.util
import json
import pathlib
import sys

import numpy as np
from tmtools import tm_align

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from c3_backbone_clusters_20261025 import one_letter  # noqa: E402

CROSS = ROOT / 'results/c3_r3_20261025/cross_tm_20261025.json'
OUT = ROOT / 'results/c3c4_dedup_symmetry_20261025/c3_recluster.json'
TM_MIN, COV_MIN = 0.65, 0.80


def _load_cw():
    spec = importlib.util.spec_from_file_location(
        'cw', ROOT / 'scripts/c3_round2_cluster_crosswalk_20261025.py')
    cw = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cw)
    return cw


def find_pdb(n):
    for c in (ROOT / f'results/c3_pod_artifacts_20261025/{n}_complex.pdb',
              ROOT / f'results/c3_round2_111_20261025/backbone_pdb/{n}.pdb',
              ROOT / f'results/c3_round2_111_20261025/screen24/c/{n}/complex_rank_001.pdb'):
        if c.exists():
            return c
    hits = [x for x in sorted(glob.glob(str(ROOT / f'results/**/{n}*.pdb'), recursive=True))
            if 'backbone_pdb' in x or 'complex' in x]
    return pathlib.Path(hits[0]) if hits else None


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
    groups = {}
    for n in nodes:
        groups.setdefault(find(n), []).append(n)
    return groups


def main():
    cw = _load_cw()
    d = json.loads(CROSS.read_text())
    p = d['pairs']
    nodes = sorted({a for a in p} | {b for a in p for b in p[a]})
    recs = {}
    for n in nodes:
        f = find_pdb(n)
        if f:
            r = cw.load(f, n)
            if r:
                recs[n] = r
    print(f'nodes {len(nodes)}, loaded {len(recs)}')

    frozen_edges = set()
    for a in p:
        for b, r in p[a].items():
            if r.get('tm', 0) >= TM_MIN and r.get('coverage', 0) >= COV_MIN:
                frozen_edges.add(tuple(sorted((a, b))))

    ns = sorted(recs)
    keep, drop, unresolved = [], [], []
    for i, a in enumerate(ns):
        for b in ns[i + 1:]:
            _, na, ca = recs[a]
            _, nb, cb = recs[b]
            sa, sb = one_letter(na), one_letter(nb)
            if 'X' in sa + sb:
                unresolved.append([a, b])
                continue
            r = tm_align(ca, cb, sa, sb)
            r2 = tm_align(cb, ca, sb, sa)
            paired = sum(1 for u, v in zip(r.seqxA, r.seqyA) if u != '-' and v != '-')
            if not paired:
                continue
            cov = min(paired / len(sa), paired / len(sb))
            sym = max(r.tm_norm_chain2, r2.tm_norm_chain2)
            e = (a, b)
            if sym >= TM_MIN and cov >= COV_MIN:
                keep.append([a, b, round(sym, 4), round(cov, 4)])
            elif e in frozen_edges:
                drop.append([a, b, round(sym, 4), round(cov, 4)])

    frozen_groups = comps(nodes, frozen_edges)
    fixed_groups = comps(ns, [(a, b) for a, b, _, _ in keep])

    # pair-level agreement
    fixed_set = {(a, b) for a, b, _, _ in keep}
    both = frozen_edges & fixed_set
    frozen_only = frozen_edges - fixed_set
    fixed_only = fixed_set - frozen_edges

    payload = {
        'rule': 'symmetric TM >= 0.65 AND true paired alignment coverage >= 0.80',
        'nodes': len(nodes), 'loaded': len(recs),
        'frozen_edges': len(frozen_edges), 'fixed_edges': len(fixed_set),
        'agree_both': len(both), 'frozen_only': len(frozen_only), 'fixed_only': len(fixed_only),
        'frozen_components': len(frozen_groups), 'fixed_components': len(fixed_groups),
        'unresolved_pairs': len(unresolved),
        'dropped_examples': sorted(drop, key=lambda x: -x[2])[:25],
        'n_dropped': len(drop),
        # Full corrected edge set, so downstream comparisons use ALL 209 edges rather than only the
        # 153 that happened to be frozen. (Astra: reusing the frozen-edge subset truncates the result.)
        'keep': keep,
        'newly_measured_pairs': len(ns) * (len(ns) - 1) // 2 - len(
            {tuple(sorted((a, b))) for a in p for b in p[a] if b in p}),
        'biggest_frozen_only_components_sample': [
            sorted(g) for g in sorted(frozen_groups.values(), key=len, reverse=True)[:5]],
        'biggest_fixed_components_sample': [
            sorted(g) for g in sorted(fixed_groups.values(), key=len, reverse=True)[:5]],
    }
    OUT.write_text(json.dumps(payload, indent=1) + '\n')
    print(json.dumps({k: v for k, v in payload.items() if not k.endswith('sample')}, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())
