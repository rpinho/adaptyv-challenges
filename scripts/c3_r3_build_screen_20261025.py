#!/usr/bin/env python3
"""Build the frozen R3 AF2M screen input from the queue. Writes only R3 files.

The target is read from the frozen round-2 screening input, not re-typed. Every
queued design must be present exactly once, every sequence must match its MPNN
hash, and no ineligible design may enter the screen. Per-pod CSVs are a
deterministic projection of the single frozen input.

Usage:
  python3 scripts/c3_r3_build_screen_20261025.py \
    --queue results/c3_r3_20261025/queue_20261025.json \
    --seqs results/c3_r3_20261025/mpnn_sequences.csv \
    --out results/c3_r3_20261025/screen_input_20261025.csv \
    --pod-dir results/c3_r3_20261025/screen_inputs
"""
import argparse
import csv
import hashlib
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from c3_soluble_filters_20261025 import failures as soluble_failures  # noqa: E402

TARGET_SHA = '5c2bae2dac5e467bf4e802473450a7ca3729990921bbe5c45cf6025531ef36b3'
TARGET_SOURCE = ROOT / 'results/c3_round2_111_20261025/screen_input_24.csv'
FIELDS = ['name', 'binder', 'target', 'source']


def sha_text(s):
    return hashlib.sha256(s.encode()).hexdigest()


def read_target():
    rows = list(csv.DictReader(open(TARGET_SOURCE)))
    targets = {r['target'].strip() for r in rows}
    if len(targets) != 1:
        raise SystemExit(f'target source has {len(targets)} distinct targets')
    t = targets.pop()
    if len(t) != 111 or sha_text(t) != TARGET_SHA:
        raise SystemExit('frozen 111-mer target hash/length mismatch')
    return t


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--queue', required=True)
    ap.add_argument('--seqs', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--pod-dir', required=True)
    a = ap.parse_args()

    queue = json.loads(pathlib.Path(a.queue).read_text())
    seqs = {r['name']: r['sequence'].strip() for r in csv.DictReader(open(a.seqs))}
    target = read_target()
    errors = []

    # The queue is authoritative about eligibility. All four soluble filters are
    # rechecked here so a corrupted/edited queue cannot smuggle a failure in.
    queued = []
    for pod in sorted(queue.get('queues', {})):
        for r in queue['queues'][pod]:
            name = r['name']
            seq = seqs.get(name)
            if seq is None:
                errors.append(f'{name}: missing from MPNN CSV')
                continue
            if r.get('sequence_sha256') != sha_text(seq):
                errors.append(f'{name}: queue/MPNN sequence hash mismatch')
            if not r.get('eligible'):
                errors.append(f'{name}: ineligible design in queue')
            fails = soluble_failures(seq)
            if fails:
                errors.append(f'{name}: soluble filter regression {fails}')
            expected = f"{r['backbone']}_s{r['sample']}"
            if name != expected:
                errors.append(f'{name}: expected provenance name {expected}')
            queued.append({'name': name, 'binder': seq, 'target': target,
                           'source': 'r3', 'pod': pod})

    names = [r['name'] for r in queued]
    if len(names) != len(set(names)):
        errors.append('duplicate design names in R3 queue')
    expected_total = queue.get('n_eligible')
    if expected_total != len(queued):
        errors.append(f'queue eligible={expected_total} but emitted={len(queued)}')
    if queue.get('n_designs') != len(seqs):
        errors.append(f"queue designs={queue.get('n_designs')} != MPNN CSV {len(seqs)}")
    if errors:
        for e in errors:
            print('ERROR', e, file=sys.stderr)
        return 4

    out = pathlib.Path(a.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open('w', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()
        for r in queued:
            w.writerow({k: r[k] for k in FIELDS})

    pod_dir = pathlib.Path(a.pod_dir)
    pod_dir.mkdir(parents=True, exist_ok=True)
    for pod in sorted(queue['queues']):
        rows = [r for r in queued if r['pod'] == pod]
        with (pod_dir / f'{pod}.csv').open('w', newline='') as fh:
            w = csv.DictWriter(fh, fieldnames=FIELDS)
            w.writeheader()
            for r in rows:
                w.writerow({k: r[k] for k in FIELDS})

    manifest = {
        'target_sha256': TARGET_SHA,
        'target_source': str(TARGET_SOURCE.relative_to(ROOT)),
        'queue': str(pathlib.Path(a.queue)),
        'queue_sha256': hashlib.sha256(pathlib.Path(a.queue).read_bytes()).hexdigest(),
        'seqs': str(pathlib.Path(a.seqs)),
        'seqs_sha256': hashlib.sha256(pathlib.Path(a.seqs).read_bytes()).hexdigest(),
        'n_designs': len(queued),
        'input_sha256': hashlib.sha256(out.read_bytes()).hexdigest(),
        'per_pod': {p: sum(r['pod'] == p for r in queued) for p in sorted(queue['queues'])},
    }
    (pathlib.Path(a.out).parent / 'screen_input_manifest_20261025.json').write_text(
        json.dumps(manifest, indent=1) + '\n')
    print(f"R3 screen input: {len(queued)} designs, sha {manifest['input_sha256']}")
    print('  per pod:', manifest['per_pod'])
    return 0


if __name__ == '__main__':
    sys.exit(main())
