#!/usr/bin/env python3
"""Round-2 ESMFold refold QC: pLDDT/frac70 + Cα RMSD to the designed binder backbone.

Reuses the exact kabsch_rmsd and PDB parsing from c3_refold_check_20261025.py, so the
round-2 refold gate is the same computation that produced c3_refold_checks_20261025.json.
Kimi round-2 plan §4: mean pLDDT >= 80, frac(res>=70) >= 0.90, CA RMSD <= 3.0.
Writes a NEW file; never touches the v7 evidence file.
"""
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from c3_refold_check_20261025 import parse_pdb, kabsch_rmsd  # noqa: E402

ESM = ROOT / 'results/c3_round2_111_20261025/esm72'
BACKBONES = ROOT / 'results/c3_round2_111_20261025/pulled'
OUT = ROOT / 'results/c3_round2_111_20261025/refold_checks_20261025.json'

MEAN_MIN, FRAC70_MIN, RMSD_MAX = 80.0, 0.90, 3.0


def binder_ca(complex_cif_pdb):
    ch = parse_pdb(complex_cif_pdb)
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
        pdb_bb = ROOT / 'results/c3_round2_111_20261025/backbone_pdb' / f'{tag}.pdb'
        rmsd = None
        if pdb_bb.exists():
            b = binder_ca(pdb_bb)
            m = [r['atoms'].get('CA') for r in residues]
            if len(m) == len(b) and all(x is not None for x in m + b):
                rmsd = kabsch_rmsd(m, b)
        passed = (mean >= MEAN_MIN and frac70 >= FRAC70_MIN and
                  rmsd is not None and rmsd <= RMSD_MAX)
        out[name] = {'backbone': tag,
                     'refold_mean_plddt': round(mean, 2),
                     'refold_frac_residues_plddt_ge70': round(frac70, 4),
                     'ca_rmsd_vs_designed_backbone': None if rmsd is None else round(rmsd, 3),
                     'pass': passed}
    OUT.write_text(json.dumps(out, indent=1) + '\n')
    npass = sum(1 for v in out.values() if v['pass'])
    print(f'{npass}/{len(out)} pass -> {OUT}')
    rms = sorted((v['ca_rmsd_vs_designed_backbone'] for v in out.values()
                  if v['ca_rmsd_vs_designed_backbone'] is not None))
    print('rmsd min/median/max', rms[0], rms[len(rms) // 2], rms[-1])


if __name__ == '__main__':
    main()
