#!/usr/bin/env python3
"""Round-2 structural evidence, identical constants to the round-1 checks.

Reuses parse_pdb/contacts/chain_integrity/_seqsha and the SAME frozen groove definition
(results/c3_groove_reference_20261025.json) from c3_refold_check_20261025.py, so round-2
structural checks are the same computation as round 1. Writes a NEW file.
"""
import glob
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from c3_refold_check_20261025 import (  # noqa: E402
    parse_pdb, contacts, chain_integrity, _seqsha,
    GROOVE_CONTACT_A, CLASH_A, MIN_GROOVE_RESIDUES, MIN_TOTAL_CONTACTS, BINDER_PLDDT_MIN)

R2 = ROOT / 'results/c3_round2_111_20261025'
SCREEN_DIR = R2 / 'screen'
OUT = R2 / 'structural_checks_20261025.json'


def main():
    groove = json.loads((ROOT / 'results/c3_groove_reference_20261025.json').read_text())
    groove_set = set(groove['groove_residues_1based'])
    seqs = {f"{s['backbone']}_s{s['sample']}": s['seq']
            for s in json.loads((R2 / 'mpnn_sequences_20261025.json').read_text())
            if s['sample'] > 0}
    out = {}
    for pdb in sorted(glob.glob(str(SCREEN_DIR / '*/*/*/complex_rank_001.pdb'))):
        name = pathlib.Path(pdb).parent.name
        ch = parse_pdb(pdb)
        if len(ch) != 2:
            out[name] = {'pass': False, 'reason': f'expected 2 chains, found {len(ch)}'}
            continue
        small = min(ch, key=lambda c: len(ch[c]))
        large = [c for c in ch if c != small][0]
        binder, target = ch[small], ch[large]
        binder_plddt = [b for res in binder for b in res['bfac'].values()]
        mean_binder = sum(binder_plddt) / len(binder_plddt) if binder_plddt else 0.0
        ncontacts, pairs = contacts(binder, target, GROOVE_CONTACT_A)
        groove_hits = sorted({ti + 1 for _, ti in pairs} & groove_set)
        clash_n, _ = contacts(binder, target, CLASH_A)
        integrity = chain_integrity(binder)
        sequence = seqs.get(name)
        checks = {
            'binder_len': len(binder),
            'target_len': len(target),
            'binder_mean_plddt': round(mean_binder, 2),
            'target_binder_contacts_le5A': ncontacts,
            'groove_residues_contacted': len(groove_hits),
            'groove_residues': groove_hits,
            'heavy_atom_pairs_lt2A': clash_n,
            'chain_integrity_problems': integrity[:10],
            'sequence_sha256': _seqsha(sequence) if sequence else None,
        }
        passed = (checks['binder_mean_plddt'] >= BINDER_PLDDT_MIN
                  and checks['groove_residues_contacted'] >= MIN_GROOVE_RESIDUES
                  and checks['target_binder_contacts_le5A'] >= MIN_TOTAL_CONTACTS
                  and checks['heavy_atom_pairs_lt2A'] == 0
                  and not integrity)
        if sequence is None:
            passed = False
            checks['reason'] = 'no round-2 sequence for this name'
        elif len(binder) != len(sequence):
            passed = False
            checks['reason'] = 'binder length differs from designed sequence'
        elif checks['target_len'] != 111:
            passed = False
            checks['reason'] = f'target length {checks["target_len"]} != 111'
        checks['pass'] = passed
        out[name] = checks
    OUT.write_text(json.dumps(out, indent=1) + '\n')
    ok = sum(1 for v in out.values() if v.get('pass'))
    print(f'round-2 structural: {ok}/{len(out)} pass -> {OUT}')
    for n, v in sorted(out.items()):
        if not v.get('pass'):
            print(f'  FAIL {n}: {v.get("reason") or v.get("chain_integrity_problems") or ""}')


if __name__ == '__main__':
    main()
