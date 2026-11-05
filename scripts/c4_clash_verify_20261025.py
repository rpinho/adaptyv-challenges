#!/usr/bin/env python3
"""Independent clash verification of the C4 ranked set, one measurement path.

Same parser and same frozen 2.0 A heavy-atom inter-chain rule as the C3 challenger verification, so
the C4 set's clash cleanliness is measured with the identical method. READ-ONLY on all inputs; writes
only results/c4_ranked_20261025/.
"""
import csv, glob, json, pathlib, sys
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from c3_clash_audit_independent_20261025 import parse_pdb, clashing_pairs, min_interchain_distance

OUT = ROOT / 'results/c4_ranked_20261025'
CSV_IN = OUT / 'c4_acid_ranked_20261025.csv'
CUTOFF = 2.0


def find_pdb(name):
    # Canonical, provenance-verified path first; glob order is not stable across copies.
    canonical = ROOT / f'results/c4_rebuild_20261024/remote_pdbs/{name}_complex.pdb'
    if canonical.exists():
        return canonical
    for pat in (f'results/**/{name}/complex_rank_001.pdb', f'results/**/{name}_complex.pdb'):
        hits = sorted(glob.glob(str(ROOT / pat), recursive=True))
        if hits:
            return pathlib.Path(hits[0])
    return None


def main():
    names = [r['name'] for r in csv.DictReader(open(CSV_IN))]
    rows, missing, odd = [], [], []
    for n in names:
        p = find_pdb(n)
        if p is None:
            missing.append(n)
            continue
        ch = parse_pdb(p)
        if len(ch) != 2:
            odd.append({'name': n, 'chains': len(ch), 'path': str(p.relative_to(ROOT))})
            continue
        order = sorted(ch, key=lambda c: len(ch[c]))
        binder, target = ch[order[0]], ch[order[1]]
        pairs = clashing_pairs(binder, target, CUTOFF)
        mind, ba, ta = min_interchain_distance(binder, target, 6.0)
        rows.append({'name': n, 'n_clash_pairs': len(pairs), 'min_dist': mind,
                     'clash_clean': len(pairs) == 0,
                     'worst_pair': pairs[0] if pairs else None,
                     'path': str(p.relative_to(ROOT))})
    clean = sum(1 for r in rows if r['clash_clean'])
    payload = {'rows_in_csv': len(names), 'rows_checked': len(rows),
               'rows_missing_structure': missing, 'rows_wrong_chain_count': odd,
               'clash_clean': clean, 'clash_flagged': len(rows) - clean,
               'cutoff_A': CUTOFF, 'rows': rows,
               'note': ('same independent parser and frozen 2.0 A rule as '
                        'c3_challenger_clash_verify_20261025.py; first clash measurement of this set')}
    (OUT / 'clash_verify.json').write_text(json.dumps(payload, indent=1) + '\n')
    print(json.dumps({k: v for k, v in payload.items() if k != 'rows'}, indent=1))
    for r in sorted(rows, key=lambda x: x['min_dist'])[:5]:
        print('  closest %.3f A  %s  pairs=%d' % (r['min_dist'], r['name'], r['n_clash_pairs']))


if __name__ == '__main__':
    main()
