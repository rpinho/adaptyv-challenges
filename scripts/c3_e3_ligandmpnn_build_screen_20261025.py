#!/usr/bin/env python3
"""Turn the LigandMPNN pilot FASTA record into the same 3-column AF2M screen CSV
used for E3 (name,binder,target), so the identical screen+gate pipeline applies."""
import csv, json, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / 'results/c3_e3_ligandmpnn_20261025'
RED = OUT / 'pilot' / 'rederived.tsv'

def main():
    rows = [l.split('\t') for l in RED.read_text().splitlines()[1:] if l.strip()]
    out = []
    seen = set()
    for parent, cond, _n, _nat, design, conf, sha in rows:
        binder, target = design.split(':')
        name = f'lm{cond}_{parent}'
        if name in seen:
            print('DUP', name); return 2
        seen.add(name)
        out.append({'name': name, 'binder': binder, 'target': target,
                    'source': f'ligandmpnn_sc{cond}'})
    dst = OUT / 'pilot' / 'screen_input_20261025.csv'
    with dst.open('w', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=['name', 'binder', 'target', 'source'])
        w.writeheader()
        w.writerows(out)
    target = {r['target'] for r in out}
    print(json.dumps({'rows': len(out), 'unique_names': len(seen),
                      'targets': len(target), 'target_len': len(next(iter(target))),
                      'binder_lens': [len(r['binder']) for r in out]}, indent=1))
    return 0 if len(target) == 1 else 1

if __name__ == '__main__':
    sys.exit(main())
