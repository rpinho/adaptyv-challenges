#!/usr/bin/env python3
"""Finalizer for the seed-replication arm (c3_seed_replication_v1_20261025).

The arm's verifier (c3_seedrep_verify_20261025.py) decides PASS/FAIL and computes the
baseline->replicate transitions. This script only freezes that evidence: an explicit status for
every one of the 160 invocations, a closed status vocabulary, a summary, and a combined
SHA256SUMS manifest.

Status vocabulary (closed):
  COMPLETE_PASS   scored and passed every frozen gate
  COMPLETE_FAIL   scored and failed at least one frozen gate
  INCOMPLETE      started but no complete artifact before the stop (never a failure)
  NOT_STARTED     no artifact and no positive started evidence
  BAD_EVIDENCE    duplicate or unreadable artifacts; never silently resolved

Only the verifier decides PASS/FAIL. This script never re-scores and never writes a submission CSV.
Incomplete runs are never counted as failures and are never replaced.

Writes, under results/c3_seed_replication_v1_20261025/:
  coverage_ledger.json, status.json, summary.md, SHA256SUMS.evidence
Usage: python3 scripts/c3_seedrep_finalize_20261025.py [--force] [--dry-run]
"""
import argparse, collections, csv, hashlib, json, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
SR = ROOT / 'results/c3_seed_replication_v1_20261025'
LEDGER = SR / 'coverage_ledger.json'
STATUS = SR / 'status.json'
SUMMARY = SR / 'summary.md'
SUMS = SR / 'SHA256SUMS.evidence'
MARK = SR / '.finalized'


def sha(p):
    h = hashlib.sha256()
    with open(p, 'rb') as fh:
        for c in iter(lambda: fh.read(1 << 20), b''):
            h.update(c)
    return h.hexdigest()


