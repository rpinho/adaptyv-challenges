#!/usr/bin/env python3
"""Build the sampling-depth arm's sequence table and frozen screen input.

Arm: c3_sampling_depth_v1_20261025 (Astra 2026-10-25 03:21).
Reads the arm's own MPNN output (never the R3 tree), takes only sampled designs
(sample != 0; sample 0 is the native sequence), applies the SAME four pre-registered
soluble filters and the SAME 111-mer target as R3, and writes a per-pod projection.

Every emitted sequence must correspond to a manifest slot. Missing slots are recorded as
explicit failures, never silently dropped: the manifest is frozen before sampling, so a
missing draw is an accountability result, not a reason to sample a replacement.

Writes only results/c3_sampling_depth_v1_20261025/.
"""
import csv, hashlib, json, pathlib, re, sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from c3_soluble_filters_20261025 import failures as soluble_failures, FilterError  # noqa: E402

OUT = ROOT / 'results/c3_sampling_depth_v1_20261025'
MDIR = OUT / 'mpnn'
TARGET_SOURCE = ROOT / 'results/c3_round2_111_20261025/screen_input_24.csv'
TARGET_SHA = '5c2bae2dac5e467bf4e802473450a7ca3729990921bbe5c45cf6025531ef36b3'
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
    man = json.loads((OUT / 'manifest.json').read_text())
    slots = {s['name']: s for s in man['slots']}
    target = read_target()

    rows, problems, seen = [], [], set()
    for fa in sorted(MDIR.glob('*/*/sd*/seqs/*.fa')):
        draw_dir = fa.parent.parent          # .../<backbone>/sd<k>
        bb = draw_dir.parent.name
        draw = draw_dir.name                 # sd1 / sd2
        k = draw[2:]
        pod = bb.split('_')[0]
        cur = None
        for line in fa.read_text().splitlines():
            if line.startswith('>'):
                cur = line[1:]
                continue
            if not line.strip() or cur is None:
                continue
            hdr, cur = cur, None
            m = re.search(r'sample=(\d+)', hdr)
            sample = m.group(1) if m else None
            if sample in (None, '0'):
                continue
            name = f'{bb}_sd{k}'
            if name in seen:
                problems.append(f'{name}: duplicate output')
                continue
            seen.add(name)
            if name not in slots:
                problems.append(f'{name}: not in frozen manifest')
                continue
            seq = line.strip()
            if sha_text(seq) == sha_text(slots[name]['backbone']):
                problems.append(f'{name}: sequence equals backbone string')
            try:
                fails = soluble_failures(seq)
            except FilterError as ex:
                fails = [f'filter error: {ex}']
            rows.append({'name': name, 'sequence': seq, 'pod': pod, 'backbone': bb,
                         'draw': k, 'eligible': not fails,
                         'filter_failures': ';'.join(fails) if fails else ''})

    missing = sorted(set(slots) - seen)
    if not rows:
        print('BUILD FAIL no sampled sequences found under', MDIR, file=sys.stderr)
        return 4

    OUT.mkdir(parents=True, exist_ok=True)
    with (OUT / 'sequences.csv').open('w', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=['name', 'sequence', 'pod', 'backbone', 'draw',
                                           'eligible', 'filter_failures'])
        w.writeheader(); w.writerows(sorted(rows, key=lambda r: r['name']))

    eligible = [r for r in rows if r['eligible']]
    if len(eligible) > man['caps']['max_af2m_admissions']:
        print('BUILD FAIL eligible exceeds cap', len(eligible), file=sys.stderr)
        return 4

    with (OUT / 'screen_input.csv').open('w', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()
        for r in sorted(eligible, key=lambda r: r['name']):
            w.writerow({'name': r['name'], 'binder': r['sequence'], 'target': target,
                        'source': 'c3_sampling_depth_v1_20261025'})

    poddir = OUT / 'screen_inputs'
    poddir.mkdir(exist_ok=True)
    per_pod = {}
    for pod in sorted({r['pod'] for r in eligible}):
        pr = [r for r in eligible if r['pod'] == pod]
        per_pod[pod] = len(pr)
        with (poddir / f'{pod}.csv').open('w', newline='') as fh:
            w = csv.DictWriter(fh, fieldnames=FIELDS)
            w.writeheader()
            for r in sorted(pr, key=lambda r: r['name']):
                w.writerow({'name': r['name'], 'binder': r['sequence'], 'target': target,
                            'source': 'c3_sampling_depth_v1_20261025'})

    manifest = {
        'arm': man['arm'],
        'target_sha256': TARGET_SHA,
        'arm_manifest_sha256': hashlib.sha256((OUT / 'manifest.json').read_bytes()).hexdigest(),
        'sequences_sha256': hashlib.sha256((OUT / 'sequences.csv').read_bytes()).hexdigest(),
        'screen_input_sha256': hashlib.sha256((OUT / 'screen_input.csv').read_bytes()).hexdigest(),
        'n_slots': len(slots),
        'n_sampled': len(rows),
        'n_eligible': len(eligible),
        'n_filter_failed': len(rows) - len(eligible),
        'n_missing_slots': len(missing),
        'missing_slots': missing,
        'problems': problems,
        'per_pod': per_pod,
    }
    (OUT / 'screen_input_manifest.json').write_text(json.dumps(manifest, indent=1) + '\n')
    print(f"SD build: {len(rows)} sampled, {len(eligible)} eligible, "
          f"{len(rows)-len(eligible)} filter-failed, {len(missing)} missing slots")
    print(f"  screen_input sha {manifest['screen_input_sha256'][:12]}  per pod {per_pod}")
    if problems:
        print('  PROBLEMS:', problems[:5])
    return 0 if not problems else 4


if __name__ == '__main__':
    sys.exit(main())
