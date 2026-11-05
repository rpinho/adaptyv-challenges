#!/usr/bin/env python3
"""Independent clash verification of ALL 20 challenger rows, one measurement path.

The dossier claims "20 of 20 clash-clean", but the 12 retained rows were measured by the v8 clash
screen and the 8 new seats by the arm's gate — two different code paths. This re-measures every row
with the independent parser from c3_clash_audit_independent_20261025.py so the claim rests on one
method. READ-ONLY; writes only results/c3_challenger_20261025/.
"""
import csv, glob, json, pathlib, sys
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from c3_clash_audit_independent_20261025 import parse_pdb, clashing_pairs, min_interchain_distance

OUT = ROOT / 'results/c3_challenger_20261025'
CHAL = OUT / 'c3_challenger_filtered_20261025.csv'
CUTOFF = 2.0


def find_pdb(name):
    for c in (ROOT / f'results/c3_pod_artifacts_20261025/{name}_complex.pdb',
              ROOT / f'results/c3_round2_111_20261025/screen24/c/{name}/complex_rank_001.pdb',
              ROOT / f'results/c3_af2m_port_20261025/portval5/portval5_out/{name}/complex_rank_001.pdb'):
        if c.exists():
            return c
    hits = glob.glob(str(ROOT / f'results/**/{name}/complex_rank_001.pdb'), recursive=True)
    return pathlib.Path(hits[0]) if hits else None


def main():
    names = [r['name'] for r in csv.DictReader(open(CHAL))]
    rows, missing = [], []
    for n in names:
        p = find_pdb(n)
        if p is None:
            missing.append(n); continue
        ch = parse_pdb(p)
        if len(ch) != 2:
            missing.append(f'{n}: {len(ch)} chains'); continue
        order = sorted(ch, key=lambda c: len(ch[c]))
        binder, target = ch[order[0]], ch[order[1]]
        pairs = clashing_pairs(binder, target, CUTOFF)
        mind, ba, ta = min_interchain_distance(binder, target, 6.0)
        rows.append({'name': n, 'n_clash_pairs': len(pairs), 'min_dist': mind,
                     'closest_binder': ba, 'closest_target': ta,
                     'clash_clean': len(pairs) == 0,
                     'worst_pair': pairs[0] if pairs else None})
    clean = sum(1 for r in rows if r['clash_clean'])
    payload = {'rows_checked': len(rows), 'rows_missing_structure': missing,
               'clash_clean': clean, 'clash_flagged': len(rows) - clean,
               'cutoff_A': CUTOFF, 'rows': rows,
               'claim_verified': clean == len(names),
               'note': 'single independent parser for all 20 rows; replaces the mixed-source claim'}
    (OUT / 'clash_verify.json').write_text(json.dumps(payload, indent=1) + '\n')
    print(json.dumps({k: v for k, v in payload.items() if k != 'rows'}, indent=1))
    for r in rows:
        if not r['clash_clean']:
            print('  FLAG', r['name'], r['n_clash_pairs'], r['min_dist'], r['worst_pair'])
    return 0


if __name__ == '__main__':
    sys.exit(main())
