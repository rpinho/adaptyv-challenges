#!/usr/bin/env python3
"""CORRECTED distinct-epitope probe.

Bug in v1: it compared each candidate against the UNION of the 18 v8 core footprints.
Jaccard(A, union) has an inflated denominator, so every design looked artificially "distinct".
The right question is: is the candidate's footprint clearly separated from the BEST-MATCHING
individual core member (max_jaccard < 0.5), not from their union?

Also runs cutoff sensitivity (4.0 / 4.5 / 5.0 A) and reports margin to the 0.5 threshold, because
a design at 0.49 is a threshold artifact, not a robust second epitope. $0, read-only.
"""
import json, csv
from pathlib import Path
from collections import defaultdict

ROOT = Path(__file__).resolve().parents[1]
SPR = ROOT / 'results/c3_sprint_8h_20261025'

def chains(pdb):
    ch = {}
    for l in open(pdb):
        if l.startswith(('ATOM','HETATM')) and l[21].strip(): ch[l[21]] = ch.get(l[21],0)+1
    return ch

def footprint(pdb, cut):
    ch = chains(pdb)
    if len(ch) < 2: return None
    order = sorted(ch.items(), key=lambda kv: kv[1])
    bch, tch = order[0][0], order[1][0]
    batoms, tcoord = [], defaultdict(list)
    for l in open(pdb):
        if not l.startswith('ATOM') or (l[77:78].strip() or 'C') == 'H': continue
        xyz = (float(l[30:38]), float(l[38:46]), float(l[46:54]))
        if l[21] == bch: batoms.append(xyz)
        elif l[21] == tch: tcoord[(l[21], int(l[22:26]), l[26].strip())].append(xyz)
    if not batoms or not tcoord: return None
    c2 = tch and cut*cut
    out = set()
    for k, pts in tcoord.items():
        for ax,ay,az in pts:
            if any((ax-bx)**2+(ay-by)**2+(az-bz)**2 <= c2 for bx,by,bz in batoms):
                out.add((l and (k[1], l[26].strip()) or (k[1],''))); break
    return out

def find(name):
    for pat in (f'results/c3_pod_artifacts_20261025/{name}_complex.pdb',
                f'results/c3_sampling_depth_v1_20261025/out/*/{name}/complex_rank_001.pdb',
                f'results/c3_r3_20261025/screen/*/{name}/*rank_001*multimer*.pdb',
                f'results/**/{name}/*rank_001*multimer*.pdb'):
        a = sorted(ROOT.glob(pat))
        if a: return a[0]
    return None

def jac(a,b):
    A,B=set(a),set(b)
    return len(A&B)/len(A|B) if A and B else None

base = json.load(open(SPR / 'epitope_baseline_v8_20261025.py'.replace('.py','') + '.json')) if False else json.load(open(OUT_JSON := SPR/'epitope_baseline_v8_20261025.json')) if False else None
# (avoid cleverness: load explicitly)
base = json.load(open(SPR/'epitope_baseline_v8.json'))
v8clusters = base['v8_baseline']['clusters']
core_names = [n for c in v8clusters if len(c)>1 for n in c]
outlier = [n for c in v8clusters if len(c)==1 for n in c]
prov = json.load(open(SPR/'challenger_variants_provenance.json'))
admits = [c['name'] for c in prov['variants']['B']['admitted']]

res = {'method': 'max Jaccard against any SINGLE core member (not the union)', 'cutoffs': {}}
for cut in (4.0, 4.5, 5.0):
    fp = {}
    for n in core_names + outlier + admits:
        p = find(n)
        fp[n] = footprint(p, cut) if p else None
    core_fps = {n: fp[n] for n in core_names if fp[n]}
    ofps = {n: fp[n] for n in outlier if fp[n]}
    rows = []
    for n in admits:
        f = fp.get(n)
        if not f: rows.append(dict(name=n, footprint=None)); continue
        js = {c: jac(f, cf) for c, cf in core_fps.items() if jac(f, cf) is not None}
        best_core = max(js.items(), key=lambda kv: kv[1]) if js else (None, None)
        jo = max((jac(f, of) for of in ofps.values() if jac(f, of) is not None), default=None)
        rows.append(dict(name=n, n_contacts=len(f),
            max_jaccard_vs_core=round(best_core[1],3) if best_core[1] is not None else None,
            closest_core_design=best_core[0],
            max_jaccard_vs_ecd29=round(jo,3) if jo is not None else None,
            distinct=(best_core[1] is not None and best_core[1] < 0.5 and (jo is None or jo < 0.5))))
    res['cutoffs'][str(cut)] = dict(designs=rows,
        n_distinct=sum(1 for r in rows if r.get('distinct')))

(SPR/'distinct_epitope_probe2.json').write_text(json.dumps(res, indent=1))
for cut, blk in res['cutoffs'].items():
    print(f"\n=== cutoff {cut} A : distinct-from-both = {blk['n_distinct']} ===")
    for r in sorted(blk['designs'], key=lambda r: (r.get('max_core') or r.get('max_core_fallback') or r.get('max_core') or 0) if False else (r.get('max_jaccard_vs_core') if r.get('max_jaccard_vs_core') is not None else 9)):
        if r.get('footprint') is None and r.get('n_contacts') is None:
            print(f"  {r['name']:32s} NO PDB"); continue
        print(f"  {r['name']:32s} contacts {r['n_contacts']:3d}  maxJ_core {r['max_jaccard_vs_core']:.3f}  "
              f"maxJ_ecd29 {'%.3f'%r['max_jaccard_vs_ecd29'] if r['max_jaccard_vs_ecd29'] is not None else ' n/a'}  "
              f"{'DISTINCT' if r['distinct'] else '-'}")
