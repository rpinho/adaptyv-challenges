#!/usr/bin/env python3
"""R3 post-cutoff summary: the counts Kimi's ledger requires but the finalizer omits.

Reads only frozen/per-run artifacts and writes two new files:
  results/c3_r3_20261025/report_20261025.json
  results/c3_r3_20261025/report_20261025.md

Per H8/H4 arm and per length bin it reports: generated, valid (eligible for screening),
screened, clash failures, fully eligible (all frozen gates), and crosswalked-independent
counts. Independence uses the SHARED X### namespace: each design maps to its backbone's
crosswalk label, and labels merged by the crosswalk collapse to one canonical component.

Fail-closed conditions (exit 4, nothing written):
  * the status file is a pre-cutoff preview (`_STALE` present) and --allow-preview is absent;
  * the crosswalk artifact is incomplete or its R3 node set differs from the frozen backbones;
  * an eligible design has no backbone record, no crosswalk label, or no canonical mapping;
  * a queue/status bin or arm is missing from the frozen queue.

This script never scores, never promotes, never writes a submission CSV, and never
re-runs a gate. It is a reporting layer over already-frozen evidence.
"""
import argparse
import collections
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
R3 = ROOT / 'results/c3_r3_20261025'
STATUS = R3 / 'status_20261025.json'
QUEUE = R3 / 'queue_20261025.json'
CROSS = R3 / 'cross_tm_20261025.json'
STRUCT = R3 / 'structural_checks_20261025.json'
REFOLD = R3 / 'refold_checks_20261025.json'
MPNN = R3 / 'mpnn_report.json'
OUT_JSON = R3 / 'report_20261025.json'
OUT_MD = R3 / 'report_20261025.md'
ARMS = ('H4', 'H8')
BINS = ('52_64', '65_80', '81_100')


class EvidenceError(Exception):
    pass


