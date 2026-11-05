#!/usr/bin/env python3
"""Fail-closed regression tests for the R3 screen adapters (builder + verifier)."""
import csv
import hashlib
import json
import pathlib
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
BUILD = ROOT / 'scripts/c3_r3_build_screen_20261025.py'
VERIFY = ROOT / 'scripts/c3_r3_verify_20261025.py'
TARGET = next(csv.DictReader(
    open(ROOT / 'results/c3_round2_111_20261025/screen_input_24.csv')))['target']
SEQ = ('EELKKRREELKKRREELKKRREELKKRREELKKRREELKKRREELKKRREELKKRRE'
       'EELKKRREELKKRREELKKRREELKKRREELKKRREELKKRREELKKRREELKKRRE')


def sha(s):
    return hashlib.sha256(s.encode()).hexdigest()


def write_fixture(tmp, *, hash_mismatch=False, ineligible=False, duplicate=False):
    tmp = pathlib.Path(tmp)
    rows = []
    for i in (1, 2):
        name = f'p1_H8_52_64_91000{i}_s1'
        rows.append({'name': name, 'sample': 1, 'backbone': f'p1_H8_52_64_91000{i}',
                     'sequence_sha256': sha(SEQ), 'eligible': True,
                     'pod': 'p1', 'arm': 'H8', 'bin': '52_64', 'seed': 910000 + i})
    if hash_mismatch:
        rows[0]['sequence_sha256'] = '0' * 64
    if ineligible:
        rows[0]['eligible'] = False
    if duplicate:
        rows[1]['name'] = rows[0]['name']
    queue = {'n_designs': 2, 'n_eligible': 2, 'queues': {'p1': rows}}
    (tmp / 'queue.json').write_text(json.dumps(queue))
    with (tmp / 'seqs.csv').open('w', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=['name', 'sequence'])
        w.writeheader()
        for r in rows:
            w.writerow({'name': r['name'], 'sequence': SEQ})
    pods = tmp / 'pods.txt'
    pods.write_text('p1 127.0.0.1 22\n')
    return queue


def build(tmp):
    tmp = pathlib.Path(tmp)
    return subprocess.run(
        [sys.executable, str(BUILD), '--queue', str(tmp / 'queue.json'),
         '--seqs', str(tmp / 'seqs.csv'), '--out', str(tmp / 'screen_input.csv'),
         '--pod-dir', str(tmp / 'pods')], capture_output=True, text=True)


def verify_fixture(tmp, mutate=None):
    tmp = pathlib.Path(tmp)
    r3 = tmp / 'r3'
    r3.mkdir(exist_ok=True)
    rows = [{'name': f'p1_H8_52_64_91000{i}_s1', 'binder': SEQ,
             'target': TARGET, 'source': 'r3'} for i in (1, 2)]
    if mutate == 'dup':
        rows[1]['name'] = rows[0]['name']
    if mutate == 'source':
        rows[0]['source'] = 'r2_111'
    if mutate == 'target':
        rows[0]['target'] = TARGET[:-1] + 'A'
    with (r3 / 'screen_input_20261025.csv').open('w', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=['name', 'binder', 'target', 'source'])
        w.writeheader(); w.writerows(rows)
    names = sorted({r['name'] for r in rows})
    qrows = [{'name': n, 'sample': 1, 'backbone': n.rsplit('_s', 1)[0],
              'pod': 'p1', 'arm': 'H8', 'bin': '52_64', 'seed': 910001,
              'eligible': True, 'sequence_sha256': sha(SEQ)} for n in names]
    (r3 / 'queue_20261025.json').write_text(json.dumps({'queues': {'p1': qrows}}))
    digest = hashlib.sha256((r3 / 'screen_input_20261025.csv').read_bytes()).hexdigest()
    (r3 / 'screen_input_manifest_20261025.json').write_text(json.dumps({'input_sha256': digest}))
    return subprocess.run([sys.executable, str(VERIFY), '--r3-dir', str(r3),
                           '--json', str(r3 / 'out.json')], capture_output=True, text=True)


def case(name, cond):
    print(('PASS ' if cond else 'FAIL ') + name)
    assert cond, name


def main():
    with tempfile.TemporaryDirectory() as d:
        write_fixture(d)
        out = build(d)
        case('builder emits a deterministic two-row CSV', out.returncode == 0)
        rows = list(csv.DictReader(open(pathlib.Path(d) / 'screen_input.csv')))
        case('builder preserves order and source', [r['name'] for r in rows] ==
             ['p1_H8_52_64_910001_s1', 'p1_H8_52_64_910002_s1']
             and {r['source'] for r in rows} == {'r3'})
        case('builder target is the frozen 111-mer', rows[0]['target'] == TARGET)
    for key in ('hash_mismatch', 'ineligible', 'duplicate'):
        with tempfile.TemporaryDirectory() as d:
            write_fixture(d, **{key: True})
            out = build(d)
            case(f'builder rejects {key}', out.returncode == 4)
    with tempfile.TemporaryDirectory() as d:
        out = verify_fixture(d)
        case('verifier accepts frozen cohort shape', out.returncode == 0)
        report = json.loads((pathlib.Path(d) / 'r3/out.json').read_text())
        case('missing artifacts are INCOMPLETE, not PASS',
             report['n_complete'] == 0 and report['n_pass'] == 0
             and report['n_incomplete'] == 2)
    for key in ('dup', 'source', 'target'):
        with tempfile.TemporaryDirectory() as d:
            out = verify_fixture(d, mutate=key)
            case(f'verifier rejects cohort mutation {key}', out.returncode == 4)
    print('R3 screen adapter tests PASS')


if __name__ == '__main__':
    main()
