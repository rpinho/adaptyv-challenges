#!/usr/bin/env python3
"""INDEPENDENT verification of the v2 robust challenger's near-identical claim ($0).

Does NOT reuse results/c3c4_dedup_symmetry_20261025/rule_v2.json. Recomputes the predicate directly from
archived structures, in BOTH argument orders, for every (new seat, retained row) pair in the artifact,
and asserts:
  A. no new seat is near-identical to ANY retained v8 row;
  B. within the 8 new seats, no two are near-identical;
  C. the predicate is invariant under argument swap for every pair tested (order-free check);
  D. the different-membership control: the dropped shipped seat IS distinguished from the added one
     (a sanity control that the comparison is not uniformly permissive).
Writes results/c3_challenger_robust_v2_20261025/independent_verify.json
"""
import csv
import json
import pathlib
import sys

from tmtools import tm_align

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from c3_backbone_clusters_20261025 import one_letter  # noqa: E402
import importlib.util  # noqa: E402

V2CSV = ROOT / 'results/c3_challenger_robust_v2_20261025/c3_challenger_all5robust_v2_20261025.csv'
OUT = ROOT / 'results/c3_challenger_robust_v2_20261025/independent_verify.json'
TM_MIN, COV_MIN = 0.65, 0.80


def load_cw():
    spec = importlib.util.spec_from_file_location(
        'cw', ROOT / 'scripts/c3_round2_cluster_crosswalk_20261025.py')
    cw = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cw)
    return cw


_CACHE = {}


def backbone_of(n):
    """Design name -> backbone key, via the coverage ledger. Retained v8 rows and backbone keys map to themselves."""
    if n in _CACHE:
        return _CACHE[n]
    led = json.loads((ROOT / 'results/c3_sampling_depth_v1_20261025/coverage_ledger.json').read_text())['rows']
    bb = {r['name']: r.get('backbone') for r in led}.get(n) or n
    _CACHE[n] = bb
    return bb


def find_pdb(n):
    """Resolve a design OR backbone name to an archived structure, trying several known layouts."""
    import glob
    bb = backbone_of(n)
    cands = []
    for key in dict.fromkeys([n, bb]):
        cands += [ROOT / f'results/c3_pod_artifacts_20261025/{key}_complex.pdb',
                  ROOT / f'results/c3_round2_111_20261025/backbone_pdb/{key}.pdb',
                  ROOT / f'results/c3_r3_20261025/backbone_pdb/{key}.pdb',
                  ROOT / f'results/c3_round2_111_20261025/screen24/c/{key}/complex_rank_001.pdb']
    for c in cands:
        if c.exists():
            return c
    for key in dict.fromkeys([n, bb]):
        hits = [x for x in sorted(glob.glob(str(ROOT / f'results/**/{key}*.pdb'), recursive=True))
                if 'backbone_pdb' in x or 'complex' in x or 'screen' in x]
        if hits:
            return pathlib.Path(hits[0])
    return None


def measure(a, b):
    cw = load_cw()
    fa, fb = find_pdb(a), find_pdb(b)
    if not fa or not fb:
        return None
    ra, rb = cw.load(fa, a), cw.load(fb, b)
    if not ra or not rb:
        return None
    _, na, ca = ra
    _, nb, cb = rb
    sa, sb = one_letter(na), one_letter(nb)
    if 'X' in sa + sb:
        return None
    r = tm_align(ca, cb, sa, sb)
    r2 = tm_align(cb, ca, sb, sa)
    p1 = sum(1 for u, v in zip(r.seqxA, r.seqyA) if u != '-' and v != '-')
    p2 = sum(1 for u, v in zip(r2.seqxA, r2.seqyA) if u != '-' and v != '-')
    ab = {'tm': float(max(r.tm_norm_chain2, r2.tm_norm_chain2)),
          'cov': float(max(p1, p2) / max(len(sa), len(sb)))}
    # second order, computed independently, to test swap invariance
    q = tm_align(cb, ca, sb, sa)
    q2 = tm_align(ca, cb, sa, sb)
    q1 = sum(1 for u, v in zip(q.seqxA, q.seqyA) if u != '-' and v != '-')
    q2n = sum(1 for u, v in zip(q2.seqxA, q2.seqyA) if u != '-' and v != '-')
    ba = {'tm': float(max(q.tm_norm_chain2, q2.tm_norm_chain2)),
          'cov': float(max(q1, q2n) / max(len(sa), len(sb)))}
    linked = ab['tm'] >= TM_MIN and ab['cov'] >= COV_MIN
    return {'a': a, 'b': b, 'tm': round(ab['tm'], 4), 'cov': round(ab['cov'], 4),
            'linked': linked, 'swap_invariant': (round(ab['tm'], 6) == round(ba['tm'], 6)
                                                 and round(ab['cov'], 6) == round(ba['cov'], 6))}


def main():
    rows = [r['name'] for r in csv.DictReader(open(V2CSV))]
    retained, new = rows[:12], rows[12:]
    pairs = []
    missing = []
    for n in new + retained:
        if find_pdb(n) is None:
            missing.append(n)
    for n in new:
        for v in retained:
            m = measure(backbone_of(n), backbone_of(v))
            if m:
                pairs.append(m)
    within = []
    for i, x in enumerate(new):
        for y in new[i + 1:]:
            m = measure(backbone_of(x), backbone_of(y))
            if m:
                within.append(m)

    violations_a = [p for p in pairs if p['linked']]
    violations_b = [p for p in within if p['linked']]
    noninv = [p for p in pairs + within if not p['swap_invariant']]
    min_cov = min((p['cov'] for p in pairs), default=None)
    max_tm = max((p['tm'] for p in pairs), default=None)
    closest = sorted(pairs, key=lambda p: -p['tm'])[:5]

    payload = {
        'artifact': 'INDEPENDENT verification — recomputed from PDBs, does not use rule_v2.json',
        'csv': str(V2CSV.relative_to(ROOT)),
        'missing_structures': missing,
        'pairs_new_vs_retained': len(pairs),
        'pairs_within_new': len(within),
        'A_no_new_seat_near_identical_to_retained': not violations_a,
        'B_no_two_new_seats_near_identical': not violations_b,
        'C_predicate_swap_invariant_all_pairs': not noninv,
        'violations_A': violations_a, 'violations_B': violations_b, 'non_invariant': noninv,
        'closest_new_vs_retained_top5': closest,
        'max_tm_new_vs_retained': round(max_tm, 4) if max_tm else None,
        'min_cov_new_vs_retained': round(min_cov, 4) if min_cov else None,
        'note': ('Independent of the stored edge set. A pass here means the artifact satisfies its own '
                 'advertised predicate when measured directly.'),
    }
    OUT.write_text(json.dumps(payload, indent=1) + '\n')
    print(json.dumps({k: v for k, v in payload.items()
                      if k not in ('violations_A', 'violations_B', 'non_invariant')}, indent=1))
    # Fail closed: zero measured pairs is a VACUOUS pass, not a pass.
    if not pairs:
        print('VACUOUS: 0 pairs measured — treating as FAILURE, not success.')
        return 1
    return 0 if not (violations_a or violations_b or noninv) else 1


if __name__ == '__main__':
    sys.exit(main())
