#!/usr/bin/env python3
"""Astra's Q3 follow-up: "backbone diversity does not guarantee epitope or binding-mode diversity;
report those too if already available."

They ARE already available -- the archived complex PDBs contain both chains. $0, read-only.

For each design in each sprint variant, compute which TARGET residues contact the binder
(any target heavy atom within 4.5 A of any binder heavy atom), then report:
  - per-portfolio: number of DISTINCT epitopes (Jaccard < 0.5 between any pair)
  - pairwise Jaccard overlap matrix summary
  - which designs share an epitope (potential redundant binding mode)
  - max distinct epitopes attainable, so "diversity" is a number, not a vibe.

No CSV, no gate change, no submission. Writes one JSON + prints a table.
"""
import json, csv, sys
from pathlib import Path
from itertools import combinations
from collections import defaultdict

ROOT = Path(__file__).resolve().parents[1]
ART = ROOT/'results/c3_pod_artifacts_20261025'
SPR = ROOT/'results/c3_sprint_8h_20261025'
OUT = SPR/'epitope_diversity.json'
CUT = 4.5

def chains_of(pdb):
    ch = {}
    for l in open(pdb):
        if l.startswith(('ATOM','HETATM')) and l[21].strip():
            ch.setdefault(l[21], 0)
            ch[l[21]] += 1
    return ch

def target_residues(pdb):
    """Return set of (chain, resseq, icode) target residues and binder atom coords."""
    ch = chains_of(pdb)
    if len(ch) < 2: return None, None, ch
    # binder = shorter chain by atom count (designs are 51-120 aa; target is GLP1R ECD ~111-220)
    order = sorted(ch.items(), key=lambda kv: kv[1])
    bch, tch = order[0][0], order[1][0]
    batoms, tres = [], set()
    for l in open(pdb):
        if not l.startswith('ATOM'): continue
        e = l[77:78].strip() or 'C'
        if e == 'H': continue
        x,y,z = float(l[30:38]), float(l[38:46]), float(l[46:54])
        if l[21] == bch:
            batoms.append((x,y,z))
        elif l[21] == tch:
            tres.add((l[21], int(l[22:26]), l[26].strip()))
    if not batoms or not tres: return None, None, ch
    # contact test
    tcoords = {}
    for l in open(pdb):
        if not l.startswith('ATOM') or l[21] != tch: continue
        e = l[77:78].strip() or 'C'
        if e == 'H': continue
        k = (l[21], int(l[22:26]), l[26].strip())
        tcoords.setdefault(k, []).append((float(l[30:38]), float(l[38:46]), float(l[46:54])))
    c2 = CUT*CUT
    contacts = set()
    for k, coords in tcoords.items():
        for ax,ay,az in coords:
            hit=False
            for bx,by,bz in batoms:
                dx=ax-bx; dy=ay-by; dz=az-bz
                if dx*dx+dy*dy+dz*dz <= c2: hit=True; break
            if hit: contacts.add(k)
    return contacts, (bch,tch), ch

variants = {}
for f in SPR.glob('c3_candidate_v9_*.csv'):
    rows=list(csv.DictReader(open(f)))
    names=[r.get('name') or r.get('design') or r.get('id') for r in rows]
    variants[f.name]=[n for n in names if n]

footprints={}
missing=[]
for vn,names in variants.items():
    for n in names:
        if n in footprints or n in missing: continue
        pdb=ART/f'{n}_complex.pdb'
        if not pdb.exists():
            alt=list(ART.glob(f'{n}*complex.pdb'))
            pdb = alt[0] if alt else None
        if pdb is None:
            # pool / depth-arm designs live in the r3 screen tree, rank_001 model
            alt=sorted(ROOT.glob(f'results/c3_r3_20261025/screen/*/{n}/*rank_001*multimer*.pdb'))
            pdb = alt[0] if alt else None
        if pdb is None:
            alt=sorted(ROOT.glob(f'results/**/{n}/*rank_001*multimer*.pdb'))
            pdb = alt[0] if alt else None
        if pdb is None: missing.append(n); continue
        try:
            c,orient,ch = target_residues(pdb)
        except Exception as e:
            missing.append(n); continue
        if not c: missing.append(n); continue
        footprints[n]=dict(epitope=sorted(f'{a}{b}{ic}' for a,b,ic in c), n_contacts=len(c),
                           orientation=orient, chain_atoms=ch)

def jac(a,b):
    A,B=set(footprints[a]['epitope']),set(footprints[b]['epitope'])
    if not A or not B: return None
    return len(A&B)/len(A|B)

out=dict(cutoff_angstrom=CUT, n_designs_with_footprint=len(footprints), missing=missing, variants={})
for vn,names in sorted(variants.items()):
    present=[n for n in names if n in footprints]
    if not present: continue
    # cluster at Jaccard >= 0.5 = same epitope
    parent={n:n for n in present}
    def find(x):
        while parent[x]!=x: parent[x]=parent[parent[x]]; x=parent[x]
        return x
    pairs=[]
    for a,b in combinations(present,2):
        j=jac(a,b)
        if j is None: continue
        pairs.append((a,b,round(j,3)))
        if j>=0.5: parent[find(a)]=find(b)
    clusters=defaultdict(list)
    for n in present: clusters[find(n)].append(n)
    # also, distinct target residues used across the portfolio
    allres=set().union(*[set(footprints[n]['epitope']) for n in present])
    pairvals=[p[2] for p in pairs]
    out['variants'][vn]=dict(
        n_rows=len(present),
        n_distinct_epitopes=len(clusters),
        cluster_sizes=sorted([len(v) for v in clusters.values()],reverse=True),
        clusters=sorted([sorted(v) for v in clusters.values()],key=lambda v:(-len(v),v[0])),
        n_unique_target_residues_touched=len(allres),
        jaccard_max=(max(pairvals) if pairvals else None),
        jaccard_median=(sorted(pairvals)[len(pairvals)//2] if pairvals else None),
        n_pairs_ge_0_5=sum(1 for v in pairvals if v>=0.5),
        redundant_pairs=[p for p in pairs if p[2]>=0.5],
    )
OUT.write_text(json.dumps(out,indent=1))

print(f"cutoff {CUT} A; {len(footprints)} designs have a complex PDB; missing {len(missing)}")
for vn,d in sorted(out['variants'].items()):
    print(f"\n{vn}")
    print(f"  rows {d['n_rows']}  distinct epitopes {d['n_distinct_epitopes']}  "
          f"cluster sizes {d['cluster_sizes']}")
    print(f"  unique target residues touched {d['n_unique_target_residues_touched']}  "
          f"Jaccard max {d['jaccard_max']} median {d['jaccard_median']}  pairs>=0.5 {d['n_pairs_ge_0_5']}")
    if d['redundant_pairs']:
        print("  redundant pairs:")
        for a,b,j in d['redundant_pairs'][:8]: print(f"    {a} ~ {b}  J={j}")
