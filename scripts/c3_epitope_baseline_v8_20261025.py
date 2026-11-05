#!/usr/bin/env python3
"""Orchestrator $0 audit: score the FROZEN v8 baseline with the identical epitope rule
used by scripts/c3_epitope_diversity_20261025.py, so worker B's "variant B collapses to a
single epitope" claim can be judged RELATIVE to the incumbent instead of in isolation.

Self-check: this implementation must reproduce the published variant-B numbers exactly
(rows 19, distinct 1, clusters [19], unique residues 35). If it does not, the baseline is
discarded rather than interpreted. Read-only; writes one JSON, touches no frozen file.
"""
import json, csv
from pathlib import Path
from itertools import combinations
from collections import defaultdict

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT/'results/c3_pod_artifacts_20261025'
SPR = ROOT/'results/c3_sprint_8h_20261025'
OUT = SPR/'epitope_baseline_v8.json'
CUT = 4.5

def chains_of(pdb):
    ch = {}
    for l in open(pdb):
        if l.startswith(('ATOM','HETATM')) and l[21].strip():
            ch.setdefault(l[21], 0); ch[l[21]] += 1
    return ch

def target_residues(pdb):
    ch = chains_of(pdb)
    if len(ch) < 2: return None, None
    order = sorted(ch.items(), key=lambda kv: kv[1])
    bch, tch = order[0][0], order[1][0]
    batoms, tcoords = [], defaultdict(list)
    for l in open(pdb):
        if not l.startswith('ATOM'): continue
        if (l[77:78].strip() or 'C') == 'H': continue
        xyz = (float(l[30:38]), float(l[38:46]), float(l[46:54]))
        if l[21] == bch: batoms.append(xyz)
        elif l[21] == tch: tcoords[(l[21], int(l[22:26]), l[26].strip())].append(xyz)
    if not batoms or not tcoords: return None, None
    c2 = CUT*CUT; contacts = set()
    for k, coords in tcoords.items():
        for ax,ay,az in coords:
            if any((ax-bx)**2+(ay-by)**2+(az-bz)**2 <= c2 for bx,by,bz in batoms):
                contacts.add(k); break
    return contacts, (bch, tch)

def find_pdb(n):
    p = ART/f'{n}_complex.pdb'
    if p.exists(): return p
    for pat in (f'{n}*complex.pdb',):
        alt = list(ART.glob(pat))
        if alt: return alt[0]
    for pat in (f'results/c3_r3_20261025/screen/*/{n}/*rank_001*multimer*.pdb',
                f'results/**/{n}/*rank_001*multimer*.pdb'):
        alt = sorted(ROOT.glob(pat))
        if alt: return alt[0]
    return None

def footprint(n, cache):
    if n in cache: return cache[n]
    pdb = find_pdb(n)
    if pdb is None: cache[n] = None; return None
    try: c, orient = target_residues(pdb)
    except Exception: c, orient = None, None
    cache[n] = (dict(epitope=sorted(f'{a}{b}{ic}' for a,b,ic in c)) if c else None)
    return cache[n]

def score(names, cache, label):
    present = [n for n in names if footprint(n, cache)]
    missing = [n for n in names if not footprint(n, cache)]
    parent = {n:n for n in present}
    def find(x):
        while parent[x]!=x: parent[x]=parent[parent[x]]; x=parent[x]
        return x
    def jac(a,b):
        A=set(footprint(a,cache)['epitope']); B=set(footprint(b,cache)['epitope'])
        return len(A&B)/len(A|B) if A and B else None
    pairs=[]
    for a,b in combinations(present,2):
        j=jac(a,b)
        if j is None: continue
        pairs.append((a,b,round(j,3)))
        if j>=0.5: parent[find(a)]=find(b)
    clusters=defaultdict(list)
    for n in present: clusters[find(n)].append(n)
    allres=set().union(*[set(footprint(n,cache)['epitope']) for n in present]) if present else set()
    pv=[p[2] for p in pairs]
    return dict(label=label, n_rows=len(present), missing=missing,
        n_distinct_epitopes=len(clusters),
        cluster_sizes=sorted([len(v) for v in clusters.values()],reverse=True),
        clusters=sorted([sorted(v) for v in clusters.values()],key=lambda v:(-len(v),v[0])),
        n_unique_target_residues_touched=len(allres),
        jaccard_max=(max(pv) if pv else None),
        jaccard_median=(sorted(pv)[len(pv)//2] if pv else None),
        n_pairs_ge_0_5=sum(1 for v in pv if v>=0.5))

cache={}
res={}
# --- self-check first, on the challenger B ---
bnames=[r['name'] for r in csv.DictReader(open(SPR/'c3_candidate_v9_B_20261025.csv'))]
b=score(bnames, cache, 'challenger_B')
res['challenger_B']=b
CHK=dict(n_rows=19, n_distinct_epitopes=1, cluster_sizes=[19], n_unique_target_residues_touched=35)
ok=all(b[k]==v for k,v in CHK.items())
res['self_check']=dict(expected=CHK, got={k:b[k] for k in CHK}, pass_=ok)

# --- the incumbent, frozen, read-only ---
v8names=[r['name'] for r in csv.DictReader(open(ROOT/'results/c3_submission_v8_20261025.csv'))]
res['v8_baseline']=score(v8names, cache, 'frozen_v8')
for vn in ('c3_candidate_v9_A_20261025.csv','c3_candidate_v9_A-bc_20261025.csv'):
    nm=[r['name'] for r in csv.DictReader(open(SPR/vn))]
    res[vn]=score(nm, cache, vn)

OUT.write_text(json.dumps(res,indent=1))
print(f"SELF-CHECK reproduces variant B: {'PASS' if ok else 'FAIL'}")
if not ok:
    print(json.dumps(res['self_check'],indent=1)); raise SystemExit(1)
for k in ('v8_baseline','challenger_B'):
    d=res[k]
    print(f"\n{k}: rows {d['n_rows']} distinct-epitopes {d['n_distinct_epitopes']} "
          f"cluster_sizes {d['cluster_sizes']} uniq_res {d['n_unique_target_residues_touched']} "
          f"J median {d['jaccard_median']} pairs>=0.5 {d['n_pairs_ge_0_5']}")
    if d['missing']: print(f"  no PDB for: {d['missing']}")
