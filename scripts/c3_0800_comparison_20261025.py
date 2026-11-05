#!/usr/bin/env python3
"""Kimi's adopted 08:00 comparison rule, computed on frozen artifacts.

Rule (results/decisions/20261025-post-r3-plan-kimi.md; adopted in
20261025-post-r3-cap-conflict-astra.md):
  lexicographic on
    (1) distinct backbones with >=1 all-rules PASS, then
    (2) total all-rules PASS;
  ties keep v8.

READ-ONLY: writes only results/c3_0800_comparison_20261025/. No CSV, no gate change.

THE UNIT PROBLEM (stated up front, because it decides the answer):
  * v8's structural unit is the DESIGN ROW. Its frozen internal count is 19 components over
    20 rows (`c3_v8_internal_tm_20261025/summary.json`, 190/190 pairs).
  * The depth arm's structural unit is the BACKBONE KEY. It sampled up to 2 sequences per
    backbone; those are not independent designs.
  * The repo records THREE universes for the same question (direct / v7cc / global) and both
    consultants declined to pick one. So this script reports all three for v8 and states which
    one the depth-arm figure is computed in. It does not silently choose the flattering one.

Cross-arm overlap is computed on the frozen 200-key matrix, which is the only place v8 design
ids and depth-arm backbone ids coexist.
"""
import csv, json, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / 'results/c3_0800_comparison_20261025'
V8 = ROOT / 'results/c3_submission_v8_20261025.csv'
CROSS = ROOT / 'results/c3_r3_20261025/cross_tm_20261025.json'
V8_INTERNAL = ROOT / 'results/c3_v8_internal_tm_20261025/summary.json'
TM_NEAR, COV_NEAR = 0.65, 0.80


def near(rec):
    return bool(rec) and rec.get('tm', 0) >= TM_NEAR and rec.get('coverage', 0) >= COV_NEAR


def comps(subset, pairs):
    """Connected components among `subset`, edges only between subset members."""
    parent = {n: n for n in subset}
    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    for a in subset:
        for b, rec in pairs.get(a, {}).items():
            if b in parent and near(rec):
                ra, rb = find(a), find(b)
                if ra != rb:
                    parent[rb] = ra
    return len({find(n) for n in subset})


def comps_global(subset, pairs):
    """Components over the FULL universe, then counted for `subset` (global definition)."""
    keys = list(pairs)
    parent = {n: n for n in keys}
    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x
    for a in keys:
        for b, rec in pairs.get(a, {}).items():
            if b in parent and near(rec):
                ra, rb = find(a), find(b)
                if ra != rb:
                    parent[rb] = ra
    return len({find(n) for n in subset if n in parent})


