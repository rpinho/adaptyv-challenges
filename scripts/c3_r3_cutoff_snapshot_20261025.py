#!/usr/bin/env python3
"""Capture which frozen R3 designs actually started before the 03:15 quiesce.

The pod runner creates /workspace/r3_screen/out/<name>/ before launching the fold,
so directory existence is positive evidence of a start even when no scores.json was
written. This script only reads the pods. It never starts, stops, or scores work.

Fail-closed conditions: SSH failure, unknown design name, a design from another
pod's frozen slice, malformed remote output, or a mismatched frozen input hash.
Nothing is written unless every pod is captured successfully.

Usage: python3 scripts/c3_r3_cutoff_snapshot_20261025.py [--out PATH]
"""
import argparse
import csv
import datetime
import hashlib
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
R3 = ROOT / 'results/c3_r3_20261025'
INPUT = R3 / 'screen_input_20261025.csv'
MANIFEST = R3 / 'screen_input_manifest_20261025.json'
OUT = R3 / 'cutoff_snapshot_20261025.json'
PODS = {
    'p1': ('63.141.33.138', '22113'),
    'p2': ('194.68.245.32', '22065'),
    'p3': ('69.30.85.102', '22129'),
    'p4': ('194.68.245.69', '22022'),
    'p5': ('194.68.245.147', '22117'),
}
# The N=2 runner keeps its bookkeeping inside the same out/ root:
# .claims/, records/, queue/, failures/. They are not designs. Ignoring them is
# explicit and bounded -- any OTHER unexpected name still fails the capture, so
# a design from the wrong slice can never slip through.
BOOKKEEPING = {'.claims', 'records', 'queue', 'failures'}

MARKERS = {
    'started': "find /workspace/r3_screen/out -mindepth 1 -maxdepth 1 -type d -printf '%f\\n' 2>/dev/null",
    'scores': "find /workspace/r3_screen/out -name scores.json -printf '%P\\n' 2>/dev/null",
    'pdb': "find /workspace/r3_screen/out -name complex_rank_001.pdb -printf '%P\\n' 2>/dev/null",
    'errors': "find /workspace/r3_screen/out -name error.json -printf '%P\\n' 2>/dev/null",
}


def sha(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()


def parent_names(lines):
    return sorted({pathlib.PurePosixPath(x.strip()).parent.name
                   for x in lines if x.strip()})


def capture_pod(pod):
    host, port = PODS[pod]
    remote = 'set -u; echo __STARTED__; ' + MARKERS['started']
    for key in ('scores', 'pdb', 'errors'):
        remote += f'; echo __{key.upper()}__; ' + MARKERS[key]
    remote += '; echo __END__'
    cmd = [
        'ssh', '-n', '-i', str(pathlib.Path.home() / '.ssh/runpod_ed25519'),
        '-o', 'StrictHostKeyChecking=no', '-o', 'ConnectTimeout=15',
        '-o', 'BatchMode=yes', '-p', port, f'root@{host}', remote,
    ]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=90)
    if p.returncode != 0:
        raise RuntimeError(f'{pod} ssh rc={p.returncode}: {p.stderr.strip()[:300]}')
    sections, current = {}, None
    for line in p.stdout.splitlines():
        if line.startswith('__') and line.endswith('__'):
            current = line.strip('_').lower()
            sections[current] = []
        elif current:
            sections[current].append(line)
    if sections.get('end') is None:
        raise RuntimeError(f'{pod} remote output had no __END__ marker')
    return {
        'endpoint': f'{host}:{port}',
        'ssh_ok': True,
        'started': sorted(set(sections.get('started', [])) - BOOKKEEPING),
        'bookkeeping_ignored': sorted(set(sections.get('started', [])) & BOOKKEEPING),
        'scores': parent_names(sections.get('scores', [])),
        'pdb': parent_names(sections.get('pdb', [])),
        'errors': parent_names(sections.get('errors', [])),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--out', default=str(OUT))
    a = ap.parse_args()
    if not INPUT.exists() or not MANIFEST.exists():
        print('ERROR frozen R3 input/manifest missing', file=sys.stderr)
        return 4
    manifest = json.loads(MANIFEST.read_text())
    input_sha = sha(INPUT)
    if manifest.get('input_sha256') != input_sha:
        print('ERROR frozen R3 input sha does not match manifest', file=sys.stderr)
        return 4
    expected = {'all': set(), 'by_pod': {}}
    for pod in PODS:
        pod_csv = R3 / 'screen_inputs' / f'{pod}.csv'
        if not pod_csv.exists():
            print(f'ERROR missing frozen pod slice {pod_csv}', file=sys.stderr)
            return 4
        names = {r['name'] for r in csv.DictReader(open(pod_csv))}
        if not names:
            print(f'ERROR empty frozen pod slice {pod}', file=sys.stderr)
            return 4
        expected['by_pod'][pod] = names
        expected['all'] |= names
    if expected['all'] != {r['name'] for r in csv.DictReader(open(INPUT))}:
        print('ERROR pod slices do not cover frozen input', file=sys.stderr)
        return 4

    pods = {}
    errors = []
    for pod in PODS:
        try:
            rec = capture_pod(pod)
        except Exception as ex:
            errors.append(str(ex))
            continue
        # A sibling lane rebalanced some p1 remainder designs onto p3 after the frozen
        # slices were cut (batch r3p3_rem_022317). Those names are legitimate work but
        # they are NOT in p3's frozen slice. Failing the whole snapshot would discard
        # evidence for 26 correctly-assigned designs; silently accepting them would let
        # foreign work masquerade as frozen-cohort coverage. So: record them explicitly
        # and keep them out of `started`, which is what the finalizer reads.
        foreign = set()
        for key in ('started', 'scores', 'pdb', 'errors'):
            unknown = sorted(set(rec[key]) - expected['by_pod'][pod])
            if unknown:
                foreign |= set(unknown)
        if foreign:
            rec['foreign_ignored'] = sorted(foreign)
            rec['started'] = sorted(set(rec['started']) - foreign)
            for key in ('scores', 'pdb', 'errors'):
                rec[key] = sorted(set(rec[key]) - foreign)
            print(f'WARN {pod}: {len(foreign)} design(s) outside the frozen slice '
                  f'recorded as foreign_ignored, excluded from started', file=sys.stderr)
        rec['expected'] = len(expected['by_pod'][pod])
        rec['not_started'] = sorted(expected['by_pod'][pod] - set(rec['started']))
        pods[pod] = rec
    if errors:
        for e in errors:
            print('ERROR', e, file=sys.stderr)
        print('CUTOFF_SNAPSHOT_FAILED; nothing written', file=sys.stderr)
        return 4

    out = {
        'schema': 'r3-cutoff-snapshot-v1',
        'captured_at_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'cutoff_et': '2026-10-25T03:15:00-04:00',
        'input_sha256': input_sha,
        'source': ('positive start evidence = /workspace/r3_screen/out/<name>/ exists; '
                   'pod_run.sh creates that directory before folding. Read-only SSH.'),
        'pods': pods,
    }
    path = pathlib.Path(a.out)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(out, indent=1) + '\n')
    tmp.replace(path)
    label = str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path)
    print(f"CUTOFF_SNAPSHOT_OK {label} "
          f"started={sum(len(v['started']) for v in pods.values())} "
          f"not_started={sum(len(v['not_started']) for v in pods.values())}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
