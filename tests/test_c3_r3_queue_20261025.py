#!/usr/bin/env python3
"""Regression tests for the frozen R3 queue (Astra option D).

These fail closed on the defects found 2026-10-24: a 24-per-pod cap that dropped
pass-2 designs, a bin parser that misread real backbone names, and silent loss of
ineligible designs from the manifest.
"""
import csv
import json
import pathlib
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts/c3_r3_queue_20261025.py'
ALLOC = {
    'p1': [('H8', '52_64', range(910000, 910024))],
    'p2': [('H8', '65_80', range(910100, 910124))],
    'p3': [('H8', '81_100', range(910200, 910224))],
    'p4': [('H8', '52_64', range(910024, 910032)),
           ('H8', '65_80', range(910124, 910132)),
           ('H8', '81_100', range(910224, 910232))],
    'p5': [('H4', '52_64', range(910300, 910308)),
           ('H4', '65_80', range(910400, 910408)),
           ('H4', '81_100', range(910500, 910508))],
}


def backbone(pod, tag, b, seed):
    return f'{pod}_{tag}_{b}_{seed}'


def build(tmp, all_pass=True):
    seqs, refold = [], {}
    for pod, jobs in ALLOC.items():
        for tag, b, seeds in jobs:
            for seed in seeds:
                bb = backbone(pod, tag, b, seed)
                for sample in (1, 2):
                    name = f'{bb}_s{sample}'
                    seq = ('AGSKDELRKQIVEEALKRGADVLTEEQKARLEELKRKGEELAKRIAELEKGG'
                           'LSEEEIRRLKEELERAKELGEEVRRLKEELEKLK')
                    seqs.append({'name': name, 'sequence': seq})
                    refold[name] = {'pass': True if all_pass else sample == 1,
                                    'ca_rmsd_vs_designed_backbone': 0.5,
                                    'refold_mean_plddt': 90.0,
                                    'refold_frac_residues_plddt_ge70': 0.95}
    sp, rp = tmp / 'seqs.csv', tmp / 'refold.json'
    with sp.open('w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=['name', 'sequence']); w.writeheader(); w.writerows(seqs)
    rp.write_text(json.dumps(refold))
    pods = tmp / 'pods.txt'
    pods.write_text(''.join(f'{p} 127.0.0.1 22\n' for p in ALLOC))
    return sp, rp, pods


def run(tmp, sp, rp, pods):
    out = tmp / 'queue.json'
    r = subprocess.run([sys.executable, str(SCRIPT), '--seqs', str(sp), '--refold', str(rp),
                        '--out', str(out), '--pod-file', str(pods)],
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return json.loads(out.read_text())


def main():
    with tempfile.TemporaryDirectory() as d:
        tmp = pathlib.Path(d)
        sp, rp, pods = build(tmp)
        q = run(tmp, sp, rp, pods)
        assert q['n_backbones'] == 120 and q['n_designs'] == 240, q
        assert q['n_eligible'] == 240
        assert q['n_pass1'] == 120 and q['n_pass2'] == 120
        assert not q['not_queued'], q['not_queued'][:3]
        assert sum(len(v) for v in q['queues'].values()) == 240
        for p, rows in q['queues'].items():
            assert len(rows) == 48, (p, len(rows))
            passes = [r['pass_no'] for r in rows]
            assert passes == sorted(passes), (p, passes)
            assert all(r['pod'] == p for r in rows)
        # p4/p5 round-robin their three bins within a pass.
        for p in ('p4', 'p5'):
            p1 = [r['bin'] for r in q['queues'][p] if r['pass_no'] == 1]
            assert p1[:6] == ['52_64', '65_80', '81_100'] * 2, (p, p1)
        # one pass-1 design per backbone, exactly.
        p1_backbones = [r['backbone'] for r in q['queues']['p1'] if r['pass_no'] == 1]
        assert len(p1_backbones) == len(set(p1_backbones)) == 24

    with tempfile.TemporaryDirectory() as d:
        tmp = pathlib.Path(d)
        sp, rp, pods = build(tmp, all_pass=False)
        q = run(tmp, sp, rp, pods)
        assert q['n_eligible'] == 120 and q['n_pass2'] == 0, q
        assert q['excluded_reasons'].get('refold_fail') == 120
        assert all(r['sample'] == 1 for v in q['queues'].values() for r in v)
    print('R3 queue regression tests PASS')


if __name__ == '__main__':
    main()
