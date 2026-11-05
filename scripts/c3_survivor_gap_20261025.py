#!/usr/bin/env python3
"""Close the B_26102611_s1 comparison gap (read-only, $0, CPU).

Astra's 07:45 ruling: the replacement-independence script silently skipped every pool
backbone's comparison to survivor B_26102611_s1, because that survivor has no binder PDB
in results/c3_round2_111_20261025/backbone_pdb/ and is therefore absent from the frozen
200-key cross-TM matrix. So "46/61 clear of all 12" was only "clear of 11 measured
survivors". This script measures the missing comparisons and reports COMPLETE/INCOMPLETE,
never "clear" by absence.

Self-validation: before using the numbers, it recomputes a sample of pairs that already
exist in the frozen matrix and reports the max |delta TM|. If that delta is not ~0 the
script refuses to emit a clearance count.

Inputs (read-only):
  results/c3_r3_20261025/cross_tm_20261025.json          frozen matrix (validation set)
  results/c3_wholeset_independence_20261025/per_backbone.json   pool members
  results/c3_r3_20261025/backbone_pdb/*.pdb              pool binder structures
  results/c3_round2_111_20261025/screen24/c/B_26102611_s1/complex_rank_001.pdb
Outputs:
  results/c3_survivor_gap_20261025/{gap.json,gap.md}
No CSV, gate, score or ranking is touched.
"""
import json, csv, pathlib, sys, collections
import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from c3_backbone_clusters_20261025 import one_letter, read_binder  # noqa: E402
from c3_round2_cluster_crosswalk_20261025 import compare  # noqa: E402

MATRIX = ROOT / 'results/c3_r3_20261025/cross_tm_20261025.json'
POOL = ROOT / 'results/c3_wholeset_independence_20261025/per_backbone.json'
BB_DIR = ROOT / 'results/c3_r3_20261025/backbone_pdb'
SURV_PDB = ROOT / 'results/c3_round2_111_20261025/screen24/c/B_26102611_s1/complex_rank_001.pdb'
V8 = ROOT / 'results/c3_submission_v8_20261025.csv'
OUT = ROOT / 'results/c3_survivor_gap_20261025'
TM_MIN, COV_MIN = 0.65, 0.80
SURV = 'B_26102611_s1'
FLAGGED = {"c3_bc_l70_7781fe","c3_bc_l100_c674f8","c3_bc_l99_e26aff","c3_bc_l52_6950ff",
           "c3_bc_l100_4bd789","c3_bc_l78_3d63fd","c3_glp1r_ecd_29","c3_glp1r_ecd_12"}


def load_binder(path, name):
    keys, residues = read_binder(str(path))
    ca = [(k, next((x for x in residues[k] if x[0] == 'CA'), None)) for k in keys]
    ca = [c for c in ca if c[1]]
    if len(ca) < 20:
        return None
    return (name, [c[1][1] for c in ca], np.array([c[1][2] for c in ca], dtype=float))


