#!/usr/bin/env python3
"""Independent R3 screen verifier, sealed to the frozen R3 screen input.

Recomputes every gate from raw pod artifacts with the same functions used by
rounds 1-2 and E3. It refuses to run if the input file is not the one recorded
in the manifest, if its cohort differs from the frozen queue, or if the target
is not the exact 111-mer. Missing artifacts are explicit `incomplete` records,
never passes and never omissions.

Usage:
  python3 scripts/c3_r3_verify_20261025.py [--json OUT]
"""
import argparse
import csv
import hashlib
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import c3_round2_verify_20261025 as V  # noqa: E402

R3 = ROOT / 'results/c3_r3_20261025'
INPUT = R3 / 'screen_input_20261025.csv'
MANIFEST = R3 / 'screen_input_manifest_20261025.json'
REFOLD = R3 / 'refold_checks_20261025.json'
QUEUE = R3 / 'queue_20261025.json'
GROOVE = ROOT / 'results/c3_groove_reference_20261025.json'
OUT = R3 / 'screen_verify_20261025.json'
TARGET_SHA = '5c2bae2dac5e467bf4e802473450a7ca3729990921bbe5c45cf6025531ef36b3'


def sha_bytes(b):
    return hashlib.sha256(b).hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--json', default=str(OUT))
    ap.add_argument('--r3-dir', default=str(R3), help='R3 directory (tests use a fixture)')
    a = ap.parse_args()
    r3 = pathlib.Path(a.r3_dir)
    inp = r3 / 'screen_input_20261025.csv'
    manifest_path = r3 / 'screen_input_manifest_20261025.json'
    refold_path = r3 / 'refold_checks_20261025.json'
    queue_path = r3 / 'queue_20261025.json'

    if not inp.exists() or not manifest_path.exists() or not queue_path.exists():
        print('COHORT FAIL missing frozen R3 input/manifest/queue', file=sys.stderr)
        return 4
    manifest = json.loads(manifest_path.read_text())
    queue = json.loads(queue_path.read_text())
    actual_sha = sha_bytes(inp.read_bytes())
    if manifest.get('input_sha256') != actual_sha:
        print('COHORT FAIL input sha differs from manifest', file=sys.stderr)
        return 4
    rows = list(csv.DictReader(open(inp)))
    names = [r['name'] for r in rows]
    queue_names = {r['name'] for q in queue.get('queues', {}).values() for r in q}
    if len(names) != len(set(names)):
        print('COHORT FAIL duplicate names in input', file=sys.stderr)
        return 4
    if set(names) != queue_names:
        print('COHORT FAIL input != frozen queue cohort', file=sys.stderr)
        return 4
    targets = {r['target'].strip() for r in rows}
    if len(targets) != 1 or len(next(iter(targets))) != 111 or \
            sha_bytes(next(iter(targets)).encode()) != TARGET_SHA:
        print('COHORT FAIL target is not the frozen 111-mer', file=sys.stderr)
        return 4
    if {r['source'] for r in rows} != {'r3'}:
        print('COHORT FAIL non-R3 source in R3 input', file=sys.stderr)
        return 4
    # A design may be scored on only one pod; duplicate artifacts are an
    # evidence conflict, not an opportunity to pick the friendlier score.
    base = r3 / 'screen'
    locations = {}
    if base.exists():
        for p in sorted(base.rglob('scores.json')):
            locations.setdefault(p.parent.name, []).append(p.parent)
    conflicts = sorted(n for n, v in locations.items() if len(v) > 1)

    refold = json.loads(refold_path.read_text()) if refold_path.exists() else {}
    groove = set(json.loads(GROOVE.read_text())['groove_residues_1based'])
    records = []
    for row in rows:
        name = row['name']
        hits = locations.get(name, [])
        if len(hits) > 1:
            records.append({'name': name, 'status': 'bad_evidence',
                            'reasons': [f'{len(hits)} duplicate scored artifacts'],
                            'artifact_dirs': [str(x) for x in hits]})
            continue
        d = hits[0] if hits else base / name
        records.append(V.verify_one(name, row['binder'].strip(), row['target'].strip(), d,
                                    refold.get(name), groove, allowed_sources=('r3',)))

    complete = [r for r in records if r['status'] != 'incomplete']
    bad = [r for r in records if r['status'] == 'bad_evidence']
    passed = [r for r in records if r['status'] == 'PASS']
    out = {
        'cohort_sha256': actual_sha,
        'queue_sha256': manifest.get('queue_sha256'),
        'n_expected': len(rows),
        'n_complete': len(complete),
        'n_incomplete': len(records) - len(complete),
        'n_bad_evidence': len(bad),
        'n_pass': len(passed),
        'duplicate_artifacts': conflicts,
        'thresholds': {
            'iptm_floor': V.FLOOR, 'refold_mean_plddt': 80.0,
            'refold_frac70': 0.90, 'refold_rmsd_max': 3.0,
            'binder_plddt_min': V.BINDER_PLDDT_MIN,
            'groove_min': V.MIN_GROOVE, 'contacts_min': V.MIN_CONTACTS,
            'clash_a': V.CLASH_A,
        },
        'records': records,
        'note': ('independent recomputation from raw artifacts; no submission '
                 'written; incomplete is not a failure and not eligible'),
    }
    pathlib.Path(a.json).write_text(json.dumps(out, indent=1) + '\n')
    print(f'R3 verify: {len(complete)}/{len(records)} complete, '
          f'{len(passed)} PASS, {len(records) - len(complete)} incomplete')
    for r in sorted(records, key=lambda x: (x['status'] != 'PASS', x['name'])):
        if r['status'] == 'PASS':
            continue
        print(f"  {r['status'].upper():<13s} {r['name']}: "
              f"{'; '.join(r.get('reasons', []))[:150]}")
    print(f'wrote {a.json}')
    return 0 if not bad and not conflicts else 4


if __name__ == '__main__':
    sys.exit(main())
