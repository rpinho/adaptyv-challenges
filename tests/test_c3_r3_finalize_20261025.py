#!/usr/bin/env python3
"""Fixture tests for R3 cutoff/status semantics. No pods and no real results touched."""
import contextlib
import csv
import hashlib
import importlib.util
import io
import json
import pathlib
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    'fin', ROOT / 'scripts/c3_r3_finalize_20261025.py')
fin = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(fin)

TARGET = 'A' * 111


def sha_bytes(b):
    return hashlib.sha256(b).hexdigest()


class FinalizeFixture:
    def __init__(self, *, started=None, missing_snapshot=False, overlap=False,
                 structural='records', verify_status=None):
        self.tmp = tempfile.TemporaryDirectory()
        self.r3 = pathlib.Path(self.tmp.name) / 'r3'
        self.r3.mkdir()
        self.names = ['p1_A_s1', 'p1_A_s2']
        rows = [{'name': n, 'binder': 'EELKKRREELKK' * 4 + 'EE',
                 'target': TARGET, 'source': 'r3'} for n in self.names]
        with (self.r3 / 'screen_input_20261025.csv').open('w', newline='') as fh:
            w = csv.DictWriter(fh, fieldnames=['name', 'binder', 'target', 'source'])
            w.writeheader(); w.writerows(rows)
        input_sha = sha_bytes((self.r3 / 'screen_input_20261025.csv').read_bytes())
        (self.r3 / 'screen_input_manifest_20261025.json').write_text(json.dumps({
            'input_sha256': input_sha, 'n_designs': len(rows)}))
        queue_rows = [{'name': n, 'pod': 'p1', 'arm': 'H8', 'bin': '52_64',
                       'seed': 910000 + i} for i, n in enumerate(self.names)]
        (self.r3 / 'queue_20261025.json').write_text(json.dumps({
            'queues': {'p1': queue_rows},
            'not_queued': [{'name': 'p1_A_s3', 'pod': 'p1', 'arm': 'H8',
                            'bin': '52_64', 'seed': 910002,
                            'reasons': ['refold_fail']}],
        }))
        (self.r3 / 'refold_checks_20261025.json').write_text('{}')
        status = verify_status or {n: 'incomplete' for n in self.names}
        recs = []
        for n in self.names:
            s = status[n]
            rec = {'name': n, 'status': s,
                   'reasons': ['scores.json or complex_rank_001.pdb absent']
                   if s == 'incomplete' else ['duplicate']}
            if s == 'PASS':
                rec.update(iptm=0.9, reasons=[])
            recs.append(rec)
        self.verify = pathlib.Path(self.tmp.name) / 'verify.json'
        self.verify.write_text(json.dumps({
            'cohort_sha256': input_sha, 'records': recs}))
        if not missing_snapshot:
            started = set(started or [])
            not_started = set(self.names) - started
            if overlap:
                not_started = set(self.names)
            (self.r3 / 'cutoff_snapshot_20261025.json').write_text(json.dumps({
                'input_sha256': input_sha,
                'pods': {'p1': {'started': sorted(started),
                                'not_started': sorted(not_started)}}}))
        if structural == 'records':
            (self.r3 / 'structural_checks_20261025.json').write_text('{}')
        elif structural == 'absent':
            pass
        self.outs = {
            'STATUS_OUT': self.r3 / 'status.json',
            'SUMMARY_OUT': self.r3 / 'summary.md',
            'SUMS_OUT': self.r3 / 'SHA256SUMS',
        }
        self._saved = None

    def run(self):
        self._saved = (fin.R3, fin.STATUS_OUT, fin.SUMMARY_OUT, fin.SUMS_OUT)
        fin.R3, fin.STATUS_OUT, fin.SUMMARY_OUT, fin.SUMS_OUT = (
            self.r3, self.outs['STATUS_OUT'], self.outs['SUMMARY_OUT'], self.outs['SUMS_OUT'])
        argv = ['finalize', '--verify', str(self.verify)]
        if (self.r3 / 'cutoff_snapshot_20261025.json').exists():
            argv += ['--cutoff-snapshot', str(self.r3 / 'cutoff_snapshot_20261025.json')]
        else:
            argv += ['--cutoff-snapshot', str(self.r3 / 'missing_snapshot.json')]
        if not (self.r3 / 'structural_checks_20261025.json').exists():
            argv += ['--structural', str(self.r3 / 'missing_structural.json')]
        old = sys.argv
        sys.argv = argv
        out = io.StringIO()
        try:
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
                rc = fin.main()
        finally:
            sys.argv = old
            (fin.R3, fin.STATUS_OUT, fin.SUMMARY_OUT, fin.SUMS_OUT) = self._saved
        status = None
        if self.outs['STATUS_OUT'].exists():
            status = json.loads(self.outs['STATUS_OUT'].read_text())
        return rc, status, out.getvalue()

    def close(self):
        self.tmp.cleanup()


class CutoffStatus(unittest.TestCase):
    def test_started_is_incomplete_and_never_started_is_time_cutoff(self):
        f = FinalizeFixture(started=['p1_A_s1'])
        try:
            rc, s, out = f.run()
        finally:
            f.close()
        self.assertEqual(rc, 0, out)
        by = {d['name']: d for d in s['designs']}
        self.assertEqual(by['p1_A_s1']['status'], 'INCOMPLETE')
        self.assertEqual(by['p1_A_s2']['status'], 'NOT_SCREENED')
        self.assertEqual(by['p1_A_s2']['reasons'], ['TIME_CUTOFF'])
        self.assertEqual(by['p1_A_s3']['status'], 'NOT_SCREENED')
        self.assertEqual(s['n_not_screened_time_cutoff'], 1)
        self.assertEqual(s['pods']['p1']['INCOMPLETE'], 1)
        self.assertEqual(s['pods']['p1']['NOT_SCREENED'], 1)

    def test_missing_snapshot_fails_closed(self):
        f = FinalizeFixture(missing_snapshot=True)
        try:
            rc, s, out = f.run()
        finally:
            f.close()
        self.assertEqual(rc, 4)
        self.assertIn('cutoff snapshot missing', out)
        self.assertIsNone(s)

    def test_overlapping_snapshot_fails_closed(self):
        f = FinalizeFixture(started=['p1_A_s1'], overlap=True)
        try:
            rc, s, out = f.run()
        finally:
            f.close()
        self.assertEqual(rc, 4)
        self.assertIn('overlap', out)
        self.assertIsNone(s)

    def test_pass_cannot_bypass_missing_structural_evidence(self):
        f = FinalizeFixture(started=['p1_A_s1'], structural='absent',
                            verify_status={'p1_A_s1': 'PASS', 'p1_A_s2': 'incomplete'})
        try:
            rc, s, out = f.run()
        finally:
            f.close()
        self.assertEqual(rc, 0, out)
        by = {d['name']: d for d in s['designs']}
        self.assertEqual(by['p1_A_s1']['status'], 'INCOMPLETE')
        self.assertEqual(by['p1_A_s1']['reasons'], ['structural evidence file missing'])

    def test_bad_evidence_is_not_eligible_or_a_pass(self):
        f = FinalizeFixture(verify_status={'p1_A_s1': 'bad_evidence',
                                           'p1_A_s2': 'incomplete'})
        try:
            rc, s, out = f.run()
        finally:
            f.close()
        self.assertEqual(rc, 4, out)
        by = {d['name']: d for d in s['designs']}
        self.assertEqual(by['p1_A_s1']['status'], 'BAD_EVIDENCE')


if __name__ == '__main__':
    unittest.main(verbosity=2)
