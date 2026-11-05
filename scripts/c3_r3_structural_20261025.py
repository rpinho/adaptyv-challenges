#!/usr/bin/env python3
"""R3 structural evidence: identical constants, functions and frozen groove set to rounds 1-2.

Pass = binder pLDDT >=80, >=5 groove residues, >=20 contacts <=5 A, ZERO heavy-atom
pairs <2.0 A, clean chain integrity, binder length matching the designed sequence, and
target length 111. Every frozen screen-input design gets a record; a missing artifact is
an explicit incomplete/fail, never a silent omission.

Inputs : results/c3_r3_20261025/screen/<name>/complex_rank_001.pdb
Output : results/c3_r3_20261025/structural_checks_20261025.json
"""
import csv
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from c3_refold_check_20261025 import (  # noqa: E402
    parse_pdb, contacts, chain_integrity, _seqsha,
    GROOVE_CONTACT_A, CLASH_A, MIN_GROOVE_RESIDUES, MIN_TOTAL_CONTACTS, BINDER_PLDDT_MIN)

R3 = ROOT / 'results/c3_r3_20261025'
SCREEN_DIR = R3 / 'screen'
OUT = R3 / 'structural_checks_20261025.json'


def artifact_index(screen_dir):
    """Map design name -> all pulled rank-001 PDB parents.

    The puller preserves each pod's shard, so the real layout is
    screen/pN/<name>/complex_rank_001.pdb, not screen/<name>/...
    Multiple hits are retained so they can be reported as bad evidence.
    """
    index = {}
    if not screen_dir.exists():
        return index
    for pdb in sorted(screen_dir.rglob('complex_rank_001.pdb')):
        index.setdefault(pdb.parent.name, []).append(pdb)
    return index


def main():
    groove = json.loads((ROOT / 'results/c3_groove_reference_20261025.json').read_text())
    groove_set = set(groove['groove_residues_1based'])
    seqs = {r['name']: r['binder']
            for r in csv.DictReader(open(R3 / 'screen_input_20261025.csv'))}
    artifacts = artifact_index(SCREEN_DIR)
    out = {}
    for name in sorted(seqs):
        hits = artifacts.get(name, [])
        if not hits:
            out[name] = {'pass': False, 'status': 'incomplete',
                         'reason': 'complex_rank_001.pdb missing'}
            continue
        if len(hits) > 1:
            out[name] = {'pass': False, 'status': 'fail',
                         'reason': f'{len(hits)} duplicate structural artifacts',
                         'artifact_dirs': [str(p.parent) for p in hits]}
            continue
        pdb = hits[0]
        ch = parse_pdb(pdb)
        if len(ch) != 2:
            out[name] = {'pass': False, 'status': 'fail',
                         'reason': f'expected 2 chains, found {len(ch)}'}
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
            checks['reason'] = 'no R3 sequence for this name'
        elif len(binder) != len(sequence):
            passed = False
            checks['reason'] = 'binder length differs from designed sequence'
        elif checks['target_len'] != 111:
            passed = False
            checks['reason'] = f'target length {checks["target_len"]} != 111'
        checks['pass'] = bool(passed)
        checks['status'] = 'pass' if passed else 'fail'
        out[name] = checks
    OUT.write_text(json.dumps(out, indent=1) + '\n')
    ok = sum(1 for v in out.values() if v.get('pass'))
    incomplete = sum(1 for v in out.values() if v.get('status') == 'incomplete')
    print(f'R3 structural: {ok}/{len(out)} pass, {incomplete} incomplete -> '
          f'{OUT.relative_to(ROOT)}')
    for n, v in sorted(out.items()):
        if not v.get('pass'):
            print(f'  FAIL {n}: {v.get("reason") or v.get("chain_integrity_problems") or ""}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
