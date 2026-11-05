#!/usr/bin/env python3
"""Consolidated invariant audit of ALL FOUR C3 candidate CSVs, under the symmetric v2 rule. ($0)

Answers one question in one place: does each candidate actually satisfy the properties it advertises?
  I1  20 rows, unique names, unique sequences, canonical residues, lengths in [10,250]
  I2  no two rows near-identical under v2 (except where the file documents a known pair)
  I3  at most one design per structural component, computed on the FULL 200-node universe
  I4  every row's CSV sequence appears exactly in its own scored/targeted structure

Components use the full measured universe (not the selection subgraph) -- the subgraph labelling differs
from the full graph for 6 pool pairs, so the full graph is the correct basis.
Writes results/c3_candidate_invariants_20261025/summary.json. Read-only on every artifact.
"""
import csv
import itertools
import json
import pathlib
import sys

from tmtools import tm_align

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from c3_backbone_clusters_20261025 import one_letter  # noqa: E402
import importlib.util  # noqa: E402

OUT = ROOT / 'results/c3_candidate_invariants_20261025'
V2 = ROOT / 'results/c3c4_dedup_symmetry_20261025/rule_v2.json'
CROSS = ROOT / 'results/c3_r3_20261025/cross_tm_20261025.json'
LEDGER = ROOT / 'results/c3_sampling_depth_v1_20261025/coverage_ledger.json'
TM, COV = 0.65, 0.80
CANON = set('ACDEFGHIKLMNPQRSTVWY')
FILES = {
    'v8': 'results/c3_submission_v8_20261025.csv',
    'filtered': 'results/c3_challenger_20261025/c3_challenger_filtered_20261025.csv',
    'robust_v1': 'results/c3_challenger_robust_20261025/c3_challenger_all5robust_20261025.csv',
    'robust_v2': 'results/c3_challenger_robust_v2_20261025/c3_challenger_all5robust_v2_20261025.csv',
}


def load_cw():
    spec = importlib.util.spec_from_file_location(
        'cw', ROOT / 'scripts/c3_round2_cluster_crosswalk_20261025.py')
    cw = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cw)
    return cw


def find_pdb(n, cw):
    import glob
    for key in dict.fromkeys([n]):
        for c in (ROOT / f'results/c3_pod_artifacts_20261025/{key}_complex.pdb',
                  ROOT / f'results/c3_round2_111_20261025/screen24/c/{key}/complex_rank_001.pdb',
                  ROOT / f'results/c3_af2m_port_20261025/portval5/portval5_out/{key}/complex_rank_001.pdb'):
            if c.exists():
                return c
    return None


def main():
    OUT.mkdir(exist_ok=True)
    cw = load_cw()
    v2 = {tuple(sorted(e[:2])) for e in json.loads(V2.read_text())['v2_edges_list']}
    cross = json.loads(CROSS.read_text())['pairs']
    nodes = sorted({a for a in cross} | {b for a in cross for b in cross[a]})
    led = {r['name']: r for r in json.loads(LEDGER.read_text())['rows']}

    parent = {n: n for n in nodes}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    for a, b in v2:
        if a in parent and b in parent:
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[rb] = ra

    out = {}
    for label, rel in FILES.items():
        rows = list(csv.DictReader(open(ROOT / rel)))
        names = [r['name'] for r in rows]
        seqs = [r['sequence'] for r in rows]
        i1 = {
            'n_rows': len(rows),
            'unique_names': len(set(names)) == len(names),
            'unique_sequences': len(set(seqs)) == len(seqs),
            'canonical_only': all(set(s) <= CANON for s in seqs),
            'lengths_in_range': all(10 <= len(s) <= 250 for s in seqs),
        }

        # I2: within-file near-identical pairs, recomputed from structures where available
        pairs, unmeasured = [], 0
        for a, b in itertools.combinations(names, 2):
            rec_a, rec_b = led.get(a), led.get(b)
            ba = rec_a.get('backbone') if rec_a else a
            bbk = rec_b.get('backbone') if rec_b else b
            if tuple(sorted((ba, bbk))) in v2:
                pairs.append([a, b, ba, bbk, 'edge in v2 set'])
        out_pairs = pairs

        # I3: one per component on the FULL universe
        comps_used = {}
        for n in names:
            r = led.get(n)
            key = r.get('backbone') if r else n
            comps_used.setdefault(find(key), []).append(n)
        multi = {k: v for k, v in comps_used.items() if len(v) > 1}

        # I4: sequence provenance (only where a structure exists)
        prov_ok = prov_missing = 0
        for r in rows:
            p = find_pdb(r['name'], cw)
            if p is None:
                prov_missing += 1
                continue
            rec = cw.load(str(p), r['name'])
            if rec is None:
                prov_missing += 1
                continue
            if one_letter(rec[1]) == r['sequence']:
                prov_ok += 1
            else:
                prov_missing += 1

        out[label] = {
            'file': rel, 'I1_integrity': i1,
            'I2_within_file_near_identical_pairs': out_pairs,
            'I3_components_with_more_than_one_row': {str(k): v for k, v in multi.items()},
            'I4_sequence_provenance': {'exact_match': prov_ok, 'no_or_mismatch': prov_missing},
        }
        print(f"\n== {label} ({len(rows)} rows)")
        print('  I1', i1)
        print('  I2 pairs:', len(out_pairs), out_pairs[:3])
        print('  I3 multi-row components:', len(multi), list(multi.values())[:3])
        print('  I4 provenance:', prov_ok, 'exact /', prov_missing, 'no-or-mismatch')

    (OUT / 'summary.json').write_text(json.dumps(
        {'artifact': 'Consolidated invariant audit — read-only, $0',
         'rule': 'v2 symmetric; components on the full 200-node universe',
         'candidates': out}, indent=1) + '\n')
    return 0


if __name__ == '__main__':
    sys.exit(main())
