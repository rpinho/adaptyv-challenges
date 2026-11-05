#!/usr/bin/env python3
"""R3 ESMFold refold QC: same computation and thresholds as rounds 1-2 and E3.

Inputs : results/c3_r3_20261025/mpnn_sequences.csv   (exact designed sequences)
         results/c3_r3_20261025/esm/<name>.pdb       (ESMFold monomers)
         results/c3_r3_20261025/backbone_pdb/<bb>.pdb (designed backbones)
Output : results/c3_r3_20261025/refold_checks_20261025.json

Every expected design gets a record. A missing ESM file or an unmeasurable RMSD is a
FAIL, never an omission. Thresholds: mean pLDDT >= 80, frac(pLDDT >= 70) >= 0.90,
CA RMSD to the designed backbone <= 3.0 A.
"""
import csv
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from c3_refold_check_20261025 import parse_pdb, kabsch_rmsd  # noqa: E402

R3 = ROOT / 'results/c3_r3_20261025'
ESM = R3 / 'esm'
BB = R3 / 'backbone_pdb'
OUT = R3 / 'refold_checks_20261025.json'
MEAN_MIN, FRAC70_MIN, RMSD_MAX = 80.0, 0.90, 3.0


def binder_ca(path):
    ch = parse_pdb(path)
    small = min(ch, key=lambda c: len(ch[c]))
    return [r['atoms'].get('CA') for r in ch[small]]


def main():
    seqs = list(csv.DictReader(open(R3 / 'mpnn_sequences.csv')))
    out = {}
    for row in seqs:
        name = row['name']
        bb = name.rsplit('_s', 1)[0]
        pdb = ESM / f'{name}.pdb'
        if not pdb.exists():
            out[name] = {'backbone': bb, 'pass': False, 'reason': 'ESMFold output missing'}
            continue
        mono = parse_pdb(pdb)
        if len(mono) != 1:
            out[name] = {'backbone': bb, 'pass': False,
                         'reason': f'monomer file has {len(mono)} chains'}
            continue
        residues = list(mono.values())[0]
        if len(residues) != len(row['sequence']):
            out[name] = {'backbone': bb, 'pass': False,
                         'reason': f'refold length {len(residues)} != designed '
                                   f'{len(row["sequence"])}'}
            continue
        plddt = [b for res in residues for b in res['bfac'].values()]
        mean = sum(plddt) / len(plddt) if plddt else 0.0
        frac70 = (sum(1 for b in plddt if b >= 70) / len(plddt)) if plddt else 0.0
        pdb_bb = BB / f'{bb}.pdb'
        rmsd = None
        if pdb_bb.exists():
            b = binder_ca(pdb_bb)
            m = [r['atoms'].get('CA') for r in residues]
            if len(m) == len(b) and all(x is not None for x in m + b):
                rmsd = kabsch_rmsd(m, b)
        out[name] = {
            'backbone': bb,
            'refold_mean_plddt': round(mean, 2),
            'refold_frac_residues_plddt_ge70': round(frac70, 4),
            'ca_rmsd_vs_designed_backbone': None if rmsd is None else round(rmsd, 3),
            'pass': bool(mean >= MEAN_MIN and frac70 >= FRAC70_MIN and
                         rmsd is not None and rmsd <= RMSD_MAX),
        }
        if rmsd is None:
            out[name]['reason'] = 'CA RMSD not measurable'
    OUT.write_text(json.dumps(out, indent=1) + '\n')
    npass = sum(1 for v in out.values() if v['pass'])
    measured = [v['ca_rmsd_vs_designed_backbone'] for v in out.values()
                if v['ca_rmsd_vs_designed_backbone'] is not None]
    try:
        shown = OUT.relative_to(ROOT)
    except ValueError:
        shown = OUT
    print(f'R3 refold: {npass}/{len(out)} pass ({len(seqs)} MPNN designs) -> {shown}')
    if measured:
        rms = sorted(measured)
        print(f'RMSD min/median/max {rms[0]:.3f}/{rms[len(rms)//2]:.3f}/{rms[-1]:.3f}')
    for name, v in sorted(out.items()):
        if not v['pass']:
            print(f"  FAIL {name}: {v.get('reason') or v.get('ca_rmsd_vs_designed_backbone')}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
