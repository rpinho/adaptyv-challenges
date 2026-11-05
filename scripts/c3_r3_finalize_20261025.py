#!/usr/bin/env python3
"""R3 finalizer: explicit status for every design, per-pod completion records,
arm/bin summary, and a combined SHA256SUMS manifest.

Status vocabulary is closed and intentionally distinguishes:
  PASS          all frozen gates passed (verifier + structural when available)
  FAIL          evidence complete, at least one gate failed
  INCOMPLETE    started but no complete artifact before the cutoff
  NOT_SCREENED  excluded by the frozen queue, or never started before TIME_CUTOFF
  BAD_EVIDENCE  duplicate/corrupt artifacts; never silently resolved

Only the verifier decides PASS/FAIL. This script never re-scores and never writes a
submission CSV.

The cutoff snapshot is positive pod evidence that a design's output directory was
created. Without it, the finalizer refuses to guess started vs never-started.

Usage: python3 scripts/c3_r3_finalize_20261025.py [--verify PATH] [--structural PATH]
       [--cutoff-snapshot PATH]
"""
import argparse
import collections
import csv
import hashlib
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
R3 = ROOT / 'results/c3_r3_20261025'
STATUS_OUT = R3 / 'status_20261025.json'
SUMMARY_OUT = R3 / 'summary_20261025.md'
SUMS_OUT = R3 / 'SHA256SUMS'