def canonical_labels(cross):
    """label -> canonical component, collapsing every recorded crosswalk merge."""
    canon = {}
    for rep, members in cross.get('merged_prior_labels', {}).items():
        group = sorted(set(members) | {rep})
        for m in group:
            if m in canon and canon[m] != rep:
                raise EvidenceError(f'label {m} merged into two components '
                                    f'({canon[m]}, {rep})')
            canon[m] = rep
    for scope in ('round1_clusters', 'round2_clusters', 'round3_clusters'):
        for name, label in cross.get(scope, {}).items():
            canon.setdefault(label, label)
    return canon


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--status', default=str(STATUS))
    ap.add_argument('--queue', default=str(QUEUE))
    ap.add_argument('--cross', default=str(CROSS))
    ap.add_argument('--structural', default=str(STRUCT))
    ap.add_argument('--refold', default=str(REFOLD))
    ap.add_argument('--mpnn', default=str(MPNN))
    ap.add_argument('--json', default=str(OUT_JSON))
    ap.add_argument('--md', default=str(OUT_MD))
    ap.add_argument('--allow-preview', action='store_true',
                    help='rehearse on a pre-cutoff preview status file')
    a = ap.parse_args()

    for p in (a.status, a.queue, a.cross):
        if not pathlib.Path(p).exists():
            print(f'ERROR missing required evidence: {p}', file=sys.stderr)
            return 4
    status = json.loads(pathlib.Path(a.status).read_text())
    queue = json.loads(pathlib.Path(a.queue).read_text())
    cross = json.loads(pathlib.Path(a.cross).read_text())

    if status.get('_STALE') and not a.allow_preview:
        print('ERROR status file is a pre-cutoff preview (_STALE present); '
              'refusing to report provisional counts', file=sys.stderr)
        return 4
    if not cross.get('complete'):
        print('ERROR crosswalk artifact is not marked complete', file=sys.stderr)
        return 4
    if cross.get('skipped_pairs') or cross.get('skipped_files'):
        raise EvidenceError('crosswalk has skipped files/pairs; missing TM evidence '
                            'is never independence')
    if cross.get('round3_backbones') != cross.get('round3_expected'):
        raise EvidenceError('crosswalk R3 backbone count != frozen expected count')

    designs = status.get('designs') or []
    if not designs:
        print('ERROR status file has no design records', file=sys.stderr)
        return 4

    # ---- generated / valid from the frozen queue (one flat list, both sets)
    frozen_rows = list(queue.get('not_queued', [])) + [
        x for v in queue.get('queues', {}).values() for x in v]
    n_generated_backbones = queue.get('n_backbones')
    n_generated_designs = queue.get('n_designs')
    total_valid = queue.get('n_eligible')

    # Kimi: counts must come from recorded evidence, never be inferred. The frozen
    # queue must account for exactly the generated population it declares, with no
    # duplicates, and (when the MPNN report exists) the sequence count must agree.
    # Any disagreement means the totals are not reconstructible -> refuse.
    names = [r.get('name') for r in frozen_rows]
    if None in names or len(names) != len(set(names)):
        raise EvidenceError('frozen queue has missing or duplicate design names; '
                            'generated/valid totals are not reconstructible')
    if len(frozen_rows) != n_generated_designs:
        raise EvidenceError(f'frozen queue covers {len(frozen_rows)} designs but '
                            f'declares {n_generated_designs} generated')
    n_valid_rows = sum(1 for r in frozen_rows
                       if r.get('eligible', True) and not r.get('reasons'))
    if total_valid is not None and n_valid_rows != total_valid:
        raise EvidenceError(f'queue rows give {n_valid_rows} valid designs but the '
                            f'frozen queue declares {total_valid}')
    n_backbones_rows = len({r.get('backbone') for r in frozen_rows})
    if n_generated_backbones is not None and n_backbones_rows != n_generated_backbones:
        raise EvidenceError(f'frozen queue covers {n_backbones_rows} backbones but '
                            f'declares {n_generated_backbones} generated')
    mpnn_report = None
    mp = pathlib.Path(a.mpnn)
    if mp.exists():
        mpnn_report = json.loads(mp.read_text())
        if mpnn_report.get('missing') or mpnn_report.get('problems'):
            raise EvidenceError('MPNN report records missing sequences or problems; '
                                'generated/valid totals are not reconstructible')
        if mpnn_report.get('n_sequences') != n_generated_designs:
            raise EvidenceError(f'MPNN report has {mpnn_report.get("n_sequences")} '
                                f'sequences but the queue declares '
                                f'{n_generated_designs} designs')
    counts_source = {
        'queue': str(pathlib.Path(a.queue)),
        'queue_n_designs': n_generated_designs,
        'queue_rows': len(frozen_rows),
        'queue_valid_rows': n_valid_rows,
        'queue_declared_valid': total_valid,
        'queue_backbones': n_backbones_rows,
        'mpnn_report': str(mp) if mpnn_report else None,
        'mpnn_sequences': (mpnn_report or {}).get('n_sequences'),
        'verified_from_recorded_evidence': True,
    }

    # ---- backbone mapping: design -> backbone, and the frozen backbone set
    bb_of = {}
    for r in frozen_rows:
        bb_of.setdefault(r['name'], r.get('backbone'))
    r3_labels = cross.get('round3_clusters', {})
    canon = canonical_labels(cross)
    prior_labels = set(cross.get('round1_clusters', {}).values()) | \
        set(cross.get('round2_clusters', {}).values())
    prior_canon = {canon.get(x, x) for x in prior_labels}

    # ---- per-design annotation
    struct = {}
    sp = pathlib.Path(a.structural)
    if sp.exists():
        struct = json.loads(sp.read_text())
    refold = {}
    rp = pathlib.Path(a.refold)
    if rp.exists():
        refold = json.loads(rp.read_text())

    rows = []
    for d in designs:
        name = d['name']
        bb = bb_of.get(name)
        label = r3_labels.get(bb) if bb else None
        if d['status'] == 'PASS':
            if not bb:
                raise EvidenceError(f'{name}: eligible design has no backbone record')
            if not label:
                raise EvidenceError(f'{name}: backbone {bb} has no crosswalk label')
            if label not in canon:
                raise EvidenceError(f'{name}: crosswalk label {label} has no canonical '
                                    f'component')
        s = struct.get(name) or {}
        clash = s.get('heavy_atom_pairs_lt2A')
        clash_fail = bool(s) and isinstance(clash, int) and clash > 0
        rows.append({
            'name': name, 'arm': d.get('arm'), 'bin': d.get('bin'),
            'pod': d.get('pod'), 'status': d['status'],
            'reasons': d.get('reasons', []), 'iptm': d.get('iptm'),
            'backbone': bb,
            'crosswalk_label': label,
            'component': canon.get(label) if label else None,
            'clash_pairs_lt2A': clash if isinstance(clash, int) else None,
            'clash_fail': clash_fail,
            'refold_pass': bool((refold.get(name) or {}).get('pass')),
            'structural_pass': s.get('pass'),
        })

    def block(pred):
        sel = [r for r in rows if pred(r)]
        # A design is SCREENED only if a pod actually ran it; NOT_SCREENED means
        # the frozen queue excluded it and it never produced an artifact.
        ran = [r for r in sel if r['status'] != 'NOT_SCREENED']
        elig = [r for r in sel if r['status'] == 'PASS']
        comps = {r['component'] for r in elig}
        new_only = {c for c in comps if c not in prior_canon}
        return {
            'generated_designs': gen_count(pred, 'gen'),
            'valid_designs': gen_count(pred, 'valid'),
            'screened': len(ran),
            'pass': len(elig),
            'fail': sum(1 for r in sel if r['status'] == 'FAIL'),
            'incomplete': sum(1 for r in sel if r['status'] == 'INCOMPLETE'),
            'not_screened': sum(1 for r in sel if r['status'] == 'NOT_SCREENED'),
            # The finalizer has a fifth terminal status. Omitting it made the
            # status counts sum to less than the design total whenever a duplicate
            # artifact existed. Report it explicitly; never fold it into PASS/FAIL.
            'bad_evidence': sum(1 for r in sel if r['status'] == 'BAD_EVIDENCE'),
            'clash_failures': sum(1 for r in ran if r['clash_fail']),
            # Refold is a PRE-screen filter: a refold failure is excluded from the
            # queue, so counting it among screened designs would always read 0.
            'refold_failures': gen_count(pred, 'refold_fail'),
            'fully_eligible': len(elig),
            'independent_components': len(comps),
            'components_without_prior_member': len(new_only),
            'eligible_designs': sorted(r['name'] for r in elig),
        }

    def gen_count(pred, which):
        n = 0
        for r in frozen_rows:
            if not pred({'arm': r.get('arm'), 'bin': r.get('bin'),
                         'pod': r.get('pod')}):
                continue
            if which == 'gen':
                n += 1
            elif which == 'valid' and r.get('eligible', True) and not r.get('reasons'):
                n += 1
            elif which == 'refold_fail' and 'refold_fail' in (r.get('reasons') or []):
                n += 1
            elif which not in ('valid', 'refold_fail'):
                raise EvidenceError(f'unknown count kind {which}')
        return n

    overall = block(lambda r: True)
    by_arm = {k: block(lambda r, k=k: r['arm'] == k) for k in ARMS}
    by_bin = {k: block(lambda r, k=k: r['bin'] == k) for k in BINS}
    by_arm_bin = {(arm, b): block(lambda r, a=arm, b=b: r['arm'] == a and r['bin'] == b)
                  for arm in ARMS for b in BINS}

    unknown = sorted({(r['arm'], r['bin']) for r in rows} - set(by_arm_bin))
    if unknown:
        raise EvidenceError(f'arms/bins outside the frozen scheme: {unknown[:5]}')

    report = {
        'cohort_sha256': status.get('cohort_sha256'),
        'status_sha256_source': str(pathlib.Path(a.status)),
        'preview': bool(status.get('_STALE')),
        'crosswalk_complete': bool(cross.get('complete')),
        'malformed': {},
        'generated': {'backbones': n_generated_backbones,
                      'designs': n_generated_designs,
                      'valid_eligible_designs': total_valid},
        'mpnn': mpnn_report,
        'counts_provenance': counts_source,
        'overall': overall,
        'by_arm': by_arm,
        'by_bin': by_bin,
        'by_arm_bin': {f'{k[0]}|{k[1]}': v for k, v in by_arm_bin.items()},
        'designs': rows,
        'note': ('reporting layer only: no gate, score, CSV or promotion is written; '
                 'crosswalked independence uses the shared X### namespace'),
    }
    report['malformed'] = {r['name']: 'structural record absent'
                           for r in rows
                           if r['status'] == 'PASS' and not struct.get(r['name'])}
    pathlib.Path(a.json).write_text(json.dumps(report, indent=1) + '\n')

    L = ['# R3 post-cutoff report (2026-10-25)', '',
         f'Frozen cohort sha256: `{report["cohort_sha256"]}`', '',
         ('> **PREVIEW — rehearsal on a pre-cutoff status file.**' if report['preview']
          else '> Generated after the cutoff from frozen evidence. Nothing submitted.'),
         '',
         '## Cohort', '',
         f'- backbones generated: **{n_generated_backbones}**',
         f'- designs generated: **{n_generated_designs}**',
         f'- valid (eligible for screening): **{total_valid}**',
         f'- screened on a pod: **{overall["screened"]}**',
         f'- fully eligible (all frozen gates): **{overall["fully_eligible"]}**',
         f'- crosswalked-independent components: **{overall["independent_components"]}**',
         f'- of those, containing no round-1/round-2 member: '
         f'**{overall["components_without_prior_member"]}**', '']
    hdr = ('| unit | generated | valid | screened | clash fails | refold fails | '
           'fully eligible | independent | new-only |')
    sep = '|---|---:|---:|---:|---:|---:|---:|---:|---:|'

    def table(title, groups):
        L.extend([f'## {title}', '', hdr, sep])
        for k, v in groups.items():
            L.append(f'| {k} | {v["generated_designs"]} | {v["valid_designs"]} | '
                     f'{v["screened"]} | {v["clash_failures"]} | '
                     f'{v["refold_failures"]} | {v["fully_eligible"]} | '
                     f'{v["independent_components"]} | '
                     f'{v["components_without_prior_member"]} |')
        L.append('')

    table('Overall', {'all': overall})
    table('By arm', by_arm)
    table('By length bin', by_bin)
    table('By arm x bin', {f'{k[0]} {k[1]}': v for k, v in by_arm_bin.items()})

    L.extend(['## Notes', '',
              '- `fully eligible` means every frozen gate passed (verifier + structural '
              '+ refold). It is not a promotion decision.',
              '- `independent` counts distinct crosswalked X### components among the '
              'eligible designs; `new-only` counts those with no round-1/round-2 member. '
              '`new-only` is NOT a novelty claim.',
              '- Independence is de-duplicated **within each scope**: a component whose '
              'members span arms or bins appears in each of those rows, so the arm/bin '
              'counts do not sum to the overall count. Use the Overall row directly.',
              '- `clash fails` counts screened designs whose structural record has any '
              'heavy-atom pair < 2 A.',
              '- Designs excluded before screening (soluble/refold filters) are not '
              'screened and never counted as biological failures.', ''])
    pathlib.Path(a.md).write_text('\n'.join(L))

    print(f'R3 report: generated={n_generated_backbones}bb/{n_generated_designs}designs '
          f'valid={total_valid} screened={overall["screened"]} '
          f'eligible={overall["fully_eligible"]} '
          f'independent={overall["independent_components"]} '
          f'new-only={overall["components_without_prior_member"]}')
    print(f'wrote {a.json} and {a.md}')
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except EvidenceError as ex:
        print(f'EVIDENCE FAIL: {ex}', file=sys.stderr)
        print('R3 report refused; nothing written', file=sys.stderr)
        sys.exit(4)
