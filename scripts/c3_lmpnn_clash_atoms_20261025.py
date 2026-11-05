#!/usr/bin/env python3
"""Per-design clash atom identities for the LigandMPNN pilot (same classifier as E3)."""
import glob, json, pathlib, sys
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from c3_refold_check_20261025 import parse_pdb, heavy_atoms  # noqa: E402
BACKBONE = {'N', 'CA', 'C', 'O'}
CUT2 = 2.0 ** 2
S = ROOT / 'results/c3_e3_ligandmpnn_20261025/screen'
OUT = ROOT / 'results/c3_e3_ligandmpnn_20261025/clash_atoms_pilot_20261025.json'

def main():
    out = {}
    for pdb in sorted(glob.glob(str(S / '**' / 'complex_rank_001.pdb'), recursive=True)):
        name = pathlib.Path(pdb).parent.name
        ch = parse_pdb(pdb)
        if len(ch) != 2:
            out[name] = {'error': f'{len(ch)} chains'}; continue
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
                     'n_sidechain_involved': len(pairs) - n_bb, 'pairs': pairs}
    OUT.write_text(json.dumps(out, indent=1) + '\n')
    tot = sum(v.get('n_pairs', 0) for v in out.values())
    bb = sum(v.get('n_backbone_backbone', 0) for v in out.values())
    print(f'{len(out)} complexes; {tot} clash pairs; {bb} backbone-backbone')
    return 0

if __name__ == '__main__':
    sys.exit(main())
