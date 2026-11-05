#!/usr/bin/env python3
"""Apply the refold filter and write the arm's final frozen AF2M screen input.

Eligible = soluble filters passed (records from c3_sd_build) AND refold QC passed
(same thresholds as R3). Writes the single frozen input plus a per-pod projection,
and records the admission cutoff epoch so no design can be admitted after the cap.

Caps (Astra 03:21): <=240 admissions; 3 h from arm start; stop admissions 20 min
before that; absolute stop 07:30 ET. The caller supplies the arm start epoch.
"""
import argparse, csv, hashlib, json, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
SD = ROOT / 'results/c3_sampling_depth_v1_20261025'
TARGET_SHA = '5c2bae2dac5e467bf4e802473450a7ca3729990921bbe5c45cf6025531ef36b3'
FIELDS = ['name', 'binder', 'target', 'source']


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--arm-start-epoch', type=int, required=True)
    ap.add_argument('--hours', type=float, default=3.0)
    ap.add_argument('--stop-margin-min', type=int, default=20)
    a = ap.parse_args()
    cutoff = int(a.arm_start_epoch + a.hours * 3600 - a.stop_margin_min * 60)
    hard = int(a.arm_start_epoch + a.hours * 3600)
    absolute = 1792927800  # 2026-10-25T07:30:00-04:00
    cutoff = min(cutoff, absolute - a.stop_margin_min * 60)
    hard = min(hard, absolute)

    manifest = json.loads((SD / 'screen_input_manifest.json').read_text())
    refold = json.loads((SD / 'refold_checks.json').read_text())
    rows = list(csv.DictReader(open(SD / 'sequences.csv')))
    src = list(csv.DictReader(open(SD / 'screen_input.csv')))
    targets = {r['target'] for r in src}
    if len(targets) != 1 or hashlib.sha256(next(iter(targets)).encode()).hexdigest() != TARGET_SHA:
        print('FINALIZE FAIL target mismatch', file=sys.stderr)
        return 4
    target = next(iter(targets))

    eligible, excluded = [], {}
    for r in rows:
        name = r['name']
        if r['eligible'] != 'True':
            excluded.setdefault('soluble', []).append(name)
            continue
        rv = refold.get(name)
        if rv is None:
            excluded.setdefault('refold_missing', []).append(name)
            continue
        if not rv.get('pass'):
            excluded.setdefault('refold', []).append(name)
            continue
        eligible.append({'name': name, 'binder': r['sequence'], 'target': target,
                         'source': 'c3_sampling_depth_v1_20261025', 'pod': r['pod']})

    if len(eligible) > 240:
        print('FINALIZE FAIL exceeds admission cap', len(eligible), file=sys.stderr)
        return 4

    with (SD / 'af2m_input.csv').open('w', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=FIELDS)
        w.writeheader()
        for r in sorted(eligible, key=lambda r: r['name']):
            w.writerow({k: r[k] for k in FIELDS})

    poddir = SD / 'af2m_inputs'
    poddir.mkdir(exist_ok=True)
    per_pod = {}
    for pod in sorted({r['pod'] for r in eligible}):
        pr = [r for r in eligible if r['pod'] == pod]
        per_pod[pod] = len(pr)
        with (poddir / f'{pod}.csv').open('w', newline='') as fh:
            w = csv.DictWriter(fh, fieldnames=FIELDS)
            w.writeheader()
            for r in sorted(pr, key=lambda r: r['name']):
                w.writerow({k: r[k] for k in FIELDS})

    out = {
        'arm': 'c3_sampling_depth_v1_20261025',
        'target_sha256': TARGET_SHA,
        'n_eligible': len(eligible),
        'n_excluded_soluble': len(excluded.get('soluble', [])),
        'n_excluded_refold': len(excluded.get('refold', [])),
        'n_excluded_refold_missing': len(excluded.get('refold_missing', [])),
        'excluded': {k: sorted(v) for k, v in excluded.items()},
        'per_pod': per_pod,
        'admission_cutoff_epoch': cutoff,
        'hard_stop_epoch': hard,
        'hard_stop_et': __import__('datetime').datetime.fromtimestamp(hard).astimezone().isoformat(),
        'arm_start_epoch': a.arm_start_epoch,
        'input_sha256': hashlib.sha256((SD / 'af2m_input.csv').read_bytes()).hexdigest(),
        'upstream_screen_input_sha256': manifest['screen_input_sha256'],
        'gate': 'unchanged: zero heavy-atom pairs <=2.0 A, iPTM>=0.85 all-rules PASS, same thresholds',
    }
    (SD / 'af2m_manifest.json').write_text(json.dumps(out, indent=1) + '\n')
    print(f"SD final input: {len(eligible)} eligible "
          f"(soluble-excluded {out['n_excluded_soluble']}, refold-excluded "
          f"{out['n_excluded_refold']}) -> {out['input_sha256'][:12]}")
    print(f"  per pod {per_pod}")
    print(f"  admission cutoff {out['hard_stop_et']} (hard), admissions stop "
          f"{__import__('datetime').datetime.fromtimestamp(cutoff).astimezone().isoformat()}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
