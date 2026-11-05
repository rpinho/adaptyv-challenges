#!/usr/bin/env python3
"""Driver counting must count DRIVERS, not processes.

A healthy wrapper+python pod is 1. Counting processes made p1/p3 report 2 and
would have hidden a genuine duplicate (2 drivers) behind the same number.
"""
import importlib.util
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    'dc', ROOT / 'scripts/c3_r3_driver_count_pod.py')
dc = importlib.util.module_from_spec(spec)
spec.loader.exec_module(dc)


def proc(args, ppid=1):
    return {'args': args, 'ppid': ppid}


WRAP = ['bash', '/workspace/r3_pod_run_par.sh', '/workspace/r3_screen/input.csv',
        'ALL', '/workspace/r3_screen/out', '2']
PY = ['python3', '/workspace/pod_run_par.py', '/workspace/r3_screen/input.csv',
      '/workspace/r3_screen/out', '2']
SER_WRAP = ['bash', '/workspace/r3_pod_run.sh', '/workspace/r3_screen/input.csv',
            'ALL', '/workspace/r3_screen/out']
SER_PY = ['python3', '/workspace/r3_screen/c3_r3_pod_run.py',
          '/workspace/r3_screen/input.csv', 'ALL', '/workspace/r3_screen/out']
FOLD = ['/workspace/af2m/venv/bin/python3.10', '/workspace/af2m/venv/bin/colabfold_batch',
        '/tmp/a/a.fasta', '/tmp/a/out']
SIBLING = ['bash', '/workspace/pod_run.sh', '/workspace/lmp_screen_p1.csv', 'ALL',
           '/workspace/lmp_out']


class Counting(unittest.TestCase):
    def test_wrapper_plus_python_is_one(self):
        self.assertEqual(dc.drivers({10: proc(WRAP), 11: proc(PY, ppid=10)}), 1)

    def test_serial_wrapper_plus_python_is_one(self):
        self.assertEqual(dc.drivers({10: proc(SER_WRAP), 11: proc(SER_PY, ppid=10)}), 1)

    def test_bare_python_is_one(self):
        self.assertEqual(dc.drivers({11: proc(PY, ppid=1)}), 1)

    def test_two_real_drivers_is_two(self):
        self.assertEqual(dc.drivers({11: proc(PY, ppid=1), 12: proc(PY, ppid=1)}), 2)

    def test_two_wrappers_is_two(self):
        self.assertEqual(dc.drivers({10: proc(WRAP), 20: proc(WRAP)}), 2)

    def test_folds_are_not_drivers(self):
        self.assertEqual(dc.drivers({10: proc(WRAP), 11: proc(PY, ppid=10),
                                     12: proc(FOLD, ppid=11), 13: proc(FOLD, ppid=11)}), 1)

    def test_sibling_lane_is_not_counted(self):
        self.assertEqual(dc.drivers({30: proc(SIBLING)}), 0)

    def test_empty_pod_is_zero(self):
        self.assertEqual(dc.drivers({}), 0)


if __name__ == '__main__':
    unittest.main(verbosity=2)
