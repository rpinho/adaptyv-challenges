#!/usr/bin/env python3
"""Delta-B for the sampling-depth arm (Kimi 2026-10-25 03:34, Q4; adopted by the 03:44 conflict ruling).

Definition, implemented verbatim:
  Delta-B = distinct backbones that gain their FIRST all-rules PASS from this arm.
  Unit = backbone (not component, not sequence). "First" is relative to R3, which screened the same
  120 backbone cohort; a backbone that already had an all-rules PASS in R3 cannot contribute.
  Unfinished designs are NOT failures: they are reported separately and excluded from both sides.

Gate is not touched: PASS/fail comes from scripts/c3_sd_verify_20261025.py, which reuses the R3
verifier unchanged. This script only *counts*.

Also reports, per Astra's truncation rule, completion BY BACKBONE and BY DRAW.

Read-only. Writes results/c3_sampling_depth_v1_20261025/delta_b.json (+ .md table).
Exits 4 on any missing input, duplicate design, or backbone/source mismatch.
"""
import collections, csv, json, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
SD = ROOT / 'results/c3_sampling_depth_v1_20261025'
R3 = ROOT / 'results/c3_r3_20261025'
ARM = 'c3_sampling_depth_v1_20261025'


def die(msg):
    print(f'DELTA-B FAIL {msg}', file=sys.stderr)
    return 4


