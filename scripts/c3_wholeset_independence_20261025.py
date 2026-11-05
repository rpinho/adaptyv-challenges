#!/usr/bin/env python3
"""READ-ONLY: whole-set structural independence of the depth-arm pool vs v8.

Dossier requirement 5 asks for "Whole-set Jaccard / TM-coverage independence vs v8, not
per-row novelty". This computes, for the 83 all-rules PASS depth-arm designs and the 75-design
high-quality subset, how much structural territory they share with v8 as a WHOLE.

It uses the frozen cross-TM matrix (rule: near-identical iff TM>=0.65 AND coverage>=0.80).
No CSV, no gate change, no admission, no promotion. It reports numbers only.
"""
import json, csv, pathlib, statistics

ROOT = pathlib.Path(__file__).resolve().parents[1]
CROSS = ROOT/"results/c3_r3_20261025/cross_tm_20261025.json"
LEDGER = ROOT/"results/c3_sampling_depth_v1_20261025/coverage_ledger.json"
V8 = ROOT/"results/c3_submission_v8_20261025.csv"
OUT = ROOT/"results/c3_wholeset_independence_20261025"
TM, COV = 0.65, 0.80

def near(e): return bool(e and e.get("tm",0)>=TM and e.get("coverage",0)>=COV)

def main():
    cross=json.loads(CROSS.read_text()); pairs=cross["pairs"]
    led=json.loads(LEDGER.read_text()); rows=led["rows"]
    v8=[r["name"] for r in csv.DictReader(open(V8))]
    pass_rows=[r for r in rows if r["status"]=="PASS"]
    hq=[r for r in pass_rows if isinstance(r.get("iptm"),(int,float)) and r["iptm"]>=0.87
        and (r.get("binder_mean_plddt") or 0)>=85 and r.get("refold_pass")]
    def analyse(subset,label):
        by_bb={}
        for r in subset: by_bb.setdefault(r["backbone"],[]).append(r["name"])
        total=0; covered=0; per_bb=[]
        for bb,names in sorted(by_bb.items()):
            hits=[v for v in v8 if near(pairs.get(bb,{}).get(v))]
            total+=len(names); covered += len(names) if hits else 0
            per_bb.append({"backbone":bb,"sequences":len(names),"near_identical_v8":hits})
        return {"label":label,"sequences":total,"backbones":len(by_bb),
                "sequences_in_v8_occupied_territory":covered,
                "fraction_in_v8_territory":round(covered/total,4) if total else None,
                "backbones_with_no_v8_near_identical":sum(1 for x in per_bb if not x["near_identical_v8"]),
                "per_backbone":per_bb}
    a=analyse(pass_rows,"depth-arm all-rules PASS")
    b=analyse(hq,"depth-arm HQ subset (iPTM>=0.87, pLDDT>=85, refold PASS)")
    # v8 intra-set comparison: how much v8 shares with itself, as the baseline rate
    v8_cov=0
    for v in v8:
        others=[o for o in v8 if o!=v]
        if any(near(pairs.get(v,{}).get(o)) for o in others): v8_cov+=1
    # distribution of best TM to v8 for depth pass designs
    best=[]
    for r in pass_rows:
        tm=max([pairs.get(r["backbone"],{}).get(v,{}).get("tm",0) for v in v8]+[0])
        best.append((r["name"],round(tm,3)))
    best.sort(key=lambda x:-x[1])
    summary={"rule":f"near-identical iff TM>={TM} AND coverage>={COV} (frozen)",
             "depth_pass":{k:v for k,v in a.items() if k!="per_backbone"},
             "depth_hq":{k:v for k,v in b.items() if k!="per_backbone"},
             "v8_rows_sharing_territory_within_v8":v8_cov,"v8_rows":len(v8),
             "note":"Coverage is 1.0 for every cross-TM pair in this matrix, so the near-identical rule reduces to TM>=0.65. Reported as measured, not assumed."}
    OUT.mkdir(parents=True,exist_ok=True)
    (OUT/"summary.json").write_text(json.dumps(summary,indent=1))
    (OUT/"per_backbone.json").write_text(json.dumps({"depth_pass":a["per_backbone"],"depth_hq":b["per_backbone"]},indent=1))
    print(json.dumps(summary,indent=1))
    print("\ntop 10 depth PASS by best TM to any v8 row:")
    for n,t in best[:10]: print(f"  {n:<32} TM={t}")

if __name__=="__main__": main()
