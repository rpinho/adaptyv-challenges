#!/usr/bin/env python3
"""Independently reproduce Astra's units-consistent comparison (design rows, not backbones).

Astra 08:1x claimed "37 depth components vs 11 v8 components" on actual eligible design
structures. This script re-derives it with the repo's own loader/compare and the frozen
thresholds, so the number is not taken on trust. READ-ONLY; writes only its own directory.
"""
import csv, glob, json, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import importlib.util
spec = importlib.util.spec_from_file_location('cw', ROOT / 'scripts/c3_round2_cluster_crosswalk_20261025.py')
cw = importlib.util.module_from_spec(spec); spec.loader.exec_module(cw)

OUT = ROOT / 'results/c3_0800_comparison_20261025'
LEDGER = ROOT / 'results/c3_sampling_depth_v1_20261025/coverage_ledger.json'
V8 = ROOT / 'results/c3_submission_v8_20261025.csv'
ELIG = ROOT / 'results/c3_v8_eligibility_20261025/eligibility.json'
TM, COV = 0.65, 0.80


def find_pdb(name):
    """Locate the archived rank-001 binder structure for a design name."""
    cands = [
        ROOT / f'results/c3_pod_artifacts_20261025/{name}_complex.pdb',
        ROOT / f'results/c3_round2_111_20261025/screen24/c/{name}/complex_rank_001.pdb',
        ROOT / f'results/c3_af2m_port_20261025/portval5/portval5_out/{name}/complex_rank_001.pdb',
    ]
    for c in cands:
        if c.exists():
            return c
    hits = glob.glob(str(ROOT / f'results/**/{name}/complex_rank_001.pdb'), recursive=True)
    return pathlib.Path(hits[0]) if hits else None


def main():
    OUT.mkdir(exist_ok=True)
    rows = json.loads(LEDGER.read_text())['rows']
    depth_pass = [r for r in rows if r.get('status') == 'PASS']
    elig = json.loads(ELIG.read_text())
    v8_pass = [r['name'] for r in elig['rows'] if r['disposition_PROPOSED'] == 'ELIGIBLE']
    v8_all = [r['name'] for r in csv.DictReader(open(V8))]

    recs, missing = {}, []
    for r in depth_pass:
        p = find_pdb(r['name'])
        if p is None:
            missing.append(r['name']); continue
        try:
            rec = cw.load(p, r['name'])
        except Exception as e:
            missing.append(f"{r['name']}: {e}"); continue
        if rec is None:
            missing.append(f"{r['name']}: <20 CA"); continue
        recs[r['name']] = rec
    v8recs = {}
    for n in v8_pass:
        p = find_pdb(n)
        if p is None:
            missing.append(f'{n} (v8)'); continue
        try:
            rec = cw.load(p, n)
        except Exception as e:
            missing.append(f'{n} (v8): {e}'); continue
        if rec is not None:
            v8recs[n] = rec

    names = sorted(set(recs) | set(v8recs))
    edges = []
    comparisons = 0
    for i, a in enumerate(names):
        for b in names[i+1:]:
            c = cw.compare(recs.get(a) or v8recs[a], recs.get(b) or v8recs[b])
            comparisons += 1
            if c and c['tm'] >= TM and c['coverage'] >= COV:
                edges.append((a, b))

    def labels(nodes):
        parent = {n: n for n in nodes}
        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]; x = parent[x]
            return x
        for a, b in edges:
            if a in parent and b in parent:
                ra, rb = find(a), find(b)
                if ra != rb: parent[rb] = ra
        return {n: find(n) for n in nodes}

    all_lab = labels(names)
    depth_lab = labels([n for n in recs])
    v8_lab = labels([n for n in v8recs])
    depth_comps = {all_lab[n] for n in recs}
    v8_comps = {all_lab[n] for n in v8recs}

    payload = {
        'method': 'design rows; archived rank-001 binder structures; repo compare(); TM>=0.65 & coverage>=0.80',
        'depth_pass_rows': len(depth_pass), 'depth_rows_measured': len(recs),
        'v8_eligible_rows': len(v8_pass), 'v8_rows_measured': len(v8recs),
        'missing_structures': missing,
        'pair_comparisons': comparisons, 'near_identical_edges': len(edges),
        'common_graph': {
            'depth_components': len(depth_comps), 'v8_components': len(v8_comps),
            'shared_components': len(depth_comps & v8_comps),
            'depth_only_components': len(depth_comps - v8_comps),
        },
        'own_graph': {'depth_components': len(set(depth_lab.values())),
                      'v8_components': len(set(v8_lab.values()))},
        'note': 'Astra reported 37 vs 11 on the common graph and 37 vs 12 on the own graph; '
                'this is an independent re-derivation, not a copy of those numbers.',
    }
    (OUT / 'designrow_verify.json').write_text(json.dumps(payload, indent=1) + '\n')
    print(json.dumps(payload, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())