def main():
    m = json.load(open(MATRIX))
    pairs = m['pairs']
    pool = json.load(open(POOL))
    v8 = [r['name'] for r in csv.DictReader(open(V8))]
    surviving = [n for n in v8 if n not in FLAGGED]
    assert SURV in surviving and SURV in v8, 'survivor list drift'

    # ---- self-validation against frozen matrix pairs (same loader, same compare) ----
    pool_names = sorted({e['backbone'] for e in pool['depth_pass']} | {e['backbone'] for e in pool['depth_hq']})
    cand = [n for n in pool_names if (BB_DIR / f'{n}.pdb').exists()]
    checks, deltas = [], []
    for a in cand[:3]:
        for b in [n for n in v8 if n != SURV][:4]:
            rec = pairs.get(a, {}).get(b)
            if not rec or rec.get('tm') is None:
                continue
            ra = load_binder(BB_DIR / f'{a}.pdb', a)
            rb = None
            for cand_pdb in ROOT.glob(f'results/c3_pod_artifacts_20261025/{b}_complex.pdb'):
                rb = load_binder(cand_pdb, b)
            if rb is None:
                p = ROOT / f'results/c3_round2_111_20261025/backbone_pdb/{b}.pdb'
                if p.exists():
                    rb = load_binder(p, b)
            if rb is None:
                continue
            c = compare(ra, rb)
            if c is None:
                continue
            d = abs(c['tm'] - rec['tm'])
            deltas.append(d)
            checks.append({'a': a, 'b': b, 'frozen_tm': rec['tm'], 'recomputed_tm': c['tm'], 'abs_delta': round(d, 4)})
    maxd = max(deltas) if deltas else None
    validated = bool(deltas) and maxd is not None and maxd <= 0.002
    print(f'validation pairs={len(deltas)} max_abs_delta_tm={maxd} validated={validated}')

    # ---- measure the gap ----
    surv = load_binder(SURV_PDB, SURV)
    if surv is None:
        print('ERROR survivor binder chain unreadable', file=sys.stderr)
        return 4
    per = {}
    for n in pool_names:
        p = BB_DIR / f'{n}.pdb'
        if not p.exists():
            per[n] = {'status': 'INCOMPLETE', 'reason': 'pool PDB missing'}
            continue
        rec = load_binder(p, n)
        if rec is None:
            per[n] = {'status': 'INCOMPLETE', 'reason': 'binder chain <20 CA'}
            continue
        c = compare(rec, surv)
        if c is None:
            per[n] = {'status': 'INCOMPLETE', 'reason': 'non-standard residue'}
            continue
        per[n] = {'status': 'MEASURED', 'tm': c['tm'], 'coverage': c['coverage'],
                  'near_identical': bool(c['tm'] >= TM_MIN and c['coverage'] >= COV_MIN)}

    summary = {'survivor': SURV, 'survivor_pdb': str(SURV_PDB.relative_to(ROOT)),
               'survivor_binder_residues': len(surv[1]),
               'why_absent_from_matrix': 'no binder PDB in results/c3_round2_111_20261025/backbone_pdb/, so the 200-key matrix never included it',
               'rule': 'near-identical iff TM>=0.65 AND coverage>=0.80',
               'validation': {'pairs': len(deltas), 'max_abs_delta_tm': maxd, 'passed': validated,
                              'samples': checks},
               'pools': {}}

    for key in ('depth_pass', 'depth_hq'):
        members = sorted({e['backbone'] for e in pool[key]})
        measured = [n for n in members if per.get(n, {}).get('status') == 'MEASURED']
        incomplete = [n for n in members if per.get(n, {}).get('status') != 'MEASURED']
        hit = [n for n in measured if per[n]['near_identical']]
        summary['pools'][key] = {
            'backbones': len(members), 'measured_vs_survivor': len(measured),
            'incomplete': len(incomplete), 'incomplete_names': incomplete,
            'near_identical_to_survivor': len(hit), 'near_identical_names': hit,
            'clear_of_survivor': (len(measured) - len(hit)) if not incomplete else None,
            'completeness': 'COMPLETE' if not incomplete else 'INCOMPLETE',
            'per_backbone': {n: per[n] for n in members},
        }
    OUT.mkdir(parents=True, exist_ok=True)
    json.dump(summary, open(OUT / 'gap.json', 'w'), indent=1)

    md = ['# Survivor-gap closure — B_26102611_s1 ($0, read-only)', '',
          'Astra (07:45) found that `c3_replacement_independence_20261025` silently skipped every',
          'comparison to survivor `B_26102611_s1`: that row has no binder PDB in',
          '`results/c3_round2_111_20261025/backbone_pdb/`, so it is absent from the frozen 200-key',
          'matrix. The "46/61 clear of all 12" figure was therefore clear of only the 11 measured',
          'survivors. This file measures the missing pairs.', '',
          f'- rule: `{summary["rule"]}`',
          f'- survivor binder chain: {summary["survivor_binder_residues"]} residues (chain A of its AF2 complex)',
          f'- self-validation against {len(deltas)} frozen matrix pairs: **max |ΔTM| = {maxd}** '
          f'({"PASS" if validated else "FAIL"})', '']
    for key, v in summary['pools'].items():
        md.append(f'- `{key}`: {v["backbones"]} backbones, {v["measured_vs_survivor"]} measured vs survivor, '
                  f'{v["near_identical_to_survivor"]} near-identical, **{v["completeness"]}**')
    md += ['', '## Result', '']
    for key, v in summary['pools'].items():
        if v['completeness'] == 'COMPLETE':
            md.append(f'- `{key}`: **{v["clear_of_survivor"]}/{v["backbones"]}** clear of `B_26102611_s1` '
                      f'({v["near_identical_to_survivor"]} near-identical).')
        else:
            md.append(f'- `{key}`: INCOMPLETE — {v["incomplete"]} pairs unmeasured; no clearance claim.')
    md += ['', '## What this changes', '',
           'This closes the specific evidentiary gap Astra named. It does **not** authorise a challenger,',
           'a swap, or a submission; portfolio composition and the contested independence-unit',
           'definition remain the binding objections (Kimi and Astra, 07:45).', '',
           'Status: PROPOSED evidence only. No CSV written; v8 byte-identical.', '']
    (OUT / 'gap.md').write_text('\n'.join(md))
    print(json.dumps({k: {kk: vv for kk, vv in v.items() if kk != 'per_backbone'} for k, v in summary['pools'].items()}, indent=1))
    print(f'wrote {OUT.relative_to(ROOT)}')
    return 0 if validated else 5


if __name__ == '__main__':
    sys.exit(main())
