#!/usr/bin/env python3
"""E3 follow-up: pick clashing parents and compute each one's design window.

Astra's spec: freeze target sequence+coordinates; redesign ONLY binder residues within 8 A of
any target heavy atom; keep the rest fixed. Backbone-backbone overlaps are excluded because a
sequence rescue cannot fix them (measured: 0 such pairs in E3).

Output: results/c3_e3_ligandmpnn_20261025/parents.json
"""
import glob
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from c3_refold_check_20261025 import parse_pdb, heavy_atoms  # noqa: E402

E3 = ROOT / 'results/c3_e3_111_20261025'
OUT = ROOT / 'results/c3_e3_ligandmpnn_20261025'
RADIUS = 8.0
MAX_PARENTS = 12


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    st = json.loads((E3 / 'structural_checks_20261025.json').read_text())
    sc = json.loads((E3 / 'screen_scores_20261025.json').read_text())['scores']
    clashes = json.loads((E3 / 'clash_atoms_20261025.json').read_text())
    cands = [(n, st[n]['heavy_atom_pairs_lt2A'], sc[n]['iptm'])
             for n in st if st[n].get('heavy_atom_pairs_lt2A', 0) > 0
             and (sc.get(n, {}).get('iptm') or 0) >= 0.850
             and not clashes.get(n, {}).get('n_backbone_backbone')]
    cands.sort(key=lambda x: (-x[1], -x[2], x[0]))
    picked = cands[:MAX_PARENTS]
    out = []
    for name, nclash, iptm in picked:
        pdb = glob.glob(str(E3 / 'screen' / '**' / name / 'complex_rank_001.pdb'), recursive=True)[0]
        ch = parse_pdb(pdb)
        small = min(ch, key=lambda c: len(ch[c]))
        large = [c for c in ch if c != small][0]
        binder, target = ch[small], ch[large]
        t_at = [xyz for res in target for xyz in heavy_atoms(res).values()]
        designable = []
        for i, res in enumerate(binder):
            near = False
            for xyz in heavy_atoms(res).values():
                for t in t_at:
                    if sum((xyz[k] - t[k]) ** 2 for k in range(3)) <= RADIUS ** 2:
                        near = True
                        break
                if near:
                    break
            if near:
                designable.append(i + 1)
        out.append({'name': name, 'clashes': nclash, 'iptm': iptm,
                    'parent_pdb': pdb, 'binder_len': len(binder), 'target_len': len(target),
                    'designable_binder_residues_8A': designable,
                    'n_designable': len(designable),
                    'fixed_binder_residues': [i + 1 for i in range(len(binder))
                                              if (i + 1) not in designable]})
    (OUT / 'parents.json').write_text(json.dumps(out, indent=1) + '\n')
    print(f'{len(out)} parents')
    for p in out:
        print(f"  {p['name']:34s} clashes={p['clashes']} iptm={p['iptm']:.3f} "
              f"designable={p['n_designable']}/{p['binder_len']}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