def sha(path):
    h = hashlib.sha256()
    with open(path, 'rb') as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def label(path):
    try:
        return str(pathlib.Path(path).relative_to(ROOT))
    except ValueError:
        return str(path)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--verify', default=str(R3 / 'screen_verify_20261025.json'))
    ap.add_argument('--structural', default=str(R3 / 'structural_checks_20261025.json'))
    ap.add_argument('--cutoff-snapshot', default=str(R3 / 'cutoff_snapshot_20261025.json'))
    a = ap.parse_args()

    queue = json.loads((R3 / 'queue_20261025.json').read_text())
    rows = list(csv.DictReader(open(R3 / 'screen_input_20261025.csv')))
    manifest = json.loads((R3 / 'screen_input_manifest_20261025.json').read_text())
    verify_path = pathlib.Path(a.verify)
    verify = json.loads(verify_path.read_text()) if verify_path.exists() else None
    structural_path = pathlib.Path(a.structural)
    structural = json.loads(structural_path.read_text()) if structural_path.exists() else None
    refold = json.loads((R3 / 'refold_checks_20261025.json').read_text())
    snapshot_path = pathlib.Path(a.cutoff_snapshot)
    if not snapshot_path.exists():
        print(f'ERROR cutoff snapshot missing: {snapshot_path}', file=sys.stderr)
        return 4
    snapshot = json.loads(snapshot_path.read_text())
    if snapshot.get('input_sha256') != manifest['input_sha256']:
        print('ERROR cutoff snapshot cohort sha != frozen screen manifest', file=sys.stderr)
        return 4
    pod_started = {}
    for pod, rec in snapshot.get('pods', {}).items():
        started = set(rec.get('started', []))
        not_started = set(rec.get('not_started', []))
        if started & not_started:
            print(f'ERROR cutoff snapshot {pod}: started and not_started overlap', file=sys.stderr)
            return 4
        pod_started[pod] = started

    if verify is None:
        print(f'ERROR verifier output missing: {verify_path}', file=sys.stderr)
        return 4
    if verify.get('cohort_sha256') != manifest['input_sha256']:
        print('ERROR verifier cohort sha != frozen screen manifest', file=sys.stderr)
        return 4
    if len(rows) != manifest['n_designs']:
        print('ERROR frozen screen row count != manifest', file=sys.stderr)
        return 4

    vrec = {r['name']: r for r in verify['records']}
    expected = {r['name'] for r in rows}
    if set(vrec) != expected:
        print('ERROR verifier records != frozen screen cohort', file=sys.stderr)
        return 4

    not_queued = {r['name']: r for r in queue.get('not_queued', [])}
    meta = {}
    for pod, items in queue['queues'].items():
        for r in items:
            meta[r['name']] = r
    for name, r in not_queued.items():
        meta.setdefault(name, r)
    missing_snapshot = []

    designs = []
    for name in sorted(meta):
        m = meta[name]
        rec = vrec.get(name)
        if name in not_queued:
            status = 'NOT_SCREENED'
            reasons = list(not_queued[name].get('reasons', []))
        elif rec is None:
            status, reasons = 'INCOMPLETE', ['no verifier record']
        elif rec['status'] == 'incomplete':
            if m.get('pod') not in pod_started:
                missing_snapshot.append(name)
                status, reasons = 'INCOMPLETE', ['cutoff snapshot missing pod record']
            elif name not in pod_started[m['pod']]:
                status, reasons = 'NOT_SCREENED', ['TIME_CUTOFF']
            else:
                status, reasons = 'INCOMPLETE', list(rec.get('reasons', []))
        elif rec['status'] == 'bad_evidence':
            status, reasons = 'BAD_EVIDENCE', list(rec.get('reasons', []))
        elif rec['status'] == 'PASS':
            status, reasons = 'PASS', []
        else:
            status, reasons = 'FAIL', list(rec.get('reasons', []))
        if status == 'PASS':
            if structural is None:
                status, reasons = 'INCOMPLETE', ['structural evidence file missing']
            else:
                s = structural.get(name)
                if not s:
                    status, reasons = 'INCOMPLETE', ['structural record missing']
                elif s.get('status') == 'incomplete':
                    status, reasons = 'INCOMPLETE', [s.get('reason', 'structural incomplete')]
                elif not s.get('pass'):
                    status, reasons = 'FAIL', list(rec.get('reasons', [])) + [
                        s.get('reason') or 'structural checks failed']
        designs.append({
            'name': name,
            'pod': m.get('pod'),
            'arm': m.get('arm'),
            'bin': m.get('bin'),
            'seed': m.get('seed'),
            'status': status,
            'reasons': reasons,
            'iptm': (rec or {}).get('iptm'),
            'refold_pass': bool((refold.get(name) or {}).get('pass')),
            'structural_pass': ((structural or {}).get(name) or {}).get('pass'),
        })
    if missing_snapshot:
        print(f'ERROR cutoff snapshot has no pod record for {missing_snapshot[:5]}',
              file=sys.stderr)
        return 4

    expected_by_pod = collections.defaultdict(set)
    for pod, items in queue['queues'].items():
        expected_by_pod[pod] = {r['name'] for r in items}
    by_name = {d['name']: d for d in designs}
    pods = {}
    for pod in sorted(expected_by_pod):
        names = expected_by_pod[pod]
        counts = collections.Counter(by_name[n]['status'] for n in names)
        done = (counts['INCOMPLETE'] == 0 and counts['BAD_EVIDENCE'] == 0
                and counts['PASS'] + counts['FAIL'] == len(names))
        pods[pod] = {
            'expected': len(names), 'PASS': counts['PASS'], 'FAIL': counts['FAIL'],
            'INCOMPLETE': counts['INCOMPLETE'],
            'NOT_SCREENED': counts['NOT_SCREENED'],
            'BAD_EVIDENCE': counts['BAD_EVIDENCE'],
            'record': 'POD_DONE' if done else 'POD_INCOMPLETE',
        }

    def summary_by(field):
        out = {}
        for d in designs:
            k = d.get(field) or 'unknown'
            c = out.setdefault(k, collections.Counter())
            c[d['status']] += 1
        return {k: dict(sorted(v.items())) for k, v in sorted(out.items())}

    # Kimi's ledger requires a complete five-model result for SCORED. Early designs
    # were folded with num_models=5 but their per-model metric JSONs were not copied
    # off the pod, so rank-1 metrics exist while models 2-5 are no longer retrievable.
    # Those rows are still PASS on the frozen gates; the gap is evidence retention and
    # must be reported, never silently upgraded to "five-model complete".
    five = {}
    for d in designs:
        if d['status'] != 'PASS':
            continue
        ddir = next((x for x in (R3 / 'screen').rglob(d['name']) if x.is_dir()), None)
        mc = None
        nranks = 0
        if ddir is not None:
            if (ddir / 'scores.json').exists():
                try:
                    mc = json.loads((ddir / 'scores.json').read_text()).get('models_complete')
                except Exception:
                    mc = None
            nranks = len(list(ddir.glob('*_scores_rank_00[2-5]_*.json')))
        # A design counts as five-model complete only if the runner recorded the flag,
        # or the four non-rank-1 metric files are physically present. Presence alone is
        # weaker than the flag, so both are reported separately below.
        five[d['name']] = {'flag': bool(mc), 'rank_files': nranks,
                           'complete': bool(mc) or nranks >= 4}
    status = {
        'cohort_sha256': manifest['input_sha256'],
        'n_pass_five_model_complete': sum(1 for v in five.values() if v['complete']),
        'n_pass_five_model_flagged': sum(1 for v in five.values() if v['flag']),
        'n_pass_rank1_only': sum(1 for v in five.values() if not v['complete']),
        'pass_rank1_only_designs': sorted(n for n, v in five.items() if not v['complete']),
        'verify_sha256': sha(verify_path),
        'n_all': len(designs),
        'n_screened_expected': len(rows),
        'n_not_screened': sum(d['status'] == 'NOT_SCREENED' for d in designs),
        'n_not_screened_time_cutoff': sum(
            d['status'] == 'NOT_SCREENED' and 'TIME_CUTOFF' in d['reasons']
            for d in designs),
        'cutoff_snapshot_sha256': sha(snapshot_path),
        'counts': dict(sorted(collections.Counter(d['status'] for d in designs).items())),
        'pods': pods,
        'by_arm': summary_by('arm'),
        'by_bin': summary_by('bin'),
        'designs': designs,
    }
    STATUS_OUT.write_text(json.dumps(status, indent=1) + '\n')

    lines = ['# R3 overnight summary (2026-10-25)', '',
             f"Frozen screen cohort sha256: `{status['cohort_sha256']}`", '',
             '## Overall', '']
    for k in ('n_all', 'n_screened_expected', 'n_not_screened'):
        lines.append(f'- {k}: **{status[k]}**')
    lines.append('- statuses: ' + ', '.join(f'{k}={v}' for k, v in status['counts'].items()))
    lines += ['', '## Per pod', '',
              '| pod | expected | PASS | FAIL | INCOMPLETE | NOT_SCREENED | record |',
              '|---|---:|---:|---:|---:|---:|---|']
    for pod, p in pods.items():
        lines.append(f"| {pod} | {p['expected']} | {p['PASS']} | {p['FAIL']} | "
                     f"{p['INCOMPLETE']} | {p['NOT_SCREENED']} | **{p['record']}** |")
    for title, field in (('By arm', 'by_arm'), ('By length bin', 'by_bin')):
        lines += ['', f'## {title}', '']
        for k, v in status[field].items():
            lines.append(f"- {k}: " + ', '.join(f'{s}={n}' for s, n in v.items()))
    lines += ['', '## Five-model evidence (Kimi ledger rule)', '',
              f"- PASS with all five models retained: **{status['n_pass_five_model_complete']}**",
              f"- PASS with rank-1 metrics only: **{status['n_pass_rank1_only']}**",
              f"- of the complete set, carrying the runner's explicit five-model flag: "
              f"**{status['n_pass_five_model_flagged']}**",
              '', 'A rank-1-only PASS was folded with `num_models=5` but its per-model metric',
              'JSONs were never copied off the pod and are no longer retrievable. The frozen',
              'gates were still evaluated on rank-1 metrics and structure; the design is not',
              'demoted, but it does not meet the strict "complete five-model result" wording.',
              '']
    lines += ['', '`INCOMPLETE` means the pod started the design but no complete artifact',
              'survived the cutoff. `NOT_SCREENED` with `TIME_CUTOFF` means the pod never',
              'created its output directory. Neither is a biological failure and neither is',
              'eligible. The cutoff snapshot is the positive start evidence.', '']
    SUMMARY_OUT.write_text('\n'.join(lines))

    files = sorted(p for p in R3.rglob('*') if p.is_file() and p != SUMS_OUT)
    with SUMS_OUT.open('w') as fh:
        for p in files:
            fh.write(f'{sha(p)}  {label(p)}\n')
    print('\n'.join(lines))
    print(f'wrote {label(STATUS_OUT)}')
    print(f'wrote {label(SUMMARY_OUT)}')
    print(f'wrote {label(SUMS_OUT)} over {len(files)} files; '
          f'sha256={sha(SUMS_OUT)}')
    return 4 if status['counts'].get('BAD_EVIDENCE') else 0


if __name__ == '__main__':
    sys.exit(main())
