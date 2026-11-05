#!/usr/bin/env python3
"""The cutoff snapshot must ignore the N=2 runner's bookkeeping dirs.

Regression for a real fail-closed bug found at 01:55 ET: the parallel runner
keeps .claims/, records/, queue/ and failures/ inside out/, so the snapshot
reported "names outside its frozen slice" for all five pods and refused to
write. At 03:30 that would have blocked the finalizer entirely.
"""
import importlib.util
import pathlib
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('snap', ROOT / 'scripts/c3_r3_cutoff_snapshot_20261025.py')
snap = importlib.util.module_from_spec(spec)
spec.loader.exec_module(snap)


class Bookkeeping(unittest.TestCase):
    def test_bookkeeping_set_is_explicit(self):
        self.assertEqual(snap.BOOKKEEPING, {'.claims', 'records', 'queue', 'failures'})

    def test_bookkeeping_is_not_a_design(self):
        for name in snap.BOOKKEEPING:
            self.assertNotIn(name, 'p1_H8_52_64_910000_s1')

    def test_real_design_names_never_collide(self):
        # Every frozen design is pN_...; none can equal a bookkeeping dir.
        import csv
        names = {r['name'] for r in
                 csv.DictReader(open(ROOT / 'results/c3_r3_20261025/screen_input_20261025.csv'))}
        self.assertTrue(names)
        self.assertFalse(names & snap.BOOKKEEPING)

    def test_started_filter_drops_only_bookkeeping(self):
        raw = ['.claims', 'records', 'queue', 'failures', 'p1_H8_52_64_910000_s1']
        filtered = sorted(set(raw) - snap.BOOKKEEPING)
        self.assertEqual(filtered, ['p1_H8_52_64_910000_s1'])

    def test_unknown_design_still_surfaces(self):
        # A name outside the slice must NOT be silently dropped.
        raw = ['p1_H8_52_64_910000_s1', 'p9_foreign_design_s1']
        filtered = set(raw) - snap.BOOKKEEPING
        self.assertIn('p9_foreign_design_s1', filtered)


if __name__ == '__main__':
    unittest.main(verbosity=2)
