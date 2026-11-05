#!/bin/bash
# Pull R3 MPNN outputs and build the exact name,sequence CSV. Fail closed unless the
# input is exactly 120 backbones x 2 designed sequences (sample 0 = native, excluded).
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1
KEY=$HOME/.ssh/runpod_ed25519
R3=results/c3_r3_20261025
mkdir -p "$R3/mpnn" "$R3/mpnn_logs"
for spec in "p1:63.141.33.138:22113" "p2:194.68.245.32:22065" \
            "p3:69.30.85.102:22129" "p4:194.68.245.69:22022" \
            "p5:194.68.245.147:22117"; do
  pod=${spec%%:*}; rest=${spec#*:}; host=${rest%%:*}; port=${rest##*:}
  mkdir -p "$R3/mpnn/$pod"
  rsync -az --timeout=120 -e "ssh -i $KEY -p $port -o ConnectTimeout=10 -o StrictHostKeyChecking=no -o BatchMode=yes" \
    "root@$host:/workspace/r3/mpnn/" "$R3/mpnn/$pod/" || echo "WARN rsync mpnn $pod failed"
  rsync -az --timeout=60 -e "ssh -i $KEY -p $port -o ConnectTimeout=10 -o StrictHostKeyChecking=no -o BatchMode=yes" \
    "root@$host:/workspace/r3/logs/mpnn_records.jsonl" "$R3/mpnn_logs/${pod}_records.jsonl" 2>/dev/null || true
done
python3 - <<'PY'
import csv, hashlib, json, pathlib, re, sys
ROOT = pathlib.Path('.')
R3 = ROOT / 'results/c3_r3_20261025'
sys.path.insert(0, str(ROOT / 'scripts'))
import c3_r3_queue_20261025 as Q
import c3_soluble_filters_20261025 as soluble
alloc = Q.allocation_map()
rows, per = [], {}
seen_seq, problems = {}, []
for fa in sorted((R3 / 'mpnn').glob('*/**/seqs/*.fa')):
    bb = fa.stem
    if bb not in alloc:
        problems.append(f'unexpected FASTA {fa}')
        continue
    name, sample = None, None
    samples = {}
    for line in fa.read_text().splitlines():
        if line.startswith('>'):
            hdr = line[1:]
            name = hdr.split(',')[0].strip()
            m = re.search(r'(?:^|,\s*)sample=(\d+)', hdr)
            sample = int(m.group(1)) if m else None
        elif line:
            if sample is None or sample == 0 or 'T=' not in (name or ''):
                continue
            samples[sample] = line.strip()
    if sorted(samples) != [1, 2]:
        problems.append(f'{bb}: samples={sorted(samples)} (need exactly 1,2)')
        continue
    for sample, seq in sorted(samples.items()):
        outname = f'{bb}_s{sample}'
        lo, hi = {'52_64': (52, 64), '65_80': (65, 80), '81_100': (81, 100)}[alloc[bb]['bin']]
        if not (lo <= len(seq) <= hi):
            problems.append(f'{outname}: length {len(seq)} outside {lo}-{hi}')
        if not re.fullmatch(r'[ACDEFGHIKLMNPQRSTVWY]+', seq):
            problems.append(f'{outname}: non-canonical residue')
        if seq in seen_seq:
            problems.append(f'{outname}: duplicate sequence of {seen_seq[seq]}')
        seen_seq[seq] = outname
        rows.append({'name': outname, 'sequence': seq})
    per[bb] = len(samples)
missing = sorted(set(alloc) - set(per))
if missing: problems.append(f'missing backbones ({len(missing)}): {missing[:12]}')
out = R3 / 'mpnn_sequences.csv'
with out.open('w', newline='') as fh:
    w = csv.DictWriter(fh, fieldnames=['name', 'sequence'])
    w.writeheader(); w.writerows(rows)
report = {'n_backbones': len(per), 'n_sequences': len(rows),
          'missing': missing, 'problems': problems,
          'fasta_sha256': {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                           for p in sorted((R3 / 'mpnn').glob('*/**/seqs/*.fa'))}}
(R3 / 'mpnn_report.json').write_text(json.dumps(report, indent=1) + '\n')
print(f'R3 MPNN pull: {len(per)}/120 backbones, {len(rows)}/240 sequences')
for p in problems: print('  PROBLEM', p)
if problems:
    sys.exit(4)
PY
