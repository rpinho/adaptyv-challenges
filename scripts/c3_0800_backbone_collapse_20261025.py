#!/usr/bin/env python3
"""Kimi's backbone-collapsed replay, done at DESIGN-ROW level ($0, CPU only).

Why design rows and not the cached matrix: the frozen 200-key cross-TM matrix is BACKBONE-keyed
for the depth arm (design names like `p1_H8_52_64_910001_sd1` are not keys). So "collapsing to one
sequence per backbone" is a no-op in that matrix — it cannot answer the best-of-two question.
The question is only meaningful on actual design structures, so this script clusters archived
rank-001 binder structures exactly as Astra's check did, then collapses.

Method, fixed before looking at results:
  * PASS label per design from the frozen coverage ledger.
  * "Expanded" = all 83 PASS design structures.
  * "Collapsed" = exactly ONE PASS design per passing backbone, chosen structure-blind by three
    deterministic rules: lowest design name; highest iPTM; lowest iPTM. Reported as a band.
  * Components via the repo's own loader/compare, TM>=0.65 AND coverage>=0.80, clustered within
    each arm (own graph) and on the union (common graph).

READ-ONLY. Writes only results/c3_0800_comparison_20261025/.
"""
import csv, glob, json, pathlib, sys, importlib.util

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
spec = importlib.util.spec_from_file_location('cw', ROOT / 'scripts/c3_round2_cluster_crosswalk_20261025.py')
cw = importlib.util.module_from_spec(spec); spec.loader.exec_module(cw)

OUT = ROOT / 'results/c3_0800_comparison_20261025'
LEDGER = ROOT / 'results/c3_sampling_depth_v1_20261025/coverage_ledger.json'
V8 = ROOT / 'results/c3_submission_v8_20261025.csv'
ELIG = ROOT / 'results/c3_v8_eligibility_20261025/eligibility.json'
TM, COV = 0.65, 0.80


def find_pdb(name):
    for c in (ROOT / f'results/c3_pod_artifacts_20261025/{name}_complex.pdb',
              ROOT / f'results/c3_round2_111_20261025/screen24/c/{name}/complex_rank_001.pdb',
              ROOT / f'results/c3_af2m_port_20261025/portval5/portval5_out/{name}/complex_rank_001.pdb'):
        if c.exists():
            return c
    hits = glob.glob(str(ROOT / f'results/**/{name}/complex_rank_001.pdb'), recursive=True)
    return pathlib.Path(hits[0]) if hits else None


def labels(nodes, edges):
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


def main():
    rows = json.loads(LEDGER.read_text())['rows']
    elig = json.loads(ELIG.read_text())
    v8_all = [r['name'] for r in csv.DictReader(open(V8))]
    v8_pass = [r['name'] for r in elig['rows'] if r['disposition_PROPOSED'] == 'ELIGIBLE']
    pass_rows = [r for r in rows if r.get('status') == 'PASS']

    recs = {}
    for r in pass_rows:
        p = find_pdb(r['name'])
        if p is None: continue
        rec = cw.load(p, r['name'])
        if rec is not None: recs[r['name']] = rec
    v8recs = {}
    for n in v8_pass:
        p = find_pdb(n)
        if p is not None:
            rec = cw.load(p, n)
            if rec is not None: v8recs[n] = rec

    names = sorted(set(recs) | set(v8recs))
    edges = []
    for i, a in enumerate(names):
        for b in names[i+1:]:
            c = cw.compare(recs.get(a) or v8recs[a], recs.get(b) or v8recs[b])
            if c and c['tm'] >= TM and c['coverage'] >= COV:
                edges.append((a, b))

    lab_all = labels(names, edges)
    depth_comps = {lab_all[n] for n in recs}
    v8_comps = {lab_all[n] for n in v8recs}
    shared = depth_comps & v8_comps

    by_bb = {}
    for r in pass_rows:
        if r['name'] in recs:
            by_bb.setdefault(r['backbone'], []).append(r)
    dist = {}
    for b, rs in by_bb.items(): dist[len(rs)] = dist.get(len(rs), 0) + 1

    def pick(rule):
        out = []
        for b, rs in by_bb.items():
            if rule == 'name': out.append(sorted(r['name'] for r in rs)[0])
            elif rule == 'iptm_high': out.append(max(rs, key=lambda r: (r.get('iptm') or -1, r['name']))['name'])
            elif rule == 'iptm_low': out.append(min(rs, key=lambda r: (r.get('iptm') or 99, r['name']))['name'])
        return out

    variants = {r: pick(r) for r in ('name', 'iptm_high', 'iptm_low')}
    vc = {}
    for rule, ns in variants.items():
        comps = {lab_all[n] for n in ns if n in lab_all}
        vc[rule] = {'designs': len(ns), 'components_own': len(set(labels(ns, edges).values())),
                    'components_common': len(comps), 'shared_with_v8': len(comps & v8_comps)}

    payload = {
        'method': 'design rows; archived rank-001 binder structures; repo compare(); TM>=0.65 & coverage>=0.80',
        'note_on_cached_matrix': 'the frozen 200-key cross-TM matrix is backbone-keyed for the depth arm, '
                                  'so a collapse there is a no-op; this replay uses actual structures instead',
        'pass_sequences_per_backbone': {'zero': len({r["backbone"] for r in rows}) - len(by_bb),
                                        'one': dist.get(1, 0), 'two': dist.get(2, 0),
                                        'passing_backbones': len(by_bb),
                                        'total_backbones': len({r["backbone"] for r in rows})},
        'expanded': {'designs': len(recs), 'components_common': len(depth_comps),
                     'components_own': len(set(labels(list(recs), edges).values()))},
        'collapsed_one_per_backbone': vc,
        'collapsed_band_common': [min(x['components_common'] for x in vc.values()),
                                  max(x['components_common'] for x in vc.values())],
        'v8': {'designs': len(v8recs), 'components_common': len(v8_comps),
               'components_own': len(set(labels(list(v8recs), edges).values()))},
        'pair_comparisons': len(names) * (len(names) - 1) // 2,
        'near_identical_edges': len(edges),
    }
    lo = payload['collapsed_band_common'][0]
    v8c = payload['v8']['components_common']
    payload['interpretation'] = (
        f'Collapsed to one PASS sequence per backbone, the arm still has {lo}-'
        f'{payload["collapsed_band_common"][1]} components vs v8\'s {v8c}. '
        + ('The rule-1 lead is NOT a best-of-two artifact.' if lo > v8c else
           'The lead DOES depend on retaining both draws; rule 1 must be re-specified.'))
    (OUT / 'backbone_collapse.json').write_text(json.dumps(payload, indent=1) + '\n')
    print(json.dumps(payload, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())
