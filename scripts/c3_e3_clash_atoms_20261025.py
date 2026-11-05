#!/usr/bin/env python3
"""Classify every inter-chain heavy-atom pair < 2.0 A: backbone-backbone vs side-chain-involved.

Astra's precondition for a sequence-redesign rescue: backbone-backbone overlaps CANNOT be fixed
by changing side chains, so they must be excluded and counted separately. Read-only.

Output: results/c3_e3_111_20261025/clash_atoms_20261025.json
"""
import glob
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from c3_refold_check_20261025 import parse_pdb, heavy_atoms  # noqa: E402

E3 = ROOT / 'results/c3_e3_111_20261025'
BACKBONE = {'N', 'CA', 'C', 'O'}
CUT2 = 2.0 ** 2


def main():
    out = {}
    for pdb in sorted(glob.glob(str(E3 / 'screen' / '**' / 'complex_rank_001.pdb'), recursive=True)):
        name = pathlib.Path(pdb).parent.name
        ch = parse_pdb(pdb)
        if len(ch) != 2:
            out[name] = {'error': f'{len(ch)} chains'}
            continue
        small = min(ch, key=lambda c: len(ch[c]))
        large = [c for c in ch if c != small][0]
        binder, target = ch[small], ch[large]
        pairs = []
        ba = [(ri, an, xyz) for ri, res in enumerate(binder) for an, xyz in heavy_atoms(res).items()]
        ta = [(ri, an, xyz) for ri, res in enumerate(target) for an, xyz in heavy_atoms(res).items()]
        for bi, ban, bxyz in ba:
            for ti, tan, txyz in ta:
                d2 = sum((bxyz[k] - txyz[k]) ** 2 for k in range(3))
                if d2 <= CUT2:
                    bb = ban in BACKBONE and tan in BACKBONE
                    pairs.append({'binder_res': bi + 1, 'binder_resname': binder[bi]['resname'],
                                  'binder_atom': ban, 'target_res': ti + 1,
                                  'target_resname': target[ti]['resname'],
                                  'target_atom': tan, 'dist': round(d2 ** 0.5, 3),
                                  'backbone_backbone': bb})
        n_bb = sum(1 for p in pairs if p['backbone_backbone'])
        out[name] = {'n_pairs': len(pairs), 'n_backbone_backbone': n_bb,
                     'n_sidechain_involved': len(pairs) - n_bb,
                     'rescuable_by_sequence': len(pairs) - n_bb > 0,
                     'pairs': pairs}
    (E3 / 'clash_atoms_20261025.json').write_text(json.dumps(out, indent=1) + '\n')
    tot = sum(v['n_pairs'] for v in out.values())
    bb = sum(v['n_backbone_backbone'] for v in out.values())
    tainted = sorted(k for k, v in out.items() if v.get('n_backbone_backbone'))
    print(f'{len(out)} complexes; {tot} clash pairs; {bb} backbone-backbone')
    print(f'complexes with >=1 backbone-backbone overlap (NOT sequence-rescuable): {len(tainted)}')
    for k in tainted:
        print(f'  {k}: {out[k]["n_backbone_backbone"]} bb / {out[k]["n_pairs"]} total')
    return 0


if __name__ == '__main__':
    sys.exit(main())
