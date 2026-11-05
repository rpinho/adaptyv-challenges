#!/usr/bin/env python3
"""Regression tests for R3 structural artifact lookup (sharded pull layout)."""
import importlib.util
import pathlib
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    's', ROOT / 'scripts/c3_r3_structural_20261025.py')
s = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(s)


class ArtifactIndex(unittest.TestCase):
    def test_finds_sharded_pull_layout(self):
        with tempfile.TemporaryDirectory() as d:
            root = pathlib.Path(d)
            p = root / 'p3' / 'design_A' / 'complex_rank_001.pdb'
            p.parent.mkdir(parents=True)
            p.write_text('ATOM\n')
            self.assertEqual(s.artifact_index(root), {'design_A': [p]})

    def test_retains_duplicates_for_bad_evidence(self):
        with tempfile.TemporaryDirectory() as d:
            root = pathlib.Path(d)
            paths = []
            for pod in ('p1', 'p3'):
                p = root / pod / 'design_A' / 'complex_rank_001.pdb'
                p.parent.mkdir(parents=True)
                p.write_text('ATOM\n')
                paths.append(p)
            self.assertEqual(s.artifact_index(root), {'design_A': paths})

    def test_missing_dir_is_empty(self):
        self.assertEqual(s.artifact_index(pathlib.Path('/no/such/r3')), {})


if __name__ == '__main__':
    unittest.main(verbosity=2)
