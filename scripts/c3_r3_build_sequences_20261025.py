#!/usr/bin/env python3
"""Build R3 (name,sequence) CSV from pulled MPNN FASTA, excluding sample 0 = native.
Same convention as rounds 2 and E3: only sampled designs enter the refold/screen queue."""
import csv, pathlib, re, sys, collections

ROOT = pathlib.Path(__file__).resolve().parents[1]
SRC = pathlib.Path('/tmp/r3mpnn')
OUT = ROOT / 'results/c3_r3_20261025'

def main():
    rows, seen, stats = [], set(), collections.Counter()
    for fa in sorted(SRC.glob('*/mpnn/*/seqs/*.fa')):
        bb = fa.parent.parent.name
        pod = fa.parts[-5]
        cur = None
        for line in fa.read_text().splitlines():
            if line.startswith('>'):
                hdr = line[1:]
                m = re.search(r'sample=(\d+)', hdr)
                sample = m.group(1) if m else None
                cur = (sample, hdr)
            elif line.strip() and cur:
                sample, hdr = cur
                cur = None
                if sample is None or sample == '0':
                    stats['native_or_unmarked'] += 1
                    continue
                name = f'{bb}_s{sample}'
                if name in seen:
                    stats['dup'] += 1
                    continue
                seen.add(name)
                rows.append({'name': name, 'sequence': line.strip(), 'pod': pod,
                             'backbone': bb, 'sample': sample})
                stats['kept'] += 1
    dst = OUT / 'r3_mpnn_sequences.csv'
    dst.parent.mkdir(parents=True, exist_ok=True)
    with dst.open('w', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=['name', 'sequence', 'pod', 'backbone', 'sample'])
        w.writeheader(); w.writerows(rows)
    print(f'{len(rows)} designs from {len({r["backbone"] for r in rows})} backbones -> {dst}')
    print(dict(stats), 'unique', len(seen))
    return 0

if __name__ == '__main__':
    sys.exit(main())
