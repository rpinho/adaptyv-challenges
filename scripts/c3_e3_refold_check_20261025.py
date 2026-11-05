#!/usr/bin/env python3
"""E3 refold QC: identical computation and thresholds to round 2 (Kimi §4).

mean pLDDT >= 80, frac(residues pLDDT>=70) >= 0.90, CA RMSD to designed backbone <= 3.0.
Reuses parse_pdb/kabsch_rmsd from c3_refold_check_20261025.py (the round-2 code).

Inputs : results/c3_e3_111_20261025/esm/*.pdb        (ESMFold monomers, <bb>_s<N>.pdb)
         results/c3_e3_111_20261025/bb_pdb/*.pdb     (designed backbones as PDB)
Output : results/c3_e3_111_20261025/refold_checks_20261025.json
"""
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from c3_refold_check_20261025 import parse_pdb, kabsch_rmsd  # noqa: E402

E3 = ROOT / 'results/c3_e3_111_20261025'
ESM = E3 / 'esm'
BBPDB = E3 / 'bb_pdb'
OUT = E3 / 'refold_checks_20261025.json'
MEAN_MIN, FRAC70_MIN, RMSD_MAX = 80.0, 0.90, 3.0


def binder_ca(path):
    ch = parse_pdb(path)
    small = min(ch, key=lambda c: len(ch[c]))
    return [r['atoms'].get('CA') for r in ch[small]]


def main():
    out = {}
    for pdb in sorted(ESM.glob('*.pdb')):
        name = pdb.stem
        tag = name.rsplit('_s', 1)[0]
        mono = parse_pdb(pdb)
        if len(mono) != 1:
            out[name] = {'pass': False, 'reason': f'monomer file has {len(mono)} chains'}
            continue
        residues = list(mono.values())[0]
        plddt = [b for res in residues for b in res['bfac'].values()]
        mean = sum(plddt) / len(plddt)
        frac70 = sum(1 for b in plddt if b >= 70) / len(plddt)
        bb = BBPDB / f'{tag}.pdb'
        rmsd = None
        if bb.exists():
            b = binder_ca(bb)
            m = [r['atoms'].get('CA') for r in residues]
            if len(m) == len(b) and all(x is not None for x in m + b):
                rmsd = kabsch_rmsd(m, b)
        out[name] = {'backbone': tag,
                     'refold_mean_plddt': round(mean, 2),
                     'refold_frac_residues_plddt_ge70': round(frac70, 4),
                     'ca_rmsd_vs_designed_backbone': None if rmsd is None else round(rmsd, 3),
                     'pass': bool(mean >= MEAN_MIN and frac70 >= FRAC70_MIN and
                                  rmsd is not None and rmsd <= RMSD_MAX)}
    OUT.write_text(json.dumps(out, indent=1) + '\n')
    npass = sum(1 for v in out.values() if v['pass'])
    print(f'{npass}/{len(out)} pass -> {OUT.relative_to(ROOT)}')
    for k, v in sorted(out.items()):
        if not v['pass']:
            print(f"  FAIL {k} plddt={v.get('refold_mean_plddt')} frac70="
                  f"{v.get('refold_frac_residues_plddt_ge70')} rmsd={v.get('ca_rmsd_vs_designed_backbone')}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
