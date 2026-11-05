#!/usr/bin/env python3
"""Finalizer for the sampling-depth arm (c3_sampling_depth_v1_20261025).

Mirrors the R3 finalizer's discipline, retargeted to this arm. Status vocabulary is closed:
  PASS / FAIL / INCOMPLETE / NOT_STARTED_DEADLINE / BAD_EVIDENCE
Only the verifier decides PASS/FAIL; this script never re-scores and never writes a submission CSV.

NOT_STARTED_DEADLINE is granted only on positive pod evidence: a pod record in
cutoff_snapshot.json that does NOT list the design as started. Without that evidence the design
stays INCOMPLETE (the finalizer refuses to guess).

Writes, under results/c3_sampling_depth_v1_20261025/:
  coverage_ledger.json, status.json, summary.md, SHA256SUMS.evidence
Usage: python3 scripts/c3_sd_finalize_20261025.py [--force]
Refuses to run if the verifier output or the cutoff snapshot is missing/stale.
"""
import argparse, collections, csv, hashlib, json, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
SD = ROOT / 'results/c3_sampling_depth_v1_20261025'
LEDGER = SD / 'coverage_ledger.json'
STATUS = SD / 'status.json'
SUMMARY = SD / 'summary.md'
SUMS = SD / 'SHA256SUMS.evidence'
MARK = SD / '.finalized'


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
    ap.add_argument('--dry-run', action='store_true',
                    help='compute and print counts; write nothing')
    a = ap.parse_args()
    if MARK.exists() and not a.force:
        print(f'already finalized at {MARK.read_text().strip()}')
        return 0
    for p in (SD / 'verify.json', SD / 'cutoff_snapshot.json', SD / 'af2m_input.csv',
              SD / 'refold_checks.json'):
        if not p.exists():
            print(f'FINALIZE FAIL missing {p}', file=sys.stderr)
            return 4
    ver = json.loads((SD / 'verify.json').read_text())
    snap = json.loads((SD / 'cutoff_snapshot.json').read_text())
    refold = json.loads((SD / 'refold_checks.json').read_text())
    rows = list(csv.DictReader(open(SD / 'af2m_input.csv')))
    if ver.get('n_bad_evidence', 0) or ver.get('duplicate_artifacts'):
        print('FINALIZE FAIL bad evidence or duplicates present', file=sys.stderr)
        return 4
    vrec = {r['name']: r for r in ver['records']}
    if set(vrec) != {r['name'] for r in rows}:
        print('FINALIZE FAIL verifier cohort != frozen input', file=sys.stderr)
        return 4
    started = set()
    for rec in snap.get('pods', {}).values():
        started |= set(rec.get('started', []))
    pods = sorted(snap.get('pods', {}))
    if not pods:
        print('FINALIZE FAIL cutoff snapshot has no pod records', file=sys.stderr)
        return 4

    designs = []
    for r in sorted(rows, key=lambda x: x['name']):
        n = r['name']
        rec = vrec[n]
        st = rec.get('status')
        if st == 'PASS':
            status, reasons = 'PASS', []
        elif st == 'fail':
            status, reasons = 'FAIL', list(rec.get('reasons', []))
        elif st == 'bad_evidence':
            status, reasons = 'BAD_EVIDENCE', list(rec.get('reasons', []))
        elif n in started:
            status, reasons = 'INCOMPLETE', list(rec.get('reasons', []))
        else:
            status, reasons = 'NOT_STARTED_DEADLINE', ['no output dir at cutoff snapshot']
        designs.append({
            'name': n, 'backbone': rec.get('backbone'), 'draw': rec.get('draw'),
            'status': status, 'reasons': reasons, 'iptm': rec.get('iptm'),
            'ptm': rec.get('ptm'), 'binder_mean_plddt': rec.get('binder_mean_plddt'),
            'clashes_lt2A': rec.get('clashes_lt2A'),
            'groove_residues_contacted': rec.get('groove_residues_contacted'),
            'contacts_le5A': rec.get('contacts_le5A'),
            'refold_pass': bool((refold.get(n) or {}).get('pass')),
            'binder_sequence_sha256': rec.get('binder_sequence_sha256'),
        })
    counts = collections.Counter(d['status'] for d in designs)
    by_draw = {}
    for k in ('1', '2'):
        sub = [d for d in designs if d['draw'] == k]
        c = collections.Counter(x['status'] for x in sub)
        by_draw[f'sd{k}'] = {'expected': len(sub), 'PASS': c['PASS'], 'FAIL': c['FAIL'],
                             'INCOMPLETE': c['INCOMPLETE'],
                             'NOT_STARTED_DEADLINE': c['NOT_STARTED_DEADLINE'],
                             'BAD_EVIDENCE': c['BAD_EVIDENCE']}
    bb = collections.defaultdict(lambda: {'PASS': 0, 'FAIL': 0, 'other': 0})
    for d in designs:
        b = bb[d['backbone']]
        if d['status'] == 'PASS':
            b['PASS'] += 1
        elif d['status'] == 'FAIL':
            b['FAIL'] += 1
        else:
            b['other'] += 1

    ledger = {
        'arm': ver.get('arm'),
        'input_sha256': ver.get('input_sha256'),
        'verify_sha256': sha(SD / 'verify.json'),
        'snapshot_sha256': sha(SD / 'cutoff_snapshot.json'),
        'generated_at': snap.get('generated_at'),
        'finalized_at': __import__('datetime').datetime.now().astimezone().isoformat(timespec='seconds'),
        'n_expected': len(designs),
        'counts': dict(counts),
        'n_pass': counts['PASS'],
        'n_complete': counts['PASS'] + counts['FAIL'],
        'by_draw': by_draw,
        'n_backbones': len(bb),
        'backbones_with_pass': sorted(b for b, v in bb.items() if v['PASS']),
        'rows': designs,
        'gate': ver.get('gate'),
        'thresholds': ver.get('thresholds'),
        'note': ('evidence only; never a submission candidate. NOT_STARTED_DEADLINE is granted '
                 'only where the cutoff snapshot shows no output dir.'),
    }
    if a.dry_run:
        print(f"[dry-run] counts={dict(counts)} backbones_with_pass="
              f"{len(ledger['backbones_with_pass'])}/{len(bb)} by_draw={by_draw}")
        return 0
    LEDGER.write_text(json.dumps(ledger, indent=1) + '\n')

    L = ['# Sampling-depth arm — final coverage', '',
         f"- arm: `{ledger['arm']}`; input sha `{(ledger['input_sha256'] or '')[:12]}…`",
         f"- designs: **{len(designs)}**; backbones: **{len(bb)}**",
         f"- **{counts['PASS']} PASS**, {counts['FAIL']} FAIL, {counts['INCOMPLETE']} INCOMPLETE, "
         f"{counts['NOT_STARTED_DEADLINE']} NOT_STARTED_DEADLINE, {counts['BAD_EVIDENCE']} BAD_EVIDENCE",
         f"- backbones with ≥1 PASS: **{len(ledger['backbones_with_pass'])}** / {len(bb)}",
         '', '## By draw', '', '| draw | expected | PASS | FAIL | INCOMPLETE | NOT_STARTED |', '|---|---|---|---|---|---|']
    for k, v in by_draw.items():
        L.append(f"| {k} | {v['expected']} | {v['PASS']} | {v['FAIL']} | {v['INCOMPLETE']} | "
                 f"{v['NOT_STARTED_DEADLINE']} |")
    L += ['', '## Backbones with an all-rules PASS', '',
          '| backbone | PASS | FAIL | unfinished |', '|---|---|---|---|']
    for b in ledger['backbones_with_pass']:
        v = bb[b]
        L.append(f"| `{b}` | {v['PASS']} | {v['FAIL']} | {v['other']} |")
    SUMMARY.write_text('\n'.join(L) + '\n')
    STATUS.write_text(json.dumps({'counts': dict(counts), 'by_draw': by_draw}, indent=1) + '\n')

    # Exclude mutable control/status files. autopilot.log is already excluded by the .log rule;
    # autopilot_tmux.out is append-only and delta_b.* is rewritten after finalize, so neither can
    # be a stable evidence member. Including them made the independent SHA check fail on a
    # correct finalize (2/3306 files), which would wrongly block .finalized.
    MUTABLE = {'autopilot_tmux.out', 'autopilot.out', 'delta_b.json', 'delta_b.md',
               'completion_by_draw.json', 'pull.log', 'autopilot.log'}
    files = sorted(p for p in SD.rglob('*')
                   if p.is_file() and p.name != SUMS.name
                   and '.finalized' not in p.name
                   and '/logs/' not in str(p) and p.name not in MUTABLE
                   and not p.name.endswith('.log'))
    with open(SUMS, 'w') as fh:
        for p in files:
            fh.write(f'{sha(p)}  {rel(p)}\n')
    MARK.write_text(ledger['finalized_at'] + '\n')
    print(f"SD FINAL: {counts['PASS']}/{len(designs)} PASS, {counts['FAIL']} FAIL, "
          f"{counts['INCOMPLETE']} INCOMPLETE, {counts['NOT_STARTED_DEADLINE']} NOT_STARTED, "
          f"backbones_with_pass={len(ledger['backbones_with_pass'])}/{len(bb)}")
    print(f"  ledger {sha(LEDGER)[:12]}… evidence files={len(files)}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
