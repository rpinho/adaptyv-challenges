#!/usr/bin/env python3
"""Independent clash verification of the v2 robust challenger, all 20 rows, one measurement path. ($0)

The v2 artifact's clash evidence currently comes from the frozen per-design archive (five models), not
from an independent re-measurement of this membership. This re-measures every row with the independent
parser from c3_clash_audit_independent_20261025.py.

CONTROL: the same code on the SHIPPED robust challenger must reproduce its known result (20/20 rank_001
clash-clean, all 8 new seats clean). If it does not, the harness is wrong and no v2 claim is drawn.
Fail-closed: zero rows measured is a failure, not a pass.
Writes results/c3_challenger_robust_v3_20261025/clash_verify.json
"""
import csv
import importlib.util
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from c3_clash_audit_independent_20261025 import (  # noqa: E402
    parse_pdb, clashing_pairs, min_interchain_distance)

V2CSV = ROOT / 'results/c3_challenger_robust_v3_20261025/c3_challenger_all5robust_v3_20261025.csv'
SHIPPED = ROOT / 'results/c3_challenger_robust_v2_20261025/c3_challenger_all5robust_v2_20261025.csv'
OUT = ROOT / 'results/c3_challenger_robust_v3_20261025/clash_verify.json'
CUTOFF = 2.0


def backbone_of(name):
    led = json.loads((ROOT / 'results/c3_sampling_depth_v1_20261025/coverage_ledger.json').read_text())['rows']
    return {r['name']: r.get('backbone') for r in led}.get(name) or name


def seed_dir(name):
    if name.endswith('_sd1'):
        return name[:-4] + '_s1'
    if name.endswith('_sd2'):
        return name[:-4] + '_s2'
    return name


def find_pdb(name):
    import glob
    bb = backbone_of(name)
    sd = seed_dir(name)
    for key in dict.fromkeys([name, sd, bb]):
        for c in (ROOT / f'results/c3_pod_artifacts_20261025/{key}_complex.pdb',
                  ROOT / f'results/c3_round2_111_20261025/screen24/c/{key}/complex_rank_001.pdb',
                  ROOT / f'results/c3_af2m_port_20261025/portval5/portval5_out/{key}/complex_rank_001.pdb'):
            if c.exists():
                return c
    # depth-arm designs live under results/c3_sampling_depth_v1_20261025/out/<pod>/<seed_dir>/
    for key in dict.fromkeys([sd, name, bb]):
        for pat in (f'{key}_unrelaxed_rank_001*.pdb', 'complex_rank_001.pdb'):
            hits = sorted(glob.glob(str(ROOT / 'results/c3_sampling_depth_v1_20261025/out/**' /
                                         key / pat), recursive=True))
            if hits:
                return pathlib.Path(hits[0])
    return None


def measure(names):
    rows, missing = [], []
    for n in names:
        p = find_pdb(n)
        if p is None:
            missing.append(n)
            continue
        ch = parse_pdb(p)
        if len(ch) != 2:
            missing.append(f'{n}: {len(ch)} chains')
            continue
        order = sorted(ch, key=lambda c: len(ch[c]))
        binder, target = ch[order[0]], ch[order[1]]
        pairs = clashing_pairs(binder, target, CUTOFF)
        mind, ba, ta = min_interchain_distance(binder, target, 6.0)
        rows.append({'name': n, 'n_clash_pairs': len(pairs),
                     'min_dist': round(float(mind), 3),
                     'closest_binder': ba, 'closest_target': ta,
                     'clash_clean': len(pairs) == 0,
                     'worst_pair': pairs[0] if pairs else None,
                     'structure': str(p.relative_to(ROOT))})
    return rows, missing


def main():
    shipped_names = [r['name'] for r in csv.DictReader(open(SHIPPED))]
    ctl_rows, ctl_missing = measure(shipped_names)
    ctl_clean = sum(1 for r in ctl_rows if r['clash_clean'])
    control_ok = (len(ctl_rows) == 20 and ctl_clean == 20 and not ctl_missing)
    print(f'CONTROL shipped robust: {ctl_clean}/{len(ctl_rows)} clash-clean, missing={ctl_missing}')

    v2_names = [r['name'] for r in csv.DictReader(open(V2CSV))]
    rows, missing = measure(v2_names)
    clean = sum(1 for r in rows if r['clash_clean'])
    new_rows = [r for r in rows if r['name'] in set(v2_names[12:])]

    payload = {
        'artifact': 'INDEPENDENT clash re-measurement (one parser) — evidence only',
        'control_shipped_robust': {'rows': len(ctl_rows), 'clash_clean': ctl_clean,
                                   'missing': ctl_missing, 'reproduced_known_20of20': control_ok},
        'v2': {'rows_checked': len(rows), 'rows_missing_structure': missing,
               'clash_clean': clean, 'rows_flagged': len(rows) - clean,
               'new_seats_checked': len(new_rows),
               'new_seats_clean': sum(1 for r in new_rows if r['clash_clean']),
               'cutoff_A': CUTOFF, 'rows': rows},
        'note': ('rank_001 clash only. All-five-model cleanliness for the NEW seats comes from the frozen '
                 'per-design archive and is not re-derived here.'),
    }
    OUT.write_text(json.dumps(payload, indent=1) + '\n')
    print(f'v2: {clean}/{len(rows)} clash-clean (new seats {payload["v2"]["new_seats_clean"]}/{len(new_rows)}), '
          f'missing={missing}')

    if not control_ok:
        print('CONTROL FAILED — harness invalid, no v2 conclusion.')
        return 1
    if not rows:
        print('VACUOUS: 0 rows measured — FAILURE, not success.')
        return 1
    return 0


if __name__ == '__main__':
    sys.exit(main())
