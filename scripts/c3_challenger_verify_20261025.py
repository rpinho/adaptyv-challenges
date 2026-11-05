#!/usr/bin/env python3
"""Independence + composition verification of the assembled challenger, on actual structures.

The frozen 200-key matrix cannot cluster v8 design IDs against depth-arm design IDs (different
key namespaces), so the assembled set's independence is measured here directly from the archived
rank-001 binder structures with the repo's own compare(), frozen thresholds, and component counting.
READ-ONLY; writes only results/c3_challenger_20261025/.
"""
import csv, glob, json, pathlib, sys, importlib.util, statistics

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
spec = importlib.util.spec_from_file_location('cw', ROOT / 'scripts/c3_round2_cluster_crosswalk_20261025.py')
cw = importlib.util.module_from_spec(spec); spec.loader.exec_module(cw)

OUT = ROOT / 'results/c3_challenger_20261025'
CHAL = OUT / 'c3_challenger_filtered_20261025.csv'
V8 = ROOT / 'results/c3_submission_v8_20261025.csv'
TM, COV = 0.65, 0.80


def find_pdb(name):
    for c in (ROOT / f'results/c3_pod_artifacts_20261025/{name}_complex.pdb',
              ROOT / f'results/c3_round2_111_20261025/screen24/c/{name}/complex_rank_001.pdb',
              ROOT / f'results/c3_af2m_port_20261025/portval5/portval5_out/{name}/complex_rank_001.pdb'):
        if c.exists():
            return c
    hits = glob.glob(str(ROOT / f'results/**/{name}/complex_rank_001.pdb'), recursive=True)
    return pathlib.Path(hits[0]) if hits else None


def cluster(names):
    recs = {}
    missing = []
    for n in names:
        p = find_pdb(n)
        if p is None:
            missing.append(n); continue
        r = cw.load(p, n)
        if r is None:
            missing.append(f'{n}:<20CA'); continue
        recs[n] = r
    edges = []
    ns = sorted(recs)
    for i, a in enumerate(ns):
        for b in ns[i+1:]:
            c = cw.compare(recs[a], recs[b])
            if c and c['tm'] >= TM and c['coverage'] >= COV:
                edges.append({'a': a, 'b': b, 'tm': c['tm']})
    parent = {n: n for n in ns}
    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]; x = parent[x]
        return x
    for e in edges:
        ra, rb = find(e['a']), find(e['b'])
        if ra != rb: parent[rb] = ra
    comps = {}
    for n in ns:
        comps.setdefault(find(n), []).append(n)
    return {'n_rows': len(names), 'n_measured': len(recs), 'missing': missing,
            'components': len(comps), 'near_identical_pairs': edges,
            'component_members': sorted(comps.values(), key=lambda x: -len(x))}


def main():
    chal = [r['name'] for r in csv.DictReader(open(CHAL))]
    v8 = [r['name'] for r in csv.DictReader(open(V8))]
    ch = cluster(chal)
    base = cluster(v8)
    payload = {
        'challenger_rows': len(chal), 'v8_rows': len(v8),
        'challenger': {k: ch[k] for k in ('n_measured', 'missing', 'components', 'component_members')},
        'v8': {k: base[k] for k in ('n_measured', 'missing', 'components', 'component_members')},
        'near_identical_pairs_challenger': ch['near_identical_pairs'],
        'verdict': None,
    }
    payload['verdict'] = (
        f"challenger {ch['components']} components over {ch['n_measured']} measured rows vs v8's "
        f"{base['components']} over {base['n_measured']}")
    (OUT / 'verify.json').write_text(json.dumps(payload, indent=1) + '\n')
    print(json.dumps({k: v for k, v in payload.items() if 'pairs' not in k}, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())
