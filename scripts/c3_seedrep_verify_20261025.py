#!/usr/bin/env python3
"""Verify the seed-replication arm and report baseline->replicate gate transitions.

Astra 04:11 (tiebreak) governs:
  * score rank 001 INDEPENDENTLY per seed; never take best-of-seeds
  * report transitions for all-rules PASS, structural PASS and clash status
  * report baseline-PASS retention in BOTH repeats
  * missing/error runs are INCOMPLETE, never failures, never replaced
  * retains the current runner's MSA behaviour and records each run's actual MSA hash
  * null = all 80 complete triplets keep their baseline classification in both repeats

Baseline = R3's frozen verdict (`c3_r3_20261025/screen_verify_20261025.json`), copied read-only.
Gate functions are the SAME module R3 used (c3_round2_verify_20261025.verify_one).

Writes results/c3_seed_replication_v1_20261025/verify.json and .md.
Exits 4 on duplicate artifacts, bad evidence, or a cohort/name mismatch.
"""
import collections, csv, hashlib, json, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import c3_round2_verify_20261025 as V  # noqa: E402

SR = ROOT / 'results/c3_seed_replication_v1_20261025'
R3 = ROOT / 'results/c3_r3_20261025'
ARM = 'c3_seed_replication_v1_20261025'
GROOVE = ROOT / 'results/c3_groove_reference_20261025.json'