def main():
    ver_p, r3_p, inp_p = SD / 'verify.json', R3 / 'report_20261025.json', SD / 'af2m_input.csv'
    for p in (ver_p, r3_p, inp_p):
        if not p.exists():
            return die(f'missing {p}')
    ver = json.loads(ver_p.read_text())
    r3 = json.loads(r3_p.read_text())
    rows = list(csv.DictReader(open(inp_p)))

    if ver.get('arm') != ARM:
        return die(f"verify.json arm is {ver.get('arm')!r}, expected {ARM}")
    if {r['source'] for r in rows} != {ARM}:
        return die('arm input contains a non-arm source')

    names = [r['name'] for r in rows]
    if len(names) != len(set(names)):
        return die('duplicate design name in arm input')
    expected = set(names)

    recs = ver['records']
    if {r['name'] for r in recs} != expected:
        return die('verify records do not cover the arm input exactly')
    if ver.get('n_bad_evidence', 0) != 0 or ver.get('duplicate_artifacts'):
        return die('bad evidence or duplicate artifacts present; refusing to count')

    # --- R3 baseline: backbones that already had >=1 all-rules PASS in R3 ---
    r3_status = collections.defaultdict(list)
    for d in r3['designs']:
        if d.get('status') in ('PASS', 'FAIL'):
            r3_status[d['backbone']].append(d['status'])
    r3_pass_bb = {b for b, s in r3_status.items() if 'PASS' in s}
    r3_scored_bb = set(r3_status)
    r3_all_bb = {d['backbone'] for d in r3['designs']}

    # --- arm results by backbone ---
    arm = collections.defaultdict(lambda: {'sd1': [], 'sd2': []})
    # every arm backbone is known from the frozen input, whether or not it has a result yet
    plan = collections.defaultdict(set)
    for r in rows:
        if '_sd' not in r['name']:
            return die(f"cannot parse draw from {r['name']}")
        bb, draw = r['name'].rsplit('_', 1)
        if draw not in ('sd1', 'sd2'):
            return die(f"unknown draw {draw} in {r['name']}")
        plan[bb].add(draw)
        arm[bb]  # materialise
    incomplete = []
    for r in recs:
        n = r['name']
        bb, draw = n.rsplit('_', 1)
        st = r.get('status')
        if st in ('pass', 'PASS'):
            arm[bb][draw].append('PASS')
        elif st == 'fail':
            arm[bb][draw].append('FAIL')
        elif st == 'incomplete':
            incomplete.append(n)
        else:
            return die(f'unexpected status {st!r} for {n}')

    if set(arm) - r3_all_bb:
        return die(f'arm backbones outside the R3 cohort: {sorted(set(arm) - r3_all_bb)[:3]}')

    delta_b, still_zero, already = [], [], []
    for bb in sorted(arm):
        scored = [s for dr in ('sd1', 'sd2') for s in arm[bb][dr]]
        got_pass = 'PASS' in scored
        if bb in r3_pass_bb:
            already.append(bb)
        elif got_pass:
            delta_b.append(bb)
        else:
            still_zero.append(bb)

    # completion by backbone / by draw
    by_bb = sum(1 for bb in arm if arm[bb]['sd1'] or arm[bb]['sd2'])
    full_bb = sum(1 for bb in arm
                  if set(plan[bb]) == {'sd1', 'sd2'} and arm[bb]['sd1'] and arm[bb]['sd2'])
    by_draw = {dr: {'expected': sum(1 for r in recs if r['name'].endswith('_' + dr)),
                    'complete': sum(len(arm[bb][dr]) for bb in arm),
                    'pass': sum(1 for bb in arm for s in arm[bb][dr] if s == 'PASS')}
               for dr in ('sd1', 'sd2')}

    out = {
        'arm': ARM,
        'definition': ('distinct backbones gaining their FIRST all-rules PASS from this arm; '
                       'baseline = backbones with >=1 all-rules PASS in R3 (same 120-backbone cohort)'),
        'n_arm_designs': len(recs),
        'n_arm_backbones': len(arm),
        'n_r3_backbones': len(r3_all_bb),
        'n_r3_backbones_with_pass': len(r3_pass_bb),
        'n_r3_backbones_scored': len(r3_scored_bb),
        'n_arm_backbones_any_result': by_bb,
        'n_arm_backbones_both_draws': full_bb,
        'n_incomplete': len(incomplete),
        'incomplete_designs': sorted(incomplete),
        'delta_b': len(delta_b),
        'delta_b_backbones': delta_b,
        'backbones_still_no_pass': len(still_zero),
        'backbones_still_no_pass_list': still_zero,
        'by_draw': by_draw,
        'note': ('Unfinished designs are excluded, not counted as failures. If the arm truncates, '
                 'delta_b is a LOWER BOUND on what the arm would yield at full coverage.'),
    }
    (SD / 'delta_b.json').write_text(json.dumps(out, indent=1) + '\n')

    L = ['# Delta-B — sampling-depth arm (partial = LIVE unless stated)', '',
         f"definition: {out['definition']}", '',
         f"- arm designs: **{len(recs)}**; arm backbones: **{len(arm)}**",
         f"- R3 backbones with >=1 all-rules PASS (baseline): **{len(r3_pass_bb)}** / {len(r3_all_bb)}",
         f"- **delta_b = {len(delta_b)}** backbones whose first all-rules PASS comes from this arm",
         f"- backbones still with no PASS after the arm's completed draws: **{len(still_zero)}**",
         f"- incomplete designs (excluded, not failed): **{len(incomplete)}**",
         f"- completion: {by_bb}/{len(arm)} backbones with any result, {full_bb}/{len(arm)} with both draws",
         f"- by draw: " + ', '.join(f"{k} {v['complete']}/{v['expected']} ({v['pass']} PASS)" for k, v in by_draw.items()),
         '', '## New backbones (delta_b)', '',
         '| backbone | sd1 | sd2 |', '|---|---|---|']
    def cell(bb, dr):
        s = arm[bb][dr]
        return '—' if not s else s[0]
    for bb in delta_b:
        L.append(f'| `{bb}` | {cell(bb,"sd1")} | {cell(bb,"sd2")} |')
    (SD / 'delta_b.md').write_text('\n'.join(L) + '\n')

    print(f"DELTA-B arm_designs={len(recs)} arm_bb={len(arm)} r3_pass_bb={len(r3_pass_bb)} "
          f"delta_b={len(delta_b)} still_zero={len(still_zero)} incomplete={len(incomplete)}")
    print(f"  by_draw: {by_draw}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
