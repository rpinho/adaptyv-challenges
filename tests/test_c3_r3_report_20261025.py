#!/usr/bin/env python3
"""Fail-closed behaviour of the R3 post-cutoff report.

The report is a reporting layer only, but a wrong number here would be read as
evidence. These tests pin the three properties that matter: a preview status
file is never reported as final, an eligible design without crosswalk evidence
aborts the run, and screened counts exclude designs that were never run.
"""
import importlib.util
import json
import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / 'scripts/c3_r3_report_20261025.py'


def load():
    spec = importlib.util.spec_from_file_location('rep', SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class Canonical(unittest.TestCase):
    def test_merge_collapses_members(self):
        rep = load()
        cross = {'merged_prior_labels': {'X000': ['X000', 'X003']},
                 'round1_clusters': {'a': 'X003'}, 'round2_clusters': {},
                 'round3_clusters': {'p1_x': 'X000'}}
        canon = rep.canonical_labels(cross)
        self.assertEqual(canon['X003'], 'X000')
        self.assertEqual(canon['X000'], 'X000')

    def test_conflicting_merges_fail_closed(self):
        rep = load()
        cross = {'merged_prior_labels': {'X000': ['X001'], 'X002': ['X001']},
                 'round1_clusters': {}, 'round2_clusters': {}, 'round3_clusters': {}}
        with self.assertRaises(rep.EvidenceError):
            rep.canonical_labels(cross)


class EndToEnd(unittest.TestCase):
    def _run(self, status_mut=None, cross_mut=None, keep_preview=False,
             queue_mut=None, mpnn_mut=None):
        status = json.loads((ROOT / 'results/c3_r3_20261025/status_20261025.json').read_text())
        cross = json.loads((ROOT / 'results/c3_r3_20261025/cross_tm_20261025.json').read_text())
        queue = json.loads((ROOT / 'results/c3_r3_20261025/queue_20261025.json').read_text())
        mpnn = json.loads((ROOT / 'results/c3_r3_20261025/mpnn_report.json').read_text())
        if not keep_preview:
            # The committed status file is a pre-cutoff preview; every test except
            # the preview guard itself must reach the later checks.
            status.pop('_STALE', None)
        if status_mut:
            status_mut(status)
        if cross_mut:
            cross_mut(cross)
        if queue_mut:
            queue_mut(queue)
        if mpnn_mut:
            mpnn_mut(mpnn)
        tmp = tempfile.mkdtemp()
        sp = pathlib.Path(tmp) / 's.json'
        cp = pathlib.Path(tmp) / 'c.json'
        qp = pathlib.Path(tmp) / 'q.json'
        mpp = pathlib.Path(tmp) / 'm.json'
        sp.write_text(json.dumps(status))
        cp.write_text(json.dumps(cross))
        qp.write_text(json.dumps(queue))
        mpp.write_text(json.dumps(mpnn))
        return subprocess.run(
            [sys.executable, str(SCRIPT), '--status', str(sp), '--cross', str(cp),
             '--queue', str(qp), '--mpnn', str(mpp),
             '--json', str(pathlib.Path(tmp) / 'o.json'),
             '--md', str(pathlib.Path(tmp) / 'o.md')],
            capture_output=True, text=True), pathlib.Path(tmp)

    def test_generated_total_must_reconcile_with_queue(self):
        """Kimi: counts come from recorded evidence, never inferred."""
        r, tmp = self._run(queue_mut=lambda q: q.update({'n_designs': 999}))
        self.assertEqual(r.returncode, 4, r.stderr)
        self.assertIn('declares 999 generated', r.stderr)
        self.assertFalse((tmp / 'o.json').exists())

    def test_valid_total_must_reconcile_with_rows(self):
        r, tmp = self._run(queue_mut=lambda q: q.update({'n_eligible': 999}))
        self.assertEqual(r.returncode, 4, r.stderr)
        self.assertIn('valid designs', r.stderr)

    def test_duplicate_design_names_refused(self):
        def dup(q):
            q['not_queued'].append(dict(q['not_queued'][0]))
            q['n_designs'] = q['n_designs'] + 1
        r, tmp = self._run(queue_mut=dup)
        self.assertEqual(r.returncode, 4, r.stderr)
        self.assertIn('duplicate design names', r.stderr)

    def test_incomplete_mpnn_report_refused(self):
        r, tmp = self._run(mpnn_mut=lambda m: m.update({'missing': ['x']}))
        self.assertEqual(r.returncode, 4, r.stderr)
        self.assertIn('MPNN report', r.stderr)

    def test_counts_provenance_recorded(self):
        r, tmp = self._run(status_mut=lambda s: s.pop('_STALE', None))
        self.assertEqual(r.returncode, 0, r.stderr)
        rep = json.loads((tmp / 'o.json').read_text())
        prov = rep['counts_provenance']
        self.assertTrue(prov['verified_from_recorded_evidence'])
        self.assertEqual(prov['queue_rows'], prov['queue_n_designs'])
        self.assertEqual(prov['mpnn_sequences'], prov['queue_n_designs'])

    def test_preview_status_refused(self):
        r, tmp = self._run(lambda s: s.update({'_STALE': 'preview'}), keep_preview=True)
        self.assertEqual(r.returncode, 4, r.stderr)
        self.assertIn('pre-cutoff preview', r.stderr)
        self.assertFalse((tmp / 'o.json').exists())

    def test_incomplete_crosswalk_refused(self):
        r, tmp = self._run(cross_mut=lambda c: c.update({'complete': False}))
        self.assertEqual(r.returncode, 4, r.stderr)
        self.assertFalse((tmp / 'o.json').exists())

    def test_skipped_pairs_are_evidence_failure(self):
        r, tmp = self._run(cross_mut=lambda c: c.update({'skipped_pairs': ['x:y']}))
        self.assertEqual(r.returncode, 4, r.stderr)
        self.assertIn('missing TM evidence', r.stderr)
        self.assertFalse((tmp / 'o.json').exists())

    def test_eligible_without_crosswalk_label_refused(self):
        def mut(c):
            c['round3_clusters'] = {}
        r, tmp = self._run(cross_mut=mut)
        self.assertEqual(r.returncode, 4, r.stderr)
        self.assertIn('no crosswalk label', r.stderr)
        self.assertFalse((tmp / 'o.json').exists())

    def test_screened_excludes_not_screened_and_counts_reconcile(self):
        def unstage(s):
            s.pop('_STALE', None)
        r, tmp = self._run(status_mut=unstage)
        self.assertEqual(r.returncode, 0, r.stderr)
        rep = json.loads((tmp / 'o.json').read_text())
        ov = rep['overall']
        self.assertEqual(ov['pass'] + ov['fail'] + ov['incomplete'] + ov['not_screened']
                         + ov['bad_evidence'],
                         len(rep['designs']))
        self.assertEqual(ov['screened'], len(rep['designs']) - ov['not_screened'])
        # refold failures are a pre-screen filter, so they must exceed zero while
        # the screened-only clash count stays independent of them
        self.assertGreater(ov['refold_failures'], 0)
        self.assertEqual(sum(v['refold_failures'] for v in rep['by_bin'].values()),
                         ov['refold_failures'])
        self.assertEqual(sum(v['screened'] for v in rep['by_arm'].values()), ov['screened'])
        self.assertEqual(sum(v['fully_eligible'] for v in rep['by_arm_bin'].values()),
                         ov['fully_eligible'])

    def test_report_writes_no_submission_csv(self):
        r, tmp = self._run(status_mut=lambda s: s.pop('_STALE', None))
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertFalse(list(tmp.glob('*submission*')))

    def test_independent_count_is_not_a_row_sum(self):
        """Astra: components can span groups, so the overall count must be computed
        directly. Summing arm rows would over-count any cross-group component."""
        r, tmp = self._run(status_mut=lambda s: s.pop('_STALE', None))
        self.assertEqual(r.returncode, 0, r.stderr)
        rep = json.loads((tmp / 'o.json').read_text())
        ov = rep['overall']
        direct = {d['component'] for d in rep['designs']
                  if d['status'] == 'PASS' and d['component']}
        self.assertEqual(ov['independent_components'], len(direct))
        arm_sum = sum(v['independent_components'] for v in rep['by_arm'].values())
        self.assertGreaterEqual(arm_sum, ov['independent_components'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
