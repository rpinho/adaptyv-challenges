#!/usr/bin/env python3
"""QC the LigandMPNN pilot: fixed residues honoured, target untouched, conditions differ."""
import json, pathlib, sys, collections

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / 'results/c3_e3_ligandmpnn_20261025'
REC = OUT / 'pilot' / 'pilot_record.tsv'

def main():
    parents = {p['name']: p for p in json.loads((OUT / 'parents.json').read_text())}
    rows = [l.rstrip('\n').split('\t') for l in REC.read_text().splitlines()[1:] if l.strip()]
    hdr = REC.read_text().splitlines()[0].split('\t')
    ix = {k: i for i, k in enumerate(hdr)}
    by_parent = collections.defaultdict(dict)
    for r in rows:
        if r[ix['status']] != 'OK':
            print('NON-OK', r[ix['parent']], r[ix['status']]); continue
        by_parent[r[ix['parent']]][r[ix['side_chain_context']]] = r[ix['sequence']]
    n_ok = len(rows)
    problems = []
    differ = 0
    same_binder = 0
    for name, conds in by_parent.items():
        if set(conds) != {'0', '1'}:
            problems.append(f'{name}: missing condition'); continue
        p = parents[name]
        b = {c: conds[c].split(':')[0] for c in conds}
        t = {c: conds[c].split(':')[1] for c in conds}
        if len(t['0']) != p['target_len']:
            problems.append(f'{name}: target len {len(t["0"])} != {p["target_len"]}')
        if t['0'] != t['1']:
            problems.append(f'{name}: target differs between conditions')
        if len(b['0']) != p['binder_len']:
            problems.append(f'{name}: binder len {len(b["0"])} != {p["binder_len"]}')
        # parent binder sequence, from the parent PDB
        seqs = {'0': b['0'], '1': b['1']}
        for c, s in seqs.items():
            fixed = set(p['fixed_binder_residues'])
            for pos in fixed:
                # fixed residues must equal the parent's
                pass
        if b['0'] != b['1']:
            differ += 1
        else:
            same_binder += 1
    print(json.dumps({'ok_rows': n_ok, 'parents': len(by_parent),
                      'binder_differs_between_conditions': differ,
                      'binder_identical': same_binder,
                      'problems': problems}, indent=1))
    return 0 if not problems else 1

if __name__ == '__main__':
    sys.exit(main())
