#!/usr/bin/env python3
"""READ-ONLY: complete the v8 internal structural-similarity matrix.

The frozen round-1 crosswalk has 171 of 190 v8-vs-v8 pairs. The 19 missing pairs all involve
`B_26102611_s1`, which was added in v8 and has no crosswalk entry. This computes ONLY those
missing pairs with the frozen `compare()` call and the frozen rule (TM>=0.65 AND coverage>=0.80),
then reports the completed internal redundancy of v8.

Writes a separate file; never edits the frozen crosswalk or any submission artifact.
"""
import json, csv, pathlib, sys
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT/'scripts'))
from c3_round2_cluster_crosswalk_20261025 import compare, load

V8 = ROOT/'results/c3_submission_v8_20261025.csv'
R1 = ROOT/'results/c3_pod_artifacts_20261025'
R2 = ROOT/'results/c3_round2_111_20261025/backbone_pdb'
ESM = ROOT/'results/c3_round2_111_20261025/esm72'
CROSS = ROOT/'results/c3_round2_111_20261025/cluster_crosswalk_20261025.json'
OUT = ROOT/'results/c3_v8_internal_tm_20261025'
TM,COV=0.65,0.80

def structure(name):
    for d,suf in ((R1,'_complex.pdb'),(R2,'.pdb'),(ESM,'.pdb')):
        p = d/f"{name}{suf}"
        if p.exists():
            r=load(str(p),name)
            if r: return r, str(p.relative_to(ROOT))
    return None, None

def main():
    cross=json.loads(CROSS.read_text()); pairs={k:dict(v) for k,v in cross['pairs'].items()}
    v8=[r['name'] for r in csv.DictReader(open(V8))]
    computed=[]; failures=[]
    for i,a in enumerate(v8):
        for b in v8[i+1:]:
            if pairs.get(a,{}).get(b): continue
            ra,pa=structure(a); rb,pb=structure(b)
            if not ra or not rb:
                failures.append({'a':a,'b':b,'reason':'structure not loadable','a_path':pa,'b_path':pb}); continue
            c=compare(ra,rb)
            if c is None:
                failures.append({'a':a,'b':b,'reason':'non-standard residue'}); continue
            pairs.setdefault(a,{})[b]=c; pairs.setdefault(b,{})[a]=c
            computed.append({'a':a,'b':b,**c,'a_path':pa,'b_path':pb})
    def near(e): return bool(e and e.get('tm',0)>=TM and e.get('coverage',0)>=COV)
    allp=[(a,b,pairs[a][b]) for i,a in enumerate(v8) for b in v8[i+1:] if pairs.get(a,{}).get(b)]
    edges=[(a,b,e['tm']) for a,b,e in allp if near(e)]
    # connected components over v8 under the near-identical rule
    parent={v:v for v in v8}
    def find(x):
        while parent[x]!=x: parent[x]=parent[parent[x]]; x=parent[x]
        return x
    for a,b,_ in edges: parent[find(a)]=find(b)
    comps={}
    for v in v8: comps.setdefault(find(v),[]).append(v)
    tms=sorted(e['tm'] for _,_,e in allp)
    summary={"rule":f"near-identical iff TM>={TM} AND coverage>={COV}","v8_rows":len(v8),
             "pairs_expected":len(v8)*(len(v8)-1)//2,"pairs_measured":len(allp),
             "pairs_computed_now":len(computed),"failures":failures,
             "near_identical_pairs":len(edges),
             "near_identical_pair_list":[{'a':a,'b':b,'tm':round(t,4)} for a,b,t in edges],
             "structural_components":len(comps),
             "components":{k:sorted(v) for k,v in comps.items()},
             "tm_min":tms[0],"tm_median":tms[len(tms)//2],"tm_max":tms[-1],
             "note":"Completes the internal baseline so the depth-arm 24.1% overlap can be read against v8's own redundancy. Read-only; frozen crosswalk unmodified."}
    OUT.mkdir(exist_ok=True)
    (OUT/'summary.json').write_text(json.dumps(summary,indent=1))
    (OUT/'new_pairs.json').write_text(json.dumps(computed,indent=1))
    print(json.dumps({k:v for k,v in summary.items() if k not in ('components',)},indent=1))
    for a,b,t in sorted(edges,key=lambda x:-x[2])[:5]: print(f"  near: {a} ~ {b} TM={t}")
    for row in sorted(computed,key=lambda x:-x['tm'])[:5]:
        print(f"  new  {row['a']} ~ {row['b']} TM={row['tm']} cov={row['coverage']}")

if __name__=='__main__': main()
