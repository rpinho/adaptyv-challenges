#!/usr/bin/env python3
"""Exact-root recognition for the N=2 parallel driver.

The three controllers (freezer, quiesce, guard/autopilot/launcher shell
patterns) must find the parallel driver and must never match the sibling
LigandMPNN lane. Attempt directories are /tmp/<batch>-<design>-slot<k>, so the
design name has to be recovered, not read off the directory.
"""
import importlib.util
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]


def load(name, rel):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


freeze = load('freeze', 'scripts/c3_r3_admission_freeze_pod.py')
q = load('q', 'scripts/c3_r3_quiesce_pod.py')

PAR_ROOT = ['bash', '/workspace/r3_pod_run_par.sh', '/workspace/r3_screen/input.csv',
            'ALL', '/workspace/r3_screen/out', '2']
PAR_PY = ['/workspace/af2m/venv/bin/python3.10', '/workspace/pod_run_par.py',
          '/workspace/r3_screen/input.csv', '/workspace/r3_screen/out', '2']
PAR_PY_SLOT = ['python3', '/workspace/r3_screen/pod_run_par.py',
               '/workspace/r3_screen/input.csv', '/workspace/r3_screen/out', '1']
SERIAL_ROOT = ['bash', '/workspace/r3_pod_run.sh', '/workspace/r3_screen/input.csv',
               'ALL', '/workspace/r3_screen/out']
SIBLING = ['bash', '/workspace/pod_run.sh', '/workspace/lmp_screen_p1.csv', 'ALL',
           '/workspace/lmp_out']


class RootRecognition(unittest.TestCase):
    def test_parallel_wrapper_is_a_root(self):
        self.assertTrue(freeze.is_root(PAR_ROOT))
        self.assertTrue(q.is_root(PAR_ROOT))

    def test_parallel_python_without_wrapper_is_found(self):
        self.assertTrue(freeze.is_par_root(PAR_PY))
        self.assertTrue(q.is_par_root(PAR_PY))
        self.assertTrue(q.is_par_root(PAR_PY_SLOT))

    def test_sibling_lane_never_matches(self):
        for mod in (freeze, q):
            self.assertFalse(mod.is_root(SIBLING))
            self.assertFalse(mod.is_par_root(SIBLING))
        self.assertFalse(freeze.is_par_root(['python3', '/workspace/pod_run_par.py',
                                             '/workspace/lmp_screen_p1.csv']))
        self.assertFalse(q.is_par_root(['python3', '/workspace/pod_run_par.py',
                                        '/workspace/e3_screen/input.csv']))
        self.assertFalse(q.is_par_root(['sh', '/workspace/pod_run_par.py',
                                        '/workspace/r3_screen/input.csv']))

    def test_serial_still_matches(self):
        self.assertTrue(freeze.is_root(SERIAL_ROOT))
        self.assertTrue(q.is_root(SERIAL_ROOT))


class ParallelPythonDriver(unittest.TestCase):
    def test_parallel_python_driver_recognized_under_wrapper(self):
        table = {
            10: {'args': PAR_ROOT, 'ppid': 1, 'pgid': 10, 'sid': 10},
            11: {'args': PAR_PY, 'ppid': 10, 'pgid': 10, 'sid': 10},
        }
        self.assertTrue(freeze.is_python_driver(11, table, 10))

    def test_serial_python_still_recognized(self):
        table = {
            10: {'args': SERIAL_ROOT, 'ppid': 1, 'pgid': 10, 'sid': 10},
            11: {'args': ['python3', '/workspace/r3_screen/c3_r3_pod_run.py',
                          '/workspace/r3_screen/input.csv', 'ALL',
                          '/workspace/r3_screen/out'], 'ppid': 10, 'pgid': 10, 'sid': 10},
        }
        self.assertTrue(freeze.is_python_driver(11, table, 10))

    def test_two_parallel_folds_are_both_found_and_named(self):
        table = {
            10: {'args': PAR_ROOT, 'ppid': 1, 'pgid': 10, 'sid': 10},
            11: {'args': PAR_PY, 'ppid': 10, 'pgid': 10, 'sid': 10},
            12: {'args': ['/workspace/af2m/venv/bin/python3.10',
                          '/workspace/af2m/venv/bin/colabfold_batch',
                          '/tmp/r3_p1_053000-p1_H8_910002_s1-slot0/p1_H8_910002_s1.fasta',
                          '/tmp/r3_p1_053000-p1_H8_910002_s1-slot0/out'],
                 'ppid': 11, 'pgid': 10, 'sid': 10},
            13: {'args': ['/workspace/af2m/venv/bin/python3.10',
                          '/workspace/af2m/venv/bin/colabfold_batch',
                          '/tmp/r3_p1_053000-p1_H8_910003_s1-slot1/p1_H8_910003_s1.fasta',
                          '/tmp/r3_p1_053000-p1_H8_910003_s1-slot1/out'],
                 'ppid': 11, 'pgid': 10, 'sid': 10},
        }
        folds = sorted(freeze.folds_for(11, table), key=lambda x: x[0])
        self.assertEqual([p for p, _ in folds], [12, 13])
        self.assertEqual([n for _, n in folds], ['p1_H8_910002_s1', 'p1_H8_910003_s1'])


