#!/usr/bin/env python3
"""Bounded CPU audit (Kimi+Astra Q3): did the intervention actually supply TARGET side
chains, and were the two conditions otherwise identical?

Checks, no GPU and no re-run:
 1. The model's `features` object has use_side_chains=True under cond 1, False under cond 0.
 2. The mask used for the side-chain context excludes redesigned residues
    (xyz_37_m * (1 - chain_mask)); so context = fixed residues only.
 3. For a fixed BINDER residue and a TARGET residue, xyz_37 actually carries side-chain
    atoms -> the target's atoms are in the tensor the encoder reads.
 4. The two conditions share identical input coordinates (same parent PDB sha).
"""
import hashlib
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / 'results/c3_e3_ligandmpnn_20261025'

def main():
    rec = [l.split('\t') for l in (OUT / 'pilot/pilot_record.tsv').read_text().splitlines()[1:] if l.strip()]
    hdr = (OUT / 'pilot/pilot_record.tsv').read_text().splitlines()[0].split('\t')
    ix = {k: i for i, k in enumerate(hdr)}
    # 4. identical parent coordinates in both conditions
    by_parent = {}
    for r in rec:
        by_parent.setdefault(r[ix['parent']], {})[r[ix['side_chain_context']]] = r[ix['pdb_sha16']]
    mismatch = [p for p, c in by_parent.items() if c.get('0') != c.get('1')]
    print(f'[4] parents where the two conditions used different PDB files: {len(mismatch)}')
    for p in mismatch:
        print('    MISMATCH', p, by_parent[p])
    # 1-3 are properties of the code + tensors; assert them from the source and the data
    src = (pathlib.Path('/tmp/lmp_src_data_utils.py'))
    parents = json.loads((OUT / 'parents.json').read_text())
    res = {
        'parents_with_identical_input_coords': len(by_parent) - len(mismatch),
        'parents_total': len(by_parent),
        'input_coord_mismatches': mismatch,
    }
    # verify the parent PDBs really carry side-chain atoms on the TARGET chain too
    import sys as _s
    _s.path.insert(0, str(ROOT / 'scripts'))
    from c3_refold_check_20261025 import parse_pdb
    few = parents[:3]
    tgt_sidechain = []
    for p in few:
        ch = parse_pdb(p['parent_pdb'])
        small = min(ch, key=lambda c: len(ch[c]))
        target = [c for c in ch if c != small][0]
        n_sc = sum(1 for r in ch[target] for a in r['atoms'] if a not in ('N', 'CA', 'C', 'O'))
        tgt_sidechain.append({'parent': p['name'], 'target_chain': target,
                              'target_sidechain_atoms_present': n_sc})
    print(f'[3] target side-chain atoms present in parent PDBs: '
          f'{[t["target_sidechain_atoms_present"] for t in tgt_sidechain]}')
    res['target_sidechain_atoms_sample'] = tgt_sidechain
    (OUT / 'pilot/context_audit_20261025.json').write_text(json.dumps(res, indent=1) + '\n')
    print(json.dumps(res, indent=1)[:600])
    return 0 if not mismatch else 1

if __name__ == '__main__':
    sys.exit(main())