def main():
    man = json.loads((SR / 'manifest.json').read_text())
    ver_r3 = json.loads((R3 / 'screen_verify_20261025.json').read_text())
    r3 = {r['name']: r for r in ver_r3['records']}
    refold = json.loads((SR / 'refold_source.json').read_text()) if (SR / 'refold_source.json').exists() else \
        json.loads((ROOT / 'results/c3_r3_20261025/refold_checks_20261025.json').read_text())
    groove = set(json.loads(GROOVE.read_text())['groove_residues_1based'])

    seq = {}
    for p in sorted((SR / 'per_pod').glob('p*.csv')):
        for r in csv.DictReader(open(p)):
            seq[r['name']] = (r['binder'].strip(), r['target'].strip())
    expected = [j['name'] for j in man['jobs']]
    if set(expected) != set(seq):
        print('SEEDREP VERIFY FAIL job list != pod slices', file=sys.stderr)
        return 4

    # Output dirs are named by JOB name ('<design_id>_s<seed>'), NOT by design_id. Filtering on
    # the cohort design ids silently excluded every real artifact (caught by a fixture test).
    job_set = {j['name'] for j in man['jobs']}
    loc = collections.defaultdict(list)
    for p in sorted((SR / 'out').rglob('scores.json')):
        # Only frozen job names count as arm evidence. The port-validation controls
        # (ctl_A/ctl_B/ctl_C) also live under /workspace/seedrep/out and would otherwise
        # be able to raise a false duplicate verdict. They are retained as provenance.
        if p.parent.name in job_set:
            loc[p.parent.name].append(p.parent)
    dup = sorted(n for n, v in loc.items() if len(v) > 1)

    recs = []
    for j in man['jobs']:
        n = j['name']
        hits = loc.get(n, [])
        if len(hits) > 1:
            recs.append({'name': n, 'design_id': j['design_id'], 'seed': j['seed'],
                         'status': 'bad_evidence',
                         'reasons': [f'{len(hits)} duplicate artifacts']})
            continue
        d = hits[0] if hits else SR / 'out' / 'none' / n
        rec = V.verify_one(n, seq[n][0], seq[n][1], d, refold.get(j['design_id']), groove,
                           allowed_sources=(ARM,))
        rec['design_id'] = j['design_id']
        rec['seed'] = j['seed']
        rec['msa_sha256'] = None
        for rp in sorted((SR / 'out').rglob(f'records/*-{n}-slot*.json')):
            try:
                rr = json.loads(rp.read_text())
                if rr.get('msa_sha256'):
                    rec['msa_sha256'] = rr['msa_sha256']
            except Exception:
                pass
        if n in loc:
            for a3m in sorted(hits[0].glob('*.a3m')):
                rec['msa_sha256'] = hashlib.sha256(a3m.read_bytes()).hexdigest()
                break
        recs.append(rec)

    def structural(r):
        # R3's vocabulary: structural PASS = every frozen geometry/refold gate passed, EXCLUDING
        # the iPTM floor. So a design that fails ONLY on "iPTM ... < floor" is a structural PASS.
        # Do not equate structural with the all-rules verdict (that would undercount by 8 in R3).
        if r is None:
            return None
        st = r.get('status')
        if st not in ('PASS', 'fail'):
            return None
        reasons = [str(x) for x in (r.get('reasons') or [])]
        if st == 'PASS':
            return 'PASS'
        non_iptm = [x for x in reasons if not x.startswith('iPTM ')]
        return 'PASS' if not non_iptm else 'FAIL'

    def clash(r):
        if r is None:
            return None
        c = r.get('clashes_lt2A')
        return None if c is None else ('pass' if c == 0 else 'fail')

    by_design = collections.defaultdict(dict)
    for r in recs:
        by_design[r['design_id']][r['seed']] = r
    seeds = sorted(man['seeds'])

    rows = []
    for n in man['cohort']:
        base = r3.get(n)
        rep = [by_design[n].get(s) for s in seeds]
        complete = all(x is not None and x.get('status') in ('PASS', 'fail') for x in rep)
        rows.append({
            'design_id': n,
            'baseline_status': (base or {}).get('status'),
            'baseline_iptm': (base or {}).get('iptm'),
            'baseline_clash_pass': clash(base) == 'pass',
            'replicate_status': [None if x is None else
                                 (x.get('status') if x.get('status') in ('PASS', 'fail') else 'incomplete')
                                 for x in rep],
            'replicate_iptm': [None if x is None else x.get('iptm') for x in rep],
            'replicate_clash_pass': [clash(x) for x in rep],
            'baseline_structural': structural(base),
            'replicate_structural': [structural(x) for x in rep],
            'retained_both': (complete and base is not None and base.get('status') == 'PASS'
                              and all(x['status'] == 'PASS' for x in rep)),
            'retained_any': (base is not None and base.get('status') == 'PASS'
                             and any(x['status'] == 'PASS' for x in rep if x)),
            'complete': complete,
        })

    done = [r for r in rows if r['complete']]
    base_pass = [r for r in done if r['baseline_status'] == 'PASS']
    base_fail = [r for r in done if r['baseline_status'] == 'fail']
    trans = collections.Counter()
    struct_trans = collections.Counter()
    for r in done:
        b = 'P' if r['baseline_status'] == 'PASS' else 'F'
        for s in r['replicate_status']:
            trans[f'{b}->{"P" if s == "PASS" else "F"}'] += 1
        sb = r['baseline_structural'] or 'N'
        for st in r['replicate_structural']:
            struct_trans[f'{sb}->{st or "N"}'] += 1

    out = {
        'arm': ARM,
        'n_jobs': len(recs),
        'n_cohort': len(man['cohort']),
        'n_complete_designs': len(done),
        'duplicate_artifacts': dup,
        'n_bad_evidence': sum(1 for r in recs if r.get('status') == 'bad_evidence'),
        # Two different denominators, kept explicit so a ratio cannot be misread:
        #   *_in_cohort  = all 80 cohort designs with a baseline PASS (complete or not)
        #   *_complete   = only those whose two replicates have both returned
        # "retained both" is only meaningful against baseline_pass_complete.
        'baseline_pass_in_cohort': len([r for r in rows if r['baseline_status'] == 'PASS']),
        'baseline_pass_complete': len(base_pass),
        'baseline_pass_retained_both': sum(1 for r in base_pass if r['retained_both']),
        'baseline_pass_retained_any': sum(1 for r in base_pass if r['retained_any']),
        'transitions': dict(trans),
        'structural_transitions': dict(struct_trans),
        'baseline_structural_pass_in_cohort': sum(1 for r in rows if r['baseline_structural'] == 'PASS'),
        'replicate_structural_pass_count': sum(
            1 for r in recs if structural(r) == 'PASS'),
        'fail_to_pass_designs': sorted(r['design_id'] for r in base_fail
                                       if any(s == 'PASS' for s in r['replicate_status'])),
        # Kimi 05:45 + Astra 05:46 both flagged this: a baseline-PASS design that fails in
        # ONLY ONE repeat was invisible, because "all()" required failure in every repeat.
        # Report both categories separately; neither is a failure of the design, only of the
        # replicate classification.
        'pass_to_fail_both_designs': sorted(r['design_id'] for r in base_pass
                                           if r['replicate_status'] and all(
                                               s == 'fail' for s in r['replicate_status'] if s)),
        'pass_to_fail_any_designs': sorted(r['design_id'] for r in base_pass
                                          if any(s == 'fail' for s in r['replicate_status'] if s)),
        'pass_to_fail_one_repeat_only': sorted(
            r['design_id'] for r in base_pass
            if any(s == 'fail' for s in r['replicate_status'] if s)
            and not all(s == 'fail' for s in r['replicate_status'] if s)),
        'designs_with_any_seed': sum(1 for r in rows
                                     if any(s in ('PASS', 'fail') for s in r['replicate_status'])),
        'null_holds': (len(done) == len(man['cohort'])
                       and all([('PASS' if s == 'PASS' else 'FAIL') for s in r['replicate_status']]
                               == [('PASS' if r['baseline_status'] == 'PASS' else 'FAIL')] * len(seeds)
                               for r in done)),
        'rows': rows,
        'records': recs,
        'note': ('Astra 04:11: rank 001 per seed; best-of-seeds never taken. Incomplete runs are '
                 'incomplete, never failures, never replaced. The null only applies at full coverage.'),
    }
    (SR / 'verify.json').write_text(json.dumps(out, indent=1) + '\n')

    L = ['# Seed replication — baseline vs replicate', '',
         f"- cohort **{len(man['cohort'])}** designs, **{len(recs)}** invocations, "
         f"complete designs **{len(done)}/{len(man['cohort'])}**",
         f"- baseline PASS in cohort: **{out['baseline_pass_in_cohort']}** "
         f"(of which **{out['baseline_pass_complete']}** are complete and evaluable)",
         f"- **retained PASS in both repeats: {out['baseline_pass_retained_both']}** of "
         f"**{out['baseline_pass_complete']} complete** baseline-PASS designs"
         + ('' if out['baseline_pass_complete'] == out['baseline_pass_in_cohort']
            else f" — {out['baseline_pass_in_cohort'] - out['baseline_pass_complete']} not yet evaluable"),
         f"- transitions (each repeat counted): `{out['transitions']}`",
         f"- structural transitions: `{out['structural_transitions']}`",
         f"- designs with **at least one** seed result: **{out['designs_with_any_seed']}**",
         f"- bad evidence {out['n_bad_evidence']}, duplicates {len(dup)}",
         f"- null (all complete triplets keep baseline class): **{out['null_holds']}**"
         + ('' if len(done) == len(man['cohort']) else ' — *not yet evaluable at partial coverage*')]
    (SR / 'verify.md').write_text('\n'.join(L) + '\n')
    print(f"SEEDREP verify: {len(done)}/{len(man['cohort'])} designs complete, "
          f"baseline PASS retained both={out['baseline_pass_retained_both']}/"
          f"{out['baseline_pass_complete']} complete "
          f"(cohort PASS={out['baseline_pass_in_cohort']}), transitions={dict(trans)}, "
          f"bad={out['n_bad_evidence']}, dup={len(dup)}")
    return 0 if not dup and out['n_bad_evidence'] == 0 else 4


if __name__ == '__main__':
    sys.exit(main())
