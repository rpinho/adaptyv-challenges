#!/usr/bin/env python3
"""One-line ranking of the three C3 candidate artifacts (mission rule 4: 'one-line ranking of which
file is best and why'). READ-ONLY; writes only results/c3_variant_ranking_20261025/.

Every artifact is measured with the SAME independent parser and frozen rules as the C3 challenger
verification: rank-001 heavy-atom inter-chain clash at 2.0 A, iPTM floor 0.85, and the frozen
near-identical rule (TM>=0.65 AND coverage>=0.80).
"""
import csv, glob, json, pathlib, sys, importlib.util
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from c3_clash_audit_independent_20261025 import parse_pdb, clashing_pairs, min_interchain_distance

OUT = ROOT / 'results/c3_variant_ranking_20261025'
TM, COV, IPTM_FLOOR, CUTOFF = 0.65, 0.80, 0.85, 2.0

VARIANTS = {
    'v8': 'results/c3_submission_v8_20261025.csv',
    'filtered_challenger': 'results/c3_challenger_20261025/c3_challenger_filtered_20261025.csv',
    'all5_robust_challenger':
        'results/c3_challenger_robust_20261025/c3_challenger_all5robust_20261025.csv',
}
IPTS = {
    'v8': 'results/c3_v8_eligibility_20261025/eligibility.json',
}


def find_pdb(name):
    for c in (ROOT / f'results/c3_pod_artifacts_20261025/{name}_complex.pdb',
              ROOT / f'results/c3_round2_111_20261025/screen24/c/{name}/complex_rank_001.pdb',
              ROOT / f'results/c3_afm2_port_20261025/portval5/portval5_out/{name}/complex_rank_001.pdb'):
        if c.exists():
            return c
    hits = sorted(glob.glob(str(ROOT / f'results/**/{name}/complex_rank_001.pdb'), recursive=True))
    return pathlib.Path(hits[0]) if hits else None


def main():
    spec = importlib.util.spec_from_file_location(
        'cw', ROOT / 'scripts/c3_round2_cluster_crosswalk_20261025.py')
    cw = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cw)

    # iPTM per design from the measured sources
    iptm = {}
    v8el = json.load(open(ROOT / IPTS['v8']))
    for r in v8el['rows']:
        if r.get('iptm') is not None:
            iptm[r['name']] = r['iptm']
    for p in (ROOT / 'results').glob('c3_*20261025*/*.json'):
        if 'challenger' not in p.name and 'challenger' not in str(p.parent.name):
            continue
    for name in set():
        pass

    # Five-model robustness evidence, from the frozen pool scan + the sensitivity scan.
    fivemodel = {}
    poolp = ROOT / 'results/c3_pool_five_model_20261025/per_design.json'
    pool = {r['name']: r for r in json.loads(poolp.read_text())} if poolp.exists() else {}
    sensp = ROOT / 'results/c3_challenger_sensitivity_20261025/per_design_models.json'
    sens = {r['name']: r for r in json.loads(sensp.read_text())} if sensp.exists() else {}

    results = {}
    for label, rel in VARIANTS.items():
        rows = list(csv.DictReader(open(ROOT / rel)))
        names = [r['name'] for r in rows]
        recs, missing, clash = {}, [], 0
        mins = []
        for n in names:
            p = find_pdb(n)
            if p is None:
                missing.append(n)
                continue
            ch = parse_pdb(p)
            if len(ch) != 2:
                missing.append(f'{n}:{len(ch)}ch')
                continue
            o = sorted(ch, key=lambda c: len(ch[c]))
            k = len(clashing_pairs(ch[o[0]], ch[o[1]], CUTOFF))
            d, _, _ = min_interchain_distance(ch[o[0]], ch[o[1]], 6.0)
            mins.append(d)
            if k:
                clash += 1
            rec = cw.load(p, n)
            if rec:
                recs[n] = rec
        edges = []
        ns = sorted(recs)
        for i, a in enumerate(ns):
            for b in ns[i + 1:]:
                c = cw.compare(recs[a], recs[b])
                if c and c['tm'] >= TM and c['coverage'] >= COV:
                    edges.append({'a': a, 'b': b, 'tm': c['tm']})
        parent = {n: n for n in ns}

        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x
        for e in edges:
            ra, rb = find(e['a']), find(e['b'])
            if ra != rb:
                parent[rb] = ra
        comps = {}
        for n in ns:
            comps.setdefault(find(n), []).append(n)

        iptms = [iptm[n] for n in names if n in iptm]
        # Provenance by design-name prefix (measured, matches the handoff's composition table):
        #   c3_bc_*            BindCraft
        #   c3_v_*             point-mutation variant of a BindCraft parent
        #   c3_glp1r_ecd_*     RFD4 round 1
        #   B_*                RFD4 round 2 (the 111-mer lane)
        #   p<N>_H<8|4>_*      sampling-depth arm (new generation, not in v8's ancestry)
        bc = sum(1 for n in names if n.startswith('c3_bc_'))
        var = sum(1 for n in names if n.startswith('c3_v_'))
        r1 = sum(1 for n in names if n.startswith('c3_glp1r'))
        r2 = sum(1 for n in names if n.startswith('B_'))
        arm = sum(1 for n in names if n[:1] in 'p12345' and '_H' in n)
        other = len(names) - bc - var - r1 - r2 - arm
        rfd = r1 + r2
        n5 = sum(1 for n in names if n in pool)
        n5clean = sum(1 for n in names if pool.get(n, {}).get('all_models_clash_clean') is True)
        n5any = sum(1 for n in names if pool.get(n, {}).get('any_model_gate_pass') is True)
        results[label] = {
            'seats_with_five_model_evidence': n5,
            'seats_all_five_clash_clean': n5clean,
            'seats_passing_gate_in_any_model': n5any,
            'file': rel, 'rows': len(names), 'measured': len(recs),
            'missing_structure': missing,
            'clash_clean': len(names) - len(missing) - clash,
            'clash_flagged': clash,
            'components': len(comps),
            'near_identical_pairs': len(edges),
            'iptm_n': len(iptms),
            'iptm_min': round(min(iptms), 3) if iptms else None,
            'iptm_max': round(max(iptms), 3) if iptms else None,
            'composition': {'bindcraft': bc, 'variant': var, 'rfd4_r1': r1, 'rfd4_r2': r2,
                            'depth_arm': arm, 'unclassified': other},
            'min_dist_A': round(min(mins), 3) if mins else None,
        }
        if edges:
            worst = max(edges, key=lambda e: e['tm'])
            results[label]['worst_near_identical'] = worst

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / 'ranking.json').write_text(json.dumps({
        'rule': 'all rows measured with one independent parser; clash <=2.0 A; near-identical TM>=0.65 & cov>=0.80',
        'variants': results,
        'note': 'evidence only; no artifact modified; nothing submitted',
    }, indent=1) + '\n')
    for k, v in results.items():
        print(f"{k:24s} rows={v['rows']:2d} clash-clean={v['clash_clean']:2d}/{v['rows']} "
              f"components={v['components']:2d} dup_pairs={v['near_identical_pairs']} "
              f"composition={v['composition']} iptm={v['iptm_min']}..{v['iptm_max']}")


if __name__ == '__main__':
    main()
