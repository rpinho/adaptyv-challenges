#!/usr/bin/env python3
"""Re-run the adopted 08:00 lexicographic comparison with the CORRECTED dedup edge set. ($0, read-only)

Two bugs were found in the first version of this rerun (both caught by Astra):
  * it used only the 153 edges that were BOTH frozen and corrected, silently dropping the 56
    corrected-only edges -> that is a truncated graph, and it inflated the depth-arm figure.
  * its "no spurious links added" check was tautological (it intersected a set with its own subset).

This version uses the FULL corrected edge set (209 edges) from
results/c3c4_dedup_symmetry_20261025/c3_recluster.json, and reports frozen vs corrected side by side
under the SAME harness. It also reports the effect of the 3,160 pairs that the frozen matrix never
measured, because those cannot be attributed to symmetrisation alone.

Rule (Kimi, adopted): lexicographic on (1) distinct backbones with >=1 all-rules PASS,
(2) total all-rules PASS; ties keep v8.

Writes only results/c3c4_dedup_symmetry_20261025/rerun_0800_corrected.json.
"""
import csv
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / 'results/c3c4_dedup_symmetry_20261025/rerun_0800_corrected.json'
CROSS = ROOT / 'results/c3_r3_20261025/cross_tm_20261025.json'
RECLUSTER = ROOT / 'results/c3c4_dedup_symmetry_20261025/c3_recluster.json'
V8 = ROOT / 'results/c3_submission_v8_20261025.csv'
TM_MIN, COV_MIN = 0.65, 0.80


def comps_e(subset, edges):
    parent = {n: n for n in subset}

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
    return len({find(n) for n in subset})


def comps_global_e(subset, edges, nodes):
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
    return len({find(n) for n in subset if n in parent})


def main():
    cross = json.loads(CROSS.read_text())['pairs']
    nodes = sorted({a for a in cross} | {b for a in cross for b in cross[a]})

    frozen = set()
    for a in cross:
        for b, r in cross[a].items():
            if r.get('tm', 0) >= TM_MIN and r.get('coverage', 0) >= COV_MIN:
                frozen.add(tuple(sorted((a, b))))

    rc = json.loads(RECLUSTER.read_text())
    corrected = {tuple(sorted((a, b))) for a, b, _, _ in rc['keep']}
    agree = frozen & corrected
    frozen_only = frozen - corrected
    corrected_only = corrected - frozen

    v8_all = [r['name'] for r in csv.DictReader(open(V8))]
    v8_in = [n for n in v8_all if n in cross]
    elig = json.loads((ROOT / 'results/c3_v8_eligibility_20261025/eligibility.json').read_text())
    v8_pass_all = [r['name'] for r in elig['rows'] if r['disposition_PROPOSED'] == 'ELIGIBLE']
    v8_pass_in = [n for n in v8_pass_all if n in cross]

    recs = json.loads((ROOT / 'results/c3_sampling_depth_v1_20261025/verify.json').read_text())['records']
    sd_bbs = sorted({r['backbone'] for r in recs})
    sd_pass = sorted({r['backbone'] for r in recs if r.get('status') == 'PASS'})

    def novel(tset):
        return sum(1 for b in sd_pass if not any(tuple(sorted((b, v))) in tset for v in v8_in))

    metrics = {}
    for label, es in (('frozen', frozen), ('corrected', corrected)):
        metrics[label] = {
            'edges': len(es),
            'v8_global_components_all': comps_global_e(v8_in, es, nodes),
            'v8_global_components_pass': comps_global_e(v8_pass_in, es, nodes),
            'v8_own_matrix_components_pass': comps_e(v8_pass_in, es),
            'depth_own_universe_components_all': comps_e(sd_bbs, es),
            'depth_own_universe_components_pass': comps_e(sd_pass, es),
            'depth_global_components_pass': comps_global_e(sd_pass, es, nodes),
            'depth_pass_novel_vs_v8': novel(es),
        }

    payload = {
        'rule': 'lexicographic (1) backbones with >=1 all-rules PASS (2) total PASS; ties keep v8',
        'near_identical_frozen': f'TM>={TM_MIN} AND coverage>={COV_MIN} (chain-2 TM, per-seq coverage)',
        'near_identical_corrected': 'symmetric TM AND true paired alignment coverage (same thresholds)',
        'nodes': len(nodes),
        'frozen_unique_pairs_measured': rc.get('frozen_unique_pairs'),
        'pairs_recomputed': len(nodes) * (len(nodes) - 1) // 2,
        'newly_measured_pairs': rc.get('newly_measured_pairs'),
        'edge_sets': {'frozen': len(frozen), 'corrected': len(corrected), 'agree': len(agree),
                      'frozen_only': len(frozen_only), 'corrected_only': len(corrected_only)},
        'metrics': metrics,
        'verdict': ('depth arm wins rule 1 under both edge sets; the lead grows with the corrected rule. '
                    'NOT to be quoted as a multiple (e.g. "4.5x") — see caveats.'),
        'caveats': [
            'the corrected edge set includes 3,160 pairs the frozen matrix never measured, so a '
            'corrected-only edge cannot be attributed to symmetrisation alone',
            'components are single-linkage: size proves connectivity under the predicate, not fold identity',
            'v8 contributes 19 of 20 rows to this matrix; one eligible row is absent',
            'a 99-backbone arm compared with a 20-row artifact is a unit-mismatch; the count is a '
            'qualifying-units metric, not a portfolio-efficiency result',
        ],
    }
    OUT.write_text(json.dumps(payload, indent=1) + '\n')

    print(f"edges: frozen {len(frozen)} / corrected {len(corrected)} / agree {len(agree)} / "
          f"frozen-only {len(frozen_only)} / corrected-only {len(corrected_only)}")
    print(f"pairs recomputed {payload['pairs_recomputed']:,}; newly measured {payload['newly_measured_pairs']:,}")
    print()
    keys = ['edges', 'v8_global_components_all', 'v8_global_components_pass',
            'v8_own_matrix_components_pass', 'depth_own_universe_components_all',
            'depth_own_universe_components_pass', 'depth_global_components_pass',
            'depth_pass_novel_vs_v8']
    print(f"{'metric':40s} {'FROZEN':>8s} {'CORRECTED':>10s}")
    for k in keys:
        print(f"{k:40s} {metrics['frozen'][k]:8d} {metrics['corrected'][k]:10d}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
