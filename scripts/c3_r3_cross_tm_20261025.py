#!/usr/bin/env python3
"""R3 TM/coverage evidence in the shared, crosswalked X### namespace.

Uses the exact tmtools call and near-identical rule (TM >=0.65 AND coverage >=0.80) as
rounds 1-2. Existing round-1/round-2 X### labels are preserved; an R3 backbone that
bridges two existing components records that merge explicitly instead of silently
renumbering either one. Every pair involving an R3 backbone is measured; a pair that
cannot be measured is recorded as a skipped evidence failure, never as novelty.

Output: results/c3_r3_20261025/cross_tm_20261025.json
"""
import glob
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from c3_round2_cluster_crosswalk_20261025 import compare, load  # noqa: E402

R1_DIR = ROOT / 'results/c3_pod_artifacts_20261025'
R2_DIR = ROOT / 'results/c3_round2_111_20261025/backbone_pdb'
R3_DIR = ROOT / 'results/c3_r3_20261025/backbone_pdb'
PRIOR = ROOT / 'results/c3_round2_111_20261025/cluster_crosswalk_20261025.json'
OUT = ROOT / 'results/c3_r3_20261025/cross_tm_20261025.json'
TM_MIN, COV_MIN = 0.65, 0.80


def component_label(existing, new_counter):
    if existing:
        return min(existing), sorted(set(existing))
    new_counter[0] += 1
    return 'X%03d' % new_counter[0], []


def main():
    prior = json.loads(PRIOR.read_text())
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
    r3 = {}
    skipped_files = []
    for pdb in sorted(R3_DIR.glob('*.pdb')):
        rec = load(pdb, pdb.stem)
        if rec:
            r3[pdb.stem] = rec
        else:
            skipped_files.append(pdb.stem)
    print(f'round1={len(r1)} round2={len(r2)} round3={len(r3)} '
          f'skipped_files={len(skipped_files)}')
    if set(prior.get('round1_clusters', {})) != set(r1):
        print('ERROR round-1 node set differs from the frozen crosswalk', file=sys.stderr)
        return 4
    if set(prior.get('round2_clusters', {})) != set(r2):
        print('ERROR round-2 node set differs from the frozen crosswalk', file=sys.stderr)
        return 4

    # Start from the frozen round1/round2 components, then add every measured R3 edge.
    parent = {n: n for n in list(r1) + list(r2) + list(r3)}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[ra] = rb

    for scope in ('round1_clusters', 'round2_clusters'):
        groups = {}
        for n, lab in prior[scope].items():
            groups.setdefault(lab, []).append(n)
        for members in groups.values():
            for m in members[1:]:
                union(members[0], m)

    pairs, skipped, edges = {}, [], 0

    def add_pair(a, b, x, y):
        nonlocal edges
        c = compare(x, y)
        if c is None:
            skipped.append({'a': a, 'b': b})
            c = {'tm': None, 'coverage': None, 'skipped': 'non-standard residue'}
        pairs.setdefault(a, {})[b] = c
        pairs.setdefault(b, {})[a] = c
        if c.get('tm') is not None and c['tm'] >= TM_MIN and c['coverage'] >= COV_MIN:
            union(a, b)
            edges += 1

    for a in sorted(r3):
        for b in sorted(r1):
            add_pair(a, b, r3[a], r1[b])
        for b in sorted(r2):
            add_pair(a, b, r3[a], r2[b])
    names3 = sorted(r3)
    for i, a in enumerate(names3):
        for b in names3[i + 1:]:
            add_pair(a, b, r3[a], r3[b])

    comps = {}
    for n in parent:
        comps.setdefault(find(n), []).append(n)
    old_labels = {}
    for n, lab in prior.get('round1_clusters', {}).items():
        old_labels[n] = lab
    for n, lab in prior.get('round2_clusters', {}).items():
        old_labels[n] = lab
    max_old = max((int(lab[1:]) for lab in old_labels.values()), default=-1)
    counter = [max_old]
    label, merges = {}, {}
    for members in sorted(comps.values(), key=lambda m: sorted(m)[0]):
        existing = [old_labels[n] for n in members if n in old_labels]
        lab, merged = component_label(existing, counter)
        for n in members:
            label[n] = lab
        if merged:
            merges[lab] = merged
    r3_clusters = {n: label[n] for n in r3}
    near = {a: sorted(b for b, c in d.items()
                      if c.get('tm') is not None and c['tm'] >= TM_MIN and
                      c['coverage'] >= COV_MIN) for a, d in pairs.items() if a in r3}
    out = {
        'rule': 'near-identical iff TM>=0.65 AND coverage>=0.80; shared X### namespace',
        'round1_backbones': len(r1), 'round2_backbones': len(r2),
        'round3_backbones': len(r3), 'round3_expected': 120,
        'skipped_files': sorted(skipped_files), 'skipped_pairs': skipped,
        'complete': not skipped_files and not skipped and len(r3) == 120,
        'near_identical_edges': edges,
        'round1_clusters': {n: label[n] for n in r1},
        'round2_clusters': {n: label[n] for n in r2},
        'round3_clusters': r3_clusters,
        'merged_prior_labels': merges,
        'round3_near_identical': near,
        'round3_distinct_labels': len(set(r3_clusters.values())),
        'pairs': pairs,
        'note': ('Existing X labels preserved. A new X label is assigned only to a '
                 'component with no round-1/2 member; bridges are recorded in '
                 'merged_prior_labels. Missing pairs are evidence failures.'),
    }
    OUT.write_text(json.dumps(out, indent=1) + '\n')
    print(f'R3 distinct X labels: {out["round3_distinct_labels"]}')
    print(f'merges: {merges}')
    print(f'skipped pairs: {len(skipped)}; complete={out["complete"]}')
    print(f'wrote {OUT.relative_to(ROOT)}')
    return 0 if out['complete'] else 4


if __name__ == '__main__':
    sys.exit(main())
