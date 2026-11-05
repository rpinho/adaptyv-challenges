#!/usr/bin/env python3
"""Behavioural tests for the N-capable R3 runner (pod_run_par).

Runs the real script as a subprocess against a fake colabfold_batch, so the
tests exercise the same code path the pods use. Each test targets a defect
that was found in review: batch-scoped claims (double folding), missing
terminal-error handling, no cutoff, and incomplete provenance.
"""
import csv
import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
RUNNER = ROOT / 'scripts' / 'pod_run_par_20261025.py'
CUTOFF = 1792911600

FAKE = r'''#!/usr/bin/env python3
import json, os, pathlib, sys
fa, out = pathlib.Path(sys.argv[1]), pathlib.Path(sys.argv[2])
name = fa.read_text().splitlines()[0][1:]
out.mkdir(parents=True, exist_ok=True)
mode = os.environ.get('FAKE_MODE', 'ok')
if mode == 'fail':
    sys.stderr.write('simulated colabfold failure\n')
    sys.exit(1)
pl = [90.0] * 60
for m in range(1, 6):
    (out / f'{name}_scores_rank_00{m}_alphafold2_multimer_v3_model_{m}_v2.json').write_text(
        json.dumps({'iptm': 0.9, 'ptm': 0.88, 'plddt': pl}))
    (out / f'{name}_rank_00{m}_alphafold2_multimer_v3_model_{m}_v2.pdb').write_text('ATOM\n')
(out / f'{name}_scores_rank_001_alphafold2_multimer_v3_model_1_v2.json').write_text(
    json.dumps({'iptm': 0.9, 'ptm': 0.88, 'plddt': pl}))
'''


def make_bin(tmp):
    b = pathlib.Path(tmp) / 'bin'
    b.mkdir(exist_ok=True)
    f = b / 'colabfold_batch'
    f.write_text(FAKE)
    f.chmod(0o755)
    return b


def make_input(tmp, names):
    p = pathlib.Path(tmp) / 'input.csv'
    with open(p, 'w', newline='') as fh:
        w = csv.writer(fh)
        w.writerow(['name', 'binder', 'target', 'source', 'pass_no'])
        for n in names:
            w.writerow([n, 'ACDEFGHIKL', 'MNPQRSTVWY', 'r3', 1])
    return p


def run(tmp, csv_path, out, cap=1, env_extra=None, extra=()):
    env = dict(os.environ)
    env['PATH'] = f"{make_bin(tmp)}:{env['PATH']}"
    # These are behavioural tests, not a clock test. Without a deterministic
    # future cutoff they start failing by design once the real 03:00 deadline
    # passes (admission correctly closes), which hides real regressions.
    env['R3_CUTOFF_EPOCH'] = '9999999999'
    env.update(env_extra or {})
    return subprocess.run([sys.executable, str(RUNNER), str(csv_path), str(out), str(cap),
                           *extra], capture_output=True, text=True, env=env, timeout=120)


