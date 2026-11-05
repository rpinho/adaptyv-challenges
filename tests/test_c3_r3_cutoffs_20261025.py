#!/usr/bin/env python3
"""Fail-closed tests for R3's cutoff predicate and pod quiesce helper."""
import importlib.util
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location('q', ROOT / 'scripts/c3_r3_quiesce_pod.py')
q = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(q)


class RootMatch(unittest.TestCase):
    def test_exact_r3_root_matches(self):
        self.assertTrue(q.is_root(
            ['bash', '/workspace/pod_run.sh', '/workspace/r3_screen/input.csv',
             'ALL', '/workspace/r3_screen/out']))
        self.assertTrue(q.is_root(
            ['/bin/bash', '/workspace/pod_run.sh', '/workspace/r3_screen/input.csv']))
        self.assertTrue(q.is_root(
            ['bash', '/workspace/r3_pod_run.sh', '/workspace/r3_screen/input.csv',
             'ALL', '/workspace/r3_screen/out']))

    def test_sibling_lane_never_matches(self):
        for args in (
            ['bash', '/workspace/pod_run.sh', '/workspace/lmp_screen_p1.csv'],
            ['bash', '/workspace/pod_run.sh', '/workspace/e3_screen/input.csv'],
            ['sh', '/workspace/pod_run.sh', '/workspace/r3_screen/input.csv'],
            ['bash', '/workspace/pod_run.sh', '/workspace/r3_screen/input.csv.bak'],
            ['bash', '/workspace/other.sh', '/workspace/r3_screen/input.csv'],
            ['sh', '/workspace/r3_pod_run.sh', '/workspace/r3_screen/input.csv'],
            ['bash', '/workspace/r3_pod_run.sh', '/workspace/lmp_screen_p1.csv'],
        ):
            self.assertFalse(q.is_root(args), args)

    def test_offlinux_is_explicitly_unsupported(self):
        if pathlib.Path('/proc').is_dir():
            self.skipTest('Linux pod')
        self.assertEqual(q.main(), 2)


class SingleRootPerDriver(unittest.TestCase):
    """A wrapper + its python child are ONE driver, not two roots.

    Regression: p1/p3 printed QUIESCE_MULTIPLE_R3_ROOTS because the parallel
    wrapper and its python were both matched. On a real pod that message is a
    warning that could make an operator think two drivers existed.
    """

    def test_parallel_python_under_wrapper_is_not_a_second_root(self):
        self.assertTrue(q.is_root(
            ['bash', '/workspace/r3_pod_run_par.sh', '/workspace/r3_screen/input.csv',
             'ALL', '/workspace/r3_screen/out', '2']))
        self.assertTrue(q.is_par_root(
            ['python3', '/workspace/pod_run_par.py', '/workspace/r3_screen/input.csv',
             '/workspace/r3_screen/out', '2']))

    def test_read_procs_returns_ppid(self):
        if not pathlib.Path('/proc').is_dir():
            self.skipTest('Linux pod only')
        procs = q.read_procs()
        self.assertTrue(procs)
        for pid, rec in list(procs.items())[:20]:
            self.assertIn('ppid', rec)
            self.assertIn('args', rec)


if __name__ == '__main__':
    unittest.main(verbosity=2)
