#!/usr/bin/env python3
"""SENSITIVITY ANALYSIS ($0): does the C4 20-row ranking change under the symmetric v2 dedup rule?

The C4 ranked file was built with the repo's FROZEN near-identical predicate
(tm = tm_norm_chain2, coverage = non-gap columns per sequence -> the dead clause that reports 1.0).
Its invariance was previously checked under v1 (max-TM, forward coverage), which is itself directional.
This re-runs the full C4 selection with the fully symmetric v2 predicate and compares membership AND order.

Held fixed: sign controls, iPTM floor 0.60, L6>0, ordering (L6 desc, iPTM desc, name), 2.0 A clash gate,
chain-count gate, and --slots 20.

CONTROL: the same harness with the frozen predicate must reproduce the shipped 20 rows in order.
Output is evidence only; no CSV is written and the shipped files are read-only.
Writes results/c4_rank_v2_sensitivity_20261025/.
"""
import csv
import glob
import importlib.util
import json
import pathlib
import sys

from tmtools import tm_align

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from c3_backbone_clusters_20261025 import one_letter  # noqa: E402
from c3_clash_audit_independent_20261025 import (  # noqa: E402
    parse_pdb, clashing_pairs, min_interchain_distance)

AUDIT = ROOT / 'results/c4_selection_audit_20261025/audit.json'
LINK = ROOT / 'results/c4_linkage_audit_20261025/summary.json'
SHIPPED = ROOT / 'results/c4_ranked_20261025/c4_acid_ranked_20261025.csv'
OUT = ROOT / 'results/c4_rank_v2_sensitivity_20261025'
TM_MIN, COV_MIN = 0.65, 0.80
IPTM_FLOOR, SLOTS = 0.60, 20


def load_cw():
    spec = importlib.util.spec_from_file_location(
        'cw', ROOT / 'scripts/c3_round2_cluster_crosswalk_20261025.py')
    cw = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cw)
    return cw


def pdb_for(n):
    canonical = ROOT / f'results/c4_rebuild_20261024/remote_pdbs/{n}_complex.pdb'
    if canonical.exists():
        return canonical
    for pat in (f'results/**/{n}/complex_rank_001.pdb', f'results/**/{n}_complex.pdb'):
        h = sorted(glob.glob(str(ROOT / pat), recursive=True))
        if h:
            return pathlib.Path(h[0])
    return None


def v2_compare(rec_a, rec_b):
    """Symmetric: TM = max over both directions; coverage = max(paired)/max(len)."""
    _, na, ca = rec_a
    _, nb, cb = rec_b
    sa, sb = one_letter(na), one_letter(nb)
    if 'X' in sa + sb:
        return None
    r = tm_align(ca, cb, sa, sb)
    r2 = tm_align(cb, ca, sb, sa)
    p1 = sum(1 for u, v in zip(r.seqxA, r.seqyA) if u != '-' and v != '-')
    p2 = sum(1 for u, v in zip(r2.seqxA, r2.seqyA) if u != '-' and v != '-')
    tm = max(r.tm_norm_chain2, r2.tm_norm_chain2)
    cov = (max(p1, p2) / max(len(sa), len(sb))) if max(p1, p2) else 0.0
    return {'tm': round(float(tm), 4), 'coverage': round(float(cov), 4)}