class ParallelRunner(unittest.TestCase):
    def test_design_only_claim_prevents_double_fold_across_batches(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = pathlib.Path(tmp) / 'out'
            csv_path = make_input(tmp, ['d1'])
            r1 = run(tmp, csv_path, out, env_extra={'R3_BATCH_ID': 'batchA'})
            self.assertEqual(r1.returncode, 0, r1.stderr)
            r2 = run(tmp, csv_path, out, env_extra={'R3_BATCH_ID': 'batchB'})
            self.assertEqual(r2.returncode, 0, r2.stderr)
            recs = sorted((out / 'records').glob('*-d1-slot*.json'))
            self.assertEqual(len(recs), 1, [p.name for p in recs])
            self.assertIn('running', r2.stdout)
            self.assertNotIn('iptm=', r2.stdout)

    def test_claim_key_is_design_only(self):
        sys.path.insert(0, str(ROOT / 'scripts'))
        import pod_run_par_20261025 as M
        self.assertEqual(M.claim_key('x'), M.claim_key('x'))
        self.assertNotEqual(M.claim_key('x'), M.claim_key('y'))

    def test_terminal_error_is_never_retried(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = pathlib.Path(tmp) / 'out'
            od = out / 'd1'
            od.mkdir(parents=True)
            (od / 'error.json').write_text(json.dumps({'error': 'timeout'}))
            csv_path = make_input(tmp, ['d1'])
            r = run(tmp, csv_path, out)
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertFalse((out / 'records').joinpath('d1-slot0.json').exists())
            self.assertEqual(list((out / 'records').glob('*-d1-slot0.json')), [])

    def test_cutoff_blocks_admission(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = pathlib.Path(tmp) / 'out'
            csv_path = make_input(tmp, ['d1', 'd2'])
            r = run(tmp, csv_path, out, env_extra={'R3_CUTOFF_EPOCH': '1'})
            self.assertEqual(r.returncode, 0, r.stderr)
            self.assertIn('CUTOFF_NO_NEW_ADMISSION', r.stdout)
            self.assertEqual(list((out / 'records').glob('*-slot0.json')), [])

    def test_admit_boundary(self):
        sys.path.insert(0, str(ROOT / 'scripts'))
        import pod_run_par_20261025 as M
        self.assertTrue(M.admit(CUTOFF - 1))
        self.assertFalse(M.admit(CUTOFF))
        self.assertEqual(M.CUTOFF_ET, CUTOFF)

    def test_provenance_fields_present(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = pathlib.Path(tmp) / 'out'
            csv_path = make_input(tmp, ['d1'])
            r = run(tmp, csv_path, out, cap=2, env_extra={'R3_BATCH_ID': 'bX',
                                                          'R3_RUN_MODE': 'screen'})
            self.assertEqual(r.returncode, 0, r.stderr)
            rec = json.loads(next((out / 'records').glob('bX-d1-slot*.json')).read_text())
            for field in ('design_id', 'attempt_id', 'batch_id', 'pod_id', 'worker_id',
                          'run_mode', 'configured_concurrency',
                          'observed_concurrency_peak', 'queue_index', 'pass_no',
                          'input_sha256', 'settings_sha256', 'input_fasta_sha256',
                          'validation_reference', 'started_epoch', 'ended_epoch',
                          'wall_s', 'rc', 'status', 'artifacts', 'models_complete'):
                self.assertIn(field, rec)
            self.assertEqual(rec['status'], 'COMPLETE')
            self.assertTrue(rec['models_complete'])
            self.assertEqual(rec['design_id'], 'd1')
            self.assertIn('scores.json', rec['artifacts'])

    def test_batch_record_has_concurrency_and_hashes(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = pathlib.Path(tmp) / 'out'
            csv_path = make_input(tmp, ['d1'])
            r = run(tmp, csv_path, out, cap=2, env_extra={'R3_BATCH_ID': 'bY'})
            self.assertEqual(r.returncode, 0, r.stderr)
            batch = json.loads((out / 'records' / 'batch_bY.json').read_text())
            self.assertEqual(batch['configured_concurrency'], 2)
            self.assertEqual(batch['input_sha256'], batch['cohort_sha256'])
            self.assertIn('settings_sha256', batch)
            self.assertEqual(batch['designs'], ['d1'])

    def test_failure_is_recorded_terminal_and_not_retried(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = pathlib.Path(tmp) / 'out'
            csv_path = make_input(tmp, ['d1'])
            r1 = run(tmp, csv_path, out, env_extra={'R3_BATCH_ID': 'f1', 'FAKE_MODE': 'fail'})
            self.assertEqual(r1.returncode, 0, r1.stderr)
            self.assertTrue((out / 'd1' / 'error.json').exists())
            self.assertTrue((out / 'failures' / 'd1.json').exists())
            f = json.loads((out / 'failures' / 'd1.json').read_text())
            self.assertTrue(f['terminal'])
            self.assertEqual(len(f['attempts']), 1)
            r2 = run(tmp, csv_path, out, env_extra={'R3_BATCH_ID': 'f2'})
            self.assertEqual(r2.returncode, 0, r2.stderr)
            f2 = json.loads((out / 'failures' / 'd1.json').read_text())
            self.assertEqual(len(f2['attempts']), 1, 'terminal error was retried')

    def test_dry_run_writes_nothing_and_reports_cutoff(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = pathlib.Path(tmp) / 'out'
            csv_path = make_input(tmp, ['d1'])
            r = run(tmp, csv_path, out, extra=('--dry-run',))
            self.assertEqual(r.returncode, 0, r.stderr)
            d = json.loads(r.stdout)
            self.assertTrue(d['admitted_now'])
            self.assertFalse(out.exists())


if __name__ == '__main__':
    unittest.main(verbosity=2)