def main():
    OUT.mkdir(exist_ok=True)
    pairs = json.loads(CROSS.read_text())['pairs']
    v8int = json.loads(V8_INTERNAL.read_text())

    v8rows = list(csv.DictReader(open(V8)))
    v8_all = [r['name'] for r in v8rows]
    v8_in = [n for n in v8_all if n in pairs]
    elig = json.loads((ROOT / 'results/c3_v8_eligibility_20261025/eligibility.json').read_text())
    v8_pass_all = [r['name'] for r in elig['rows'] if r['disposition_PROPOSED'] == 'ELIGIBLE']
    v8_pass_in = [n for n in v8_pass_all if n in pairs]

    d = json.loads((ROOT / 'results/c3_sampling_depth_v1_20261025/verify.json').read_text())
    recs = d['records']
    sd_pass = [r for r in recs if r.get('status') == 'PASS']
    sd_bbs = sorted({r['backbone'] for r in recs})
    sd_pass_bbs = sorted({r['backbone'] for r in sd_pass})

    # depth-arm components, computed within its own measured set (its own universe)
    sd_comp_all = comps(sd_bbs, pairs)
    sd_comp_pass = comps(sd_pass_bbs, pairs)
    # and under the global universe, for the one comparable figure
    sd_comp_pass_global = comps_global(sd_pass_bbs, pairs)

    # cross-arm overlap: depth PASS backbones near-identical to ANY v8 row
    sd_pass_novel = [b for b in sd_pass_bbs if not any(near(pairs.get(b, {}).get(v)) for v in v8_in)]
    sd_pass_in_v8_territory = len(sd_pass_bbs) - len(sd_pass_novel)
    # ...and the stricter test: not near-identical to any v8 row that is itself all-rules PASS
    sd_pass_novel_vs_v8pass = [b for b in sd_pass_bbs if not any(near(pairs.get(b, {}).get(v)) for v in v8_pass_in)]

    delta = json.loads((ROOT / 'results/c3_sampling_depth_v1_20261025/delta_b.json').read_text())
    delta_b = delta.get('delta_b') if isinstance(delta, dict) else None

    payload = {
        'generated': '2026-10-25 08:00 comparison (read-only)',
        'rule': ('lexicographic on (1) distinct backbones with >=1 all-rules PASS, '
                 '(2) total all-rules PASS; ties keep v8'),
        'near_identical_rule': f'TM>={TM_NEAR} AND coverage>={COV_NEAR}',
        'universe': str(CROSS.relative_to(ROOT)),
        'universe_keys': len(pairs),
        'v8_source': str(V8.relative_to(ROOT)),
        'v8_unmodified': True,
        'v8_components_by_universe': {
            'direct': 'not recomputed here',
            'v7cc': 'not recomputed here',
            'global_this_script': comps_global(v8_in, pairs),
            'own_matrix_frozen': v8int['structural_components'],
            'rows': 20, 'rows_measured_in_matrix': len(v8_in),
            'rows_not_in_matrix': [n for n in v8_all if n not in pairs],
        },
        'arms': {
            'v8': {
                'unit': 'design row',
                'rows_expected': 20, 'rows_all_rules_pass': len(v8_pass_all),
                'components_own_matrix': v8int['structural_components'],
                'components_with_pass_own_matrix': comps(v8_pass_in, pairs),
                'components_global': comps_global(v8_in, pairs),
                'components_global_with_pass': comps_global(v8_pass_in, pairs),
            },
            'c3_sampling_depth_v1': {
                'unit': 'backbone key',
                'designs_expected': d['n_expected'], 'designs_measured': len(recs),
                'backbones_measured': len(sd_bbs),
                'designs_all_rules_pass': len(sd_pass),
                'backbones_with_pass': len(sd_pass_bbs),
                'components_own_universe': sd_comp_all,
                'components_with_pass_own_universe': sd_comp_pass,
                'components_with_pass_global': sd_comp_pass_global,
                'backbones_with_pass_in_v8_territory': sd_pass_in_v8_territory,
                'backbones_with_pass_novel_vs_any_v8_row': len(sd_pass_novel),
                'backbones_with_pass_novel_vs_v8_pass_rows_only': len(sd_pass_novel_vs_v8pass),
                'delta_b_frozen': delta_b,
            },
        },
        'caveat': ('Units differ: v8 counts 19 measurable design rows; the depth arm counts 99 '
                   'backbone keys each carrying up to 2 sequences. A backbone key is not a design. '
                   'Rule 1 as written therefore favours the larger, coarser pool; both raw and '
                   'novel-after-overlap figures are reported.'),
    }
    (OUT / 'comparison.json').write_text(json.dumps(payload, indent=1) + '\n')

    v8 = payload['arms']['v8']
    sd = payload['arms']['c3_sampling_depth_v1']
    L = ['# 08:00 comparison — v8 vs the frozen depth arm (read-only)', '',
         "Kimi's adopted rule: **lexicographic on (1) distinct backbones with >=1 all-rules PASS, then",
         '(2) total all-rules PASS; ties keep v8.**', '',
         f"- near-identical rule: `{payload['near_identical_rule']}`",
         f"- universe: `{CROSS.name}` — **{len(pairs)} keys** (v8 design ids + R3/depth backbone ids)",
         '- v8 is unmodified; nothing here writes a CSV or changes a gate', '',
         '## The unit problem — read this before the table', '',
         'v8\'s structural unit is the **design row**. The depth arm\'s is the **backbone key**, and each',
         'backbone carries up to 2 sampled sequences. So "distinct backbones" is not the same object in',
         'the two arms. The repo already records three universes for v8 (direct 16→17, v7cc 18→19,',
         'global 15→16) and neither consultant chose one; all are shown.', '',
         '## Rule 1 — distinct units with >=1 all-rules PASS', '',
         '| arm | unit | measured | all-rules PASS | components (own universe) | components (global) |',
         '|---|---|---:|---:|---:|---:|',
         f"| v8 | design row | {payload['v8_components_by_universe']['rows_measured_in_matrix']}/20 | "
         f"{v8['rows_all_rules_pass']} | {v8['components_own_matrix']} | {v8['components_global']} |",
         f"| c3_sampling_depth_v1 | backbone key | {sd['backbones_measured']} | "
         f"{sd['backbones_with_pass']} | {sd['components_with_pass_own_universe']} | "
         f"{sd['components_with_pass_global']} |", '',
         '## Cross-arm overlap — the decisive quantity', '',
         f"- Depth-arm PASS backbones sitting in **v8 territory** (near-identical to any v8 row): "
         f"**{sd['backbones_with_pass_in_v8_territory']}** of {sd['backbones_with_pass']}",
         f"- Depth-arm PASS backbones with **no** near-identical v8 row: **{sd['backbones_with_pass_novel_vs_any_v8_row']}**",
         f"- Stricter: with no near-identical v8 row **that is itself all-rules PASS**: "
         f"**{sd['backbones_with_pass_novel_vs_v8_pass_rows_only']}**",
         f"- Frozen ΔB (first all-rules PASS from this arm): **{delta_b}** backbones", '',
         '## Verdict under the adopted rule', '']
    if sd['backbones_with_pass_novel_vs_any_v8_row'] > v8['components_own_matrix']:
        L += [f"- Rule 1 is evaluated first. Even counting only backbones with **no** near-identical v8",
              f"  neighbour, the arm has **{sd['backbones_with_pass_novel_vs_any_v8_row']}** units vs v8's",
              f"  **{v8['components_own_matrix']}** components. The depth arm wins rule 1; rule 2 is never",
              '  reached, so v8 does not retain the tiebreak.']
    else:
        L += [f"- Rule 1: v8 **{v8['components_own_matrix']}** components vs the arm's "
              f"**{sd['backbones_with_pass_novel_vs_any_v8_row']}** novel units. The arm does not clear",
              '  v8 after removing overlap, so **ties keep v8**.']
    L += ['', '## What this does and does not mean', '',
          '- It **does not** produce a submission file. A 172-design evidence arm cannot be uploaded as-is.',
          '- It **does** mean the depth arm is a legitimate pool to draw replacement rows from, which is',
          '  exactly the "filtered challenger" Kimi leaned toward at 07:00.',
          '- Any swap changes backbone composition and needs Ricardo; the 8 flagged v8 rows still need a',
          '  disposition either way.', '']
    (OUT / 'comparison.md').write_text('\n'.join(L) + '\n')
    print(json.dumps(payload, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())
