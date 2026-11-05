#!/usr/bin/env python3
"""Independent E3 screen verification. Writes only new E3 files.

Uses c3_round2_verify's raw-artifact recomputation unchanged, but points it at
the frozen E3 screen input and refold file, and hard-fails on cohort leakage.
"""
import json, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import c3_round2_verify_20261025 as V  # noqa: E402

E3 = ROOT / 'results/c3_e3_111_20261025'


def main():
    import argparse, csv
    ap = argparse.ArgumentParser()
    ap.add_argument('--json', default=str(E3 / 'screen_verify_20261025.json'))
    a = ap.parse_args()

    selected = json.loads((E3 / 'selected_20261025.json').read_text())
    frozen = {e['name'] for e in selected['selected']}
    inputs = {r['name']: r for r in csv.DictReader(open(E3 / 'screen_input_20261025.csv'))}
    leaked = sorted(set(inputs) - frozen)
    missing = sorted(frozen - set(inputs))
    if leaked or missing:
        print(f'COHORT FAIL leaked={leaked} missing={missing}', file=sys.stderr)
        return 4

    V.INPUT = E3 / 'screen_input_20261025.csv'
    V.REFOLD = E3 / 'refold_checks_20261025.json'
    refold = json.loads(V.REFOLD.read_text())
    groove = set(json.loads((ROOT / 'results/c3_groove_reference_20261025.json').read_text())['groove_residues_1based'])
    base = E3 / 'screen'
    records = []
    for name, row in inputs.items():
        d = base / name
        if not (d / 'scores.json').exists():
            for sub in sorted(p for p in base.iterdir() if p.is_dir()):
                cand = sub / name
                if (cand / 'scores.json').exists() or (cand / 'complex_rank_001.pdb').exists():
                    d = cand
                    break
        records.append(V.verify_one(name, row['binder'].strip(), row['target'].strip(), d,
                                    refold.get(name), groove))
    complete = [r for r in records if r['status'] != 'incomplete']
    passed = [r for r in records if r['status'] == 'PASS']
    print(f'E3 verify: {len(complete)}/{len(records)} complete, {len(passed)} PASS')
    for r in sorted(records, key=lambda x: (x['status'] != 'PASS', x['name'])):
        if r['status'] != 'PASS':
            print(f"  {r['status'].upper():<10s} {r['name']}: {'; '.join(r.get('reasons', []))[:140]}")
    out = {'cohort_sha256': __import__('hashlib').sha256((E3/'screen_input_20261025.csv').read_bytes()).hexdigest(),
           'n_selected': len(frozen), 'n_complete': len(complete), 'n_pass': len(passed),
           'records': records, 'note': 'independent recomputation; no submission written'}
    pathlib.Path(a.json).write_text(json.dumps(out, indent=1) + '\n')
    print(f'wrote {a.json}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