def run(rule):
    cw = load_cw()
    audit = json.load(open(AUDIT))
    link = json.load(open(LINK))
    if not link['controls'].get('all_ok'):
        sys.exit('sign controls FAILED')

    recs = [r for r in audit['records'] if r.get('L6') is not None]
    pool = [r for r in recs
            if r.get('iptm') is not None and r['iptm'] >= IPTM_FLOOR and r['L6'] > 0]
    pool.sort(key=lambda r: (-r['L6'], -(r['iptm'] or 0), r['name']))

    chosen, rejected, measured = [], [], {}
    for r in pool:
        if len(chosen) >= SLOTS:
            break
        p = pdb_for(r['name'])
        if p is None:
            rejected.append({'name': r['name'], 'why': 'no archived structure'})
            continue
        chains = parse_pdb(p)
        if len(chains) != 2:
            rejected.append({'name': r['name'], 'why': f'{len(chains)} chains'})
            continue
        order = sorted(chains, key=lambda c: len(chains[c]))
        n_clash = len(clashing_pairs(chains[order[0]], chains[order[1]], 2.0))
        if n_clash:
            rejected.append({'name': r['name'], 'why': 'rank-001 clash', 'n_clash_pairs': n_clash})
            continue
        rec = cw.load(p, r['name'])
        if rec is None:
            rejected.append({'name': r['name'], 'why': '<20 CA'})
            continue

        dup = None
        for name, prior in measured.items():
            c = v2_compare(rec, prior) if rule == 'v2' else cw.compare(rec, prior)
            if c and c['tm'] >= TM_MIN and c['coverage'] >= COV_MIN:
                dup = {'name': name, 'tm': c['tm'], 'coverage': c['coverage']}
                break
        if dup:
            rejected.append({'name': r['name'], 'why': 'near-identical to retained', **dup})
            continue
        dmin, _, _ = min_interchain_distance(chains[order[0]], chains[order[1]], 6.0)
        chosen.append(dict(r, n_clash_pairs=0, d_min=round(float(dmin), 3)))
        measured[r['name']] = rec

    return {'chosen': [c['name'] for c in chosen],
            'chosen_detail': [{'rank': i + 1, 'name': c['name'], 'L6': c['L6'],
                               'iptm': round(c['iptm'], 3), 'd_min_A': c['d_min']}
                              for i, c in enumerate(chosen)],
            'n_rejected_diversity': len([x for x in rejected if x['why'] == 'near-identical to retained']),
            'diversity_rejections': [x for x in rejected if x['why'] == 'near-identical to retained'][:40]}


def main():
    OUT.mkdir(exist_ok=True)
    shipped = [r['name'] for r in csv.DictReader(open(SHIPPED))]
    control = run('frozen')
    control_ok = control['chosen'] == shipped
    print(f'CONTROL reproduces shipped 20 in order: {control_ok}')
    if not control_ok:
        print('  shipped:', shipped)
        print('  control:', control['chosen'])
        print('HARNESS INVALID — no v2 conclusion drawn.')
        (OUT / 'sensitivity.json').write_text(json.dumps(
            {'control_ok': False, 'shipped': shipped, 'control': control['chosen']}, indent=1) + '\n')
        return 1

    v2 = run('v2')
    added = [n for n in v2['chosen'] if n not in shipped]
    dropped = [n for n in shipped if n not in v2['chosen']]
    order_changed = v2['chosen'] != shipped
    payload = {
        'artifact': 'SENSITIVITY ANALYSIS — evidence only; shipped C4 ranked file untouched',
        'rule_frozen': 'tm_norm_chain2 + per-sequence non-gap coverage (dead clause -> 1.0)',
        'rule_v2': 'max(TM both directions) + max(paired cols)/max(len)',
        'control': {'reproduced_shipped': control_ok, 'n_shipped': len(shipped)},
        'frozen_diversity_rejections': control['n_rejected_diversity'],
        'v2_diversity_rejections': v2['n_rejected_diversity'],
        'membership_identical': set(v2['chosen']) == set(shipped),
        'order_identical': not order_changed,
        'added': added, 'dropped': dropped,
        'shipped_order': shipped,
        'v2_order': v2['chosen'],
        'v2_chosen_detail': v2['chosen_detail'],
        'v2_rejections_head': v2['diversity_rejections'],
        'note': 'No CSV written. A different membership is a different artifact needing re-derived evidence.',
    }
    (OUT / 'sensitivity.json').write_text(json.dumps(payload, indent=1) + '\n')

    print(f"v2 rows {len(v2['chosen'])}/20  membership identical: {not added and not dropped}"
          f"  order identical: {not order_changed}")
    print(f'  added  ({len(added)}): {added}')
    print(f'  dropped({len(dropped)}): {dropped}')
    print(f"  diversity rejections: frozen {control['n_rejected_diversity']} -> v2 {v2['n_rejected_diversity']}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