def rel(p):
    return str(pathlib.Path(p).relative_to(ROOT))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--force', action='store_true')
    ap.add_argument('--dry-run', action='store_true')
    a = ap.parse_args()
    if MARK.exists() and not a.force:
        print(f'already finalized at {MARK.read_text().strip()}')
        return 0
    for p in (SR / 'verify.json', SR / 'manifest.json'):
        if not p.exists():
            print(f'SEEDREP FINALIZE FAIL missing {p}', file=sys.stderr)
            return 4
    ver = json.loads((SR / 'verify.json').read_text())
    man = json.loads((SR / 'manifest.json').read_text())
    if ver.get('n_bad_evidence', 0) or ver.get('duplicate_artifacts'):
        print('SEEDREP FINALIZE FAIL bad evidence or duplicates present', file=sys.stderr)
        return 4
    vrec = {r['name']: r for r in ver['records']}
    expected = [j['name'] for j in man['jobs']]
    if set(vrec) != set(expected):
        print('SEEDREP FINALIZE FAIL verifier cohort != frozen manifest jobs', file=sys.stderr)
        return 4

    # Positive started-evidence: an output dir OR a .claims entry OR a records/*.json naming it.
    started = set()
    for d in (SR / 'out').rglob('*'):
        if d.is_dir() and d.name in set(expected):
            started.add(d.name)
    for p in (SR / 'out').rglob('records/*.json'):
        try:
            r = json.loads(p.read_text())
        except Exception:
            continue
        n = r.get('name') or r.get('design_id')
        if n in set(expected):
            started.add(n)
    for p in (SR / 'out').rglob('.claims/*'):
        try:
            r = json.loads(p.read_text())
        except Exception:
            continue
        n = r.get('name')
        if n in set(expected):
            started.add(n)

    by_seed = collections.defaultdict(lambda: collections.Counter())
    by_pod = collections.defaultdict(lambda: collections.Counter())
    rows = []
    for j in man['jobs']:
        n = j['name']
        rec = vrec.get(n) or {}
        st = rec.get('status')
        if st == 'PASS':
            status, reasons = 'COMPLETE_PASS', []
        elif st == 'fail':
            status, reasons = 'COMPLETE_FAIL', list(rec.get('reasons', []))
        elif st == 'bad_evidence':
            status, reasons = 'BAD_EVIDENCE', list(rec.get('reasons', []))
        elif n in started:
            status, reasons = 'INCOMPLETE', list(rec.get('reasons', []))
        else:
            status, reasons = 'NOT_STARTED', ['no artifact and no positive started evidence']
        row = {
            'name': n, 'design_id': j['design_id'], 'seed': str(j['seed']),
            'status': status, 'reasons': reasons,
            'iptm': rec.get('iptm'), 'ptm': rec.get('ptm'),
            'binder_mean_plddt': rec.get('binder_mean_plddt'),
            'clashes_lt2A': rec.get('clashes_lt2A'),
            'groove_residues_contacted': rec.get('groove_residues_contacted'),
            'contacts_le5A': rec.get('contacts_le5A'),
            'binder_sequence_sha256': rec.get('binder_sequence_sha256'),
            'msa_sha256': rec.get('msa_sha256'),
        }
        rows.append(row)
        by_seed[row['seed']][status] += 1
        # pod is derivable from the design id's prefix; keep it explicit for the ledger
        by_pod[j['design_id'].split('_')[0]][status] += 1

    counts = collections.Counter(r['status'] for r in rows)
    # Triplet completeness: a design needs BOTH seeds complete to be evaluable as a triplet.
    per_design = collections.defaultdict(list)
    for r in rows:
        per_design[r['design_id']].append(r)
    complete_triplets = sum(1 for v in per_design.values()
                            if len(v) == len(man['seeds'])
                            and all(x['status'] in ('COMPLETE_PASS', 'COMPLETE_FAIL') for x in v))

    ledger = {
        'arm': ver.get('arm'),
        'input_sha256': hashlib.sha256((SR / 'seedrep_input.csv').read_bytes()).hexdigest()
        if (SR / 'seedrep_input.csv').exists() else None,
        'cohort_sha256': man.get('cohort_sha256'),
        'jobs_sha256': man.get('jobs_sha256'),
        'n_expected': len(expected),
        'n_cohort': man.get('n_cohort'),
        'n_complete_triplets': complete_triplets,
        'counts': dict(counts),
        'by_seed': {k: dict(v) for k, v in sorted(by_seed.items())},
        'by_pod': {k: dict(v) for k, v in sorted(by_pod.items())},
        'transitions': ver.get('transitions'),
        'structural_transitions': ver.get('structural_transitions'),
        'baseline_pass_in_cohort': ver.get('baseline_pass_in_cohort'),
        'baseline_pass_retained_both': ver.get('baseline_pass_retained_both'),
        'baseline_pass_retained_any': ver.get('baseline_pass_retained_any'),
        'fail_to_pass_designs': ver.get('fail_to_pass_designs'),
        'pass_to_fail_designs': ver.get('pass_to_fail_designs'),
        'null_holds': ver.get('null_holds'),
        'duplicate_artifacts': ver.get('duplicate_artifacts'),
        'n_bad_evidence': ver.get('n_bad_evidence'),
        'rows': rows,
        'gate': ver.get('gate'),
        'note': ('evidence only; never a submission candidate. Incomplete runs are never counted '
                 'as failures and are never replaced. The null only applies at full coverage.'),
        'finalized_at': None,
    }
    import datetime
    ledger['finalized_at'] = datetime.datetime.now().astimezone().isoformat(timespec='seconds')
    if a.dry_run:
        print(f"[dry-run] counts={dict(counts)} triplets={complete_triplets}/{man['n_cohort']} "
              f"by_seed={ {k: dict(v) for k, v in sorted(by_seed.items())} }")
        return 0
    LEDGER.write_text(json.dumps(ledger, indent=1) + '\n')

    L = ['# Seed-replication arm — final coverage', '',
         f"- arm: `{ledger['arm']}`; cohort sha `{(ledger['cohort_sha256'] or '')[:12]}…`",
         f"- invocations: **{len(rows)}** across **{man.get('n_cohort')}** designs × "
         f"{len(man.get('seeds', []))} seeds",
         f"- **{counts['COMPLETE_PASS']} COMPLETE_PASS**, {counts['COMPLETE_FAIL']} COMPLETE_FAIL, "
         f"{counts['INCOMPLETE']} INCOMPLETE, {counts['NOT_STARTED']} NOT_STARTED, "
         f"{counts['BAD_EVIDENCE']} BAD_EVIDENCE",
         f"- **complete triplets: {complete_triplets}/{man.get('n_cohort')}** "
         "(a design counts only when both seeds are complete)",
         '', '## By seed', '', '| seed | PASS | FAIL | INCOMPLETE | NOT_STARTED |', '|---|---|---|---|---|']
    for k, v in sorted(by_seed.items()):
        L.append(f"| {k} | {v['COMPLETE_PASS']} | {v['COMPLETE_FAIL']} | {v['INCOMPLETE']} | "
                 f"{v['NOT_STARTED']} |")
    L += ['', '## Baseline → replicate transitions', '',
          f"- all-rules: `{ver.get('transitions')}`",
          f"- structural: `{ver.get('structural_transitions')}`",
          f"- baseline PASS retained in BOTH repeats: "
          f"**{ver.get('baseline_pass_retained_both')}** / {ver.get('baseline_pass_in_cohort')}",
          f"- baseline PASS retained in ANY repeat: "
          f"**{ver.get('baseline_pass_retained_any')}** / {ver.get('baseline_pass_in_cohort')}",
          f"- fail→PASS designs: {ver.get('fail_to_pass_designs')}",
          f"- PASS→fail in BOTH repeats: {ver.get('pass_to_fail_both_designs')}",
          f"- PASS→fail in AT LEAST ONE repeat: {ver.get('pass_to_fail_any_designs')}",
          f"- PASS→fail in exactly one repeat: {ver.get('pass_to_fail_one_repeat_only')}",
          f"- null holds: **{ver.get('null_holds')}**"
          + ('' if complete_triplets == man.get('n_cohort') else ' — *not evaluable at partial coverage*')]
    SUMMARY.write_text('\n'.join(L) + '\n')
    STATUS.write_text(json.dumps({'counts': dict(counts), 'by_seed': {k: dict(v) for k, v in by_seed.items()},
                                  'complete_triplets': complete_triplets}, indent=1) + '\n')

    # Exclude append-only control-plane output. autopilot_tmux.out is written by the live tmux
    # supervisor while it runs, so including it made a correct freeze fail its own independent
    # SHA check (1/2649) minutes later. Same defect was fixed in the depth-arm finalizer; the
    # evidence set must contain only immutable artifacts.
    MUTABLE = {'autopilot_tmux.out', 'autopilot.out', 'autopilot.log', 'pull.log', 'pipeline.log'}
    files = sorted(p for p in SR.rglob('*')
                   if p.is_file() and p.name != SUMS.name
                   and '.finalized' not in p.name
                   and '/logs/' not in str(p) and not p.name.endswith('.log')
                   and p.name not in MUTABLE)
    with open(SUMS, 'w') as fh:
        for p in files:
            fh.write(f'{sha(p)}  {rel(p)}\n')
    MARK.write_text(ledger['finalized_at'] + '\n')
    print(f"SEEDREP FINAL: {counts['COMPLETE_PASS']} PASS, {counts['COMPLETE_FAIL']} FAIL, "
          f"{counts['INCOMPLETE']} INCOMPLETE, {counts['NOT_STARTED']} NOT_STARTED; "
          f"complete triplets={complete_triplets}/{man.get('n_cohort')}")
    print(f"  ledger {sha(LEDGER)[:12]}… evidence files={len(files)}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
