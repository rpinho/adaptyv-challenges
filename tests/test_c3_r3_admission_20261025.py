#!/usr/bin/env python3
"""Cutoff and process-identification tests for the R3-only pod runner/freezer."""
import importlib.util
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


runner = load('runner', ROOT / 'scripts/c3_r3_pod_run.py')
freeze = load('freeze', ROOT / 'scripts/c3_r3_admission_freeze_pod.py')


class AdmissionCutoff(unittest.TestCase):
    def test_before_cutoff_admits(self):
        self.assertTrue(runner.admit(runner.CUTOFF_ET - 1))

    def test_exact_cutoff_does_not_admit(self):
        self.assertFalse(runner.admit(runner.CUTOFF_ET))

    def test_after_cutoff_does_not_admit(self):
        self.assertFalse(runner.admit(runner.CUTOFF_ET + 1))

    def test_exact_epoch_is_0300_et(self):
        from datetime import datetime
        from zoneinfo import ZoneInfo
        self.assertEqual(runner.CUTOFF_ET,
                         int(datetime(2026, 10, 25, 3, 0,
                                      tzinfo=ZoneInfo('America/New_York')).timestamp()))


class FreezeIdentification(unittest.TestCase):
    def test_r3_root_matches_and_sibling_does_not(self):
        self.assertTrue(freeze.is_root(
            ['bash', '/workspace/pod_run.sh', '/workspace/r3_screen/input.csv', 'ALL']))
        self.assertTrue(freeze.is_root(
            ['bash', '/workspace/r3_pod_run.sh', '/workspace/r3_screen/input.csv', 'ALL']))
        self.assertFalse(freeze.is_root(
            ['bash', '/workspace/pod_run.sh', '/workspace/lmp_screen_p1.csv', 'ALL']))
        self.assertFalse(freeze.is_root(
            ['sh', '/workspace/pod_run.sh', '/workspace/r3_screen/input.csv']))
        self.assertFalse(freeze.is_root(
            ['bash', '/workspace/r3_pod_run.sh', '/workspace/lmp_screen_p1.csv']))

    def test_colabfold_child_detected_by_interpreter_argument(self):
        table = {
            10: {'args': ['bash', '/workspace/pod_run.sh',
                          '/workspace/r3_screen/input.csv', 'ALL'], 'ppid': 1,
                 'pgid': 10, 'sid': 10},
            11: {'args': ['python3', '-', '/workspace/r3_screen/input.csv', 'ALL',
                          '/workspace/r3_screen/out'], 'ppid': 10, 'pgid': 10, 'sid': 10},
            12: {'args': ['/workspace/af2m/venv/bin/python3.10',
                          '/workspace/af2m/venv/bin/colabfold_batch',
                          '/tmp/p3_H8_s1/p3_H8_s1.fasta', '/tmp/p3_H8_s1/out'],
                 'ppid': 11, 'pgid': 10, 'sid': 10},
        }
        self.assertTrue(freeze.is_python_driver(11, table, 10))
        self.assertEqual(freeze.folds_for(11, table), [(12, 'p3_H8_s1')])

    def test_r3_wrapper_python_driver_detected(self):
        table = {
            10: {'args': ['bash', '/workspace/r3_pod_run.sh',
                          '/workspace/r3_screen/input.csv', 'ALL',
                          '/workspace/r3_screen/out'], 'ppid': 1, 'pgid': 10, 'sid': 10},
            11: {'args': ['python3', '/workspace/r3_screen/c3_r3_pod_run.py',
                          '/workspace/r3_screen/input.csv', 'ALL',
                          '/workspace/r3_screen/out'], 'ppid': 10, 'pgid': 10, 'sid': 10},
        }
        self.assertTrue(freeze.is_root(table[10]['args']))
        self.assertTrue(freeze.is_python_driver(11, table, 10))

    def test_terminal_error_is_not_retried(self):
        import json, tempfile
        with tempfile.TemporaryDirectory() as tmp:
            od = pathlib.Path(tmp) / 'p3_H8_s1'
            od.mkdir()
            (od / 'error.json').write_text(json.dumps({'error': 'timeout'}))
            rows = [{'name': 'p3_H8_s1', 'binder': 'ACDE', 'target': 'FGHI',
                     'source': 'test'}]
            csv_path = pathlib.Path(tmp) / 'input.csv'
            csv_path.write_text('name,binder,target,source\np3_H8_s1,ACDE,FGHI,test\n')
            import io, contextlib
            old_root = runner.CUTOFF_ET
            old_run = runner.subprocess.run
            runner.CUTOFF_ET = 2**31
            runner.subprocess.run = lambda *a, **k: self.fail('must not fold')
            try:
                import sys
                old_argv = sys.argv
                sys.argv = ['c3_r3_pod_run.py', str(csv_path), 'ALL', tmp]
                out = io.StringIO()
                with contextlib.redirect_stdout(out):
                    runner.main()
                self.assertIn('terminal error.json', out.getvalue())
            finally:
                runner.CUTOFF_ET = old_root
                runner.subprocess.run = old_run
                sys.argv = old_argv

    def test_unrelated_children_are_not_folds(self):
        table = {11: {'args': ['python3', '-', '/workspace/r3_screen/input.csv',
                               'ALL', '/workspace/r3_screen/out'], 'ppid': 10,
                      'pgid': 10, 'sid': 10},
                 12: {'args': ['bash', '/workspace/lmp_screen_p1.csv'], 'ppid': 11,
                      'pgid': 10, 'sid': 10}}
        self.assertEqual(freeze.folds_for(11, table), [])


if __name__ == '__main__':
    unittest.main(verbosity=2)