class AttemptDirMapping(unittest.TestCase):
    def test_attempt_dir_maps_to_design(self):
        self.assertEqual(freeze.design_from_attempt('r3_p1_053000-p1_H8_910002_s1-slot0'),
                         'p1_H8_910002_s1')
        self.assertEqual(freeze.design_from_attempt('b20261025T051500Z-p5_H4_910301_s2-slot1'),
                         'p5_H4_910301_s2')

    def test_unknown_shapes_are_not_guessed(self):
        self.assertIsNone(freeze.design_from_attempt('p1_H8_910002_s1'))
        self.assertIsNone(freeze.design_from_attempt('random'))

    def test_fasta_header_is_authoritative(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            fa = pathlib.Path(tmp) / 'x.fasta'
            fa.write_text('>p9_REAL_s1\nACDEF\n')
            self.assertEqual(freeze.design_from_fasta(str(fa)), 'p9_REAL_s1')
            self.assertEqual(freeze.design_of('weird-name-slot0', str(fa)), 'p9_REAL_s1')

    def test_design_of_falls_back_to_attempt_without_fasta(self):
        self.assertEqual(freeze.design_of(
            'r3_p1_053000-p1_H8_910002_s1-slot0', '/nonexistent.fasta'),
            'p1_H8_910002_s1')

    def test_fasta_header_wins_over_a_dash_in_the_batch_id(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            fa = pathlib.Path(tmp) / 'x.fasta'
            fa.write_text('>p1_H8_910002_s1\nACDEF\n')
            # batch id contains a dash: attempt parsing alone would be wrong
            self.assertEqual(freeze.design_of('r3-p1-053000-x-slot0', str(fa)),
                             'p1_H8_910002_s1')


class WrapperRefusesDuplicate(unittest.TestCase):
    """The wrapper must never become a second driver (recurring failure tonight).

    Evaluated by extracting the awk program the wrapper runs, so the test
    exercises the real expression rather than a re-implementation.
    """

    def awk_program(self):
        src = (ROOT / 'scripts/c3_r3_pod_run_par.sh').read_text()
        start = src.index("others=$(ps -eo pid=,args= | awk -v me=")
        body = src[start:]
        body = body[body.index('awk -v me="$$'):]
        # take the single-quoted awk program
        first = body.index("'")
        second = body.index("'", first + 1)
        return body[first + 1:second]

    def run_awk(self, lines, me='999'):
        import subprocess
        prog = self.awk_program().replace('\n', ' ')
        r = subprocess.run(['awk', '-v', f'me={me}', prog], input='\n'.join(lines) + '\n',
                           capture_output=True, text=True)
        return r.stdout.split()

    SIBLING = '104 bash /workspace/pod_run.sh /workspace/lmp_screen_p1.csv ALL /workspace/lmp_out'
    SERIAL = '103 bash /workspace/r3_pod_run.sh /workspace/r3_screen/input.csv ALL /workspace/r3_screen/out'
    PAR_SH = '100 bash /workspace/r3_pod_run_par.sh /workspace/r3_screen/input.csv ALL /workspace/r3_screen/out 2'
    PAR_PY = '101 python3 /workspace/pod_run_par.py /workspace/r3_screen/input.csv /workspace/r3_screen/out 2'
    FOLD = '102 /workspace/af2m/venv/bin/python3.10 /workspace/af2m/venv/bin/colabfold_batch /tmp/a/a.fasta /tmp/a/out'

    def test_refuses_when_parallel_python_alive(self):
        self.assertEqual(self.run_awk([self.PAR_PY]), ['101'])

    def test_refuses_when_parallel_wrapper_alive(self):
        self.assertEqual(self.run_awk([self.PAR_SH]), ['100'])

    def test_allows_when_only_serial_and_sibling(self):
        self.assertEqual(self.run_awk([self.SERIAL, self.SIBLING, self.FOLD]), [])

    def test_ignores_its_own_pid(self):
        self.assertEqual(self.run_awk([self.PAR_SH], me='100'), [])

    def test_ignores_sibling_lane_entirely(self):
        self.assertEqual(self.run_awk([self.SIBLING]), [])


if __name__ == '__main__':
    unittest.main(verbosity=2)
