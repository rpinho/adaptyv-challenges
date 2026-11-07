#!/usr/bin/env python3
"""C5 design round: design → harvest → score → report.

Usage:
    python3 scripts/c5_round.py --round N [--length-min 230] [--length-max 250] [--num-jobs 12] [--num-designs 10]

Requires: JAPANFOLD_KEY env var or ~/.config/japanfold/key
Outputs: results/japanfold_pilot/roundN_{jobs,seqs,sel_jobs}.json
"""
import argparse, csv, json, os, sys, time, urllib.request

BASE = "https://api.japanfold.aiand.com"

# 2026-11-07: these used to be four literals here, and they were the WRONG ALLELE -
# HLA-A*02:01 plus a 24aa signal peptide, against a challenge that targets A*11:01.
# One source of truth now, verified against the captured challenge page on import.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from c5_target import HLA, B2M, G12D, WT, MIN_LEN, MAX_LEN, fasta as target_fasta, verify

_bad = verify()
if _bad:
    sys.exit("c5_target.py failed verification, refusing to run a round:\n  " + "\n  ".join(_bad))

def get_key():
    k = os.environ.get("JAPANFOLD_KEY", "")
    if not k:
        p = os.path.expanduser("~/.config/japanfold/key")
        if os.path.exists(p):
            k = open(p).read().strip()
    if not k:
        sys.exit("No API key: set JAPANFOLD_KEY or ~/.config/japanfold/key")
    return k

def api(key, path, data=None, retries=3):
    for attempt in range(retries):
        try:
            headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
            if data:
                req = urllib.request.Request(f"{BASE}{path}", json.dumps(data).encode(), headers=headers)
            else:
                req = urllib.request.Request(f"{BASE}{path}", headers={"Authorization": f"Bearer {key}"})
            return json.loads(urllib.request.urlopen(req, timeout=60).read())
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(5)
            else:
                print(f"  API error: {e}", file=sys.stderr)
                return None

def make_spec(length_min, length_max, binding_chain=None, binding_range=None):
    """Target spec. binding_chain/binding_range add BoltzGen epitope conditioning
    (binding_types.binding, 1-based residues) to that target chain."""
    def ent(cid, seq):
        block = f"  - protein:\n      id: {cid}\n      sequence: {seq}"
        if binding_chain == cid and binding_range:
            block += f"\n      binding_types:\n        binding: '{binding_range}'"
        return block
    return "entities:\n" + "\n".join([
        ent("A", HLA), ent("B", B2M), ent("C", G12D),
        f"  - protein:\n      id: D\n      sequence: {length_min}..{length_max}",
    ])

def make_fasta(hla, b2m, pep, binder):
    return f">A\n{hla}\n>B\n{b2m}\n>C\n{pep}\n>D\n{binder}"

def main():
    parser = argparse.ArgumentParser(description="C5 design round")
    parser.add_argument("--round", type=int, required=True)
    parser.add_argument("--length-min", type=int, default=230)
    parser.add_argument("--length-max", type=int, default=250)
    parser.add_argument("--num-jobs", type=int, default=12)
    parser.add_argument("--num-designs", type=int, default=10)
    parser.add_argument("--outdir", default="results/japanfold_pilot")
    parser.add_argument("--tag", default="maxlong", help="job-name tag, keeps round families distinguishable")
    parser.add_argument("--binding-chain", default=None, help="target chain id to condition on (A, B or C)")
    parser.add_argument("--binding-range", default=None, help="1-based residue range on that chain, e.g. 1..10")
    args = parser.parse_args()

    # The official cap is 10-250 aa. R114 spent a round at 280-350 aa and produced the
    # lane's "best" design at 338 aa, which was never submittable. Refuse here instead.
    if args.length_min < MIN_LEN or args.length_max > MAX_LEN:
        sys.exit("refusing: %d-%daa is outside the official %d-%daa submission cap"
                 % (args.length_min, args.length_max, MIN_LEN, MAX_LEN))

    key = get_key()
    R = args.round
    outdir = args.outdir
    os.makedirs(outdir, exist_ok=True)
    letters = "abcdefghijklmnopqrstuvwxyz"

    # Phase 1: Submit design jobs
    print(f"=== R{R}: Submitting {args.num_jobs} design jobs ({args.length_min}-{args.length_max}aa) ===")
    spec = make_spec(args.length_min, args.length_max, args.binding_chain, args.binding_range)
    if args.binding_chain:
        print(f"  epitope conditioning: chain {args.binding_chain} residues {args.binding_range}")
    jobs = []
    for i in range(args.num_jobs):
        name = f"c5_r{R}_{args.tag}_{letters[i]}"
        r = api(key, "/v1/designs", {"name": name, "protocol": "protein-anything", "spec": spec, "params": {"num_designs": args.num_designs}})
        jid = r.get("id", "") if r else ""
        jobs.append({"name": name, "job_id": jid})
        if not jid:
            print(f"  FAILED: {name}")
    with open(f"{outdir}/round{R}_jobs.json", "w") as f:
        json.dump(jobs, f, indent=2)
    print(f"  {sum(1 for j in jobs if j['job_id'])}/{len(jobs)} submitted")

    # Phase 2: Poll for design completion
    print(f"=== R{R}: Waiting for designs ===")
    for poll in range(120):
        done = 0
        for j in jobs:
            if not j.get("job_id"): continue
            r = api(key, f"/v1/jobs/{j['job_id']}")
            if r and r.get("status") == "succeeded": done += 1
        print(f"  Poll {poll+1}: {done}/{len(jobs)} done")
        if done >= len(jobs): break
        time.sleep(60)

    # Phase 3: Harvest designs
    print(f"=== R{R}: Harvesting designs ===")
    designs = []
    for j in jobs:
        if not j.get("job_id"): continue
        r = api(key, f"/v1/jobs/{j['job_id']}/results")
        if not r: continue
        letter = j["name"].split("_")[-1]
        for i, d in enumerate(r.get("designs", [])):
            seq = d.get("designed_sequence", "")
            if seq and len(seq) >= 80:
                designs.append({"name": f"c5_r{R}_{letter}_r{i}", "sequence": seq, "length": len(seq)})
    with open(f"{outdir}/round{R}_seqs.csv", "w") as f:
        w = csv.writer(f)
        w.writerow(["name", "sequence", "molecule_class"])
        for d in designs:
            w.writerow([d["name"], d["sequence"], "single_chain"])
    print(f"  {len(designs)} designs harvested")

    # Phase 4: Score with OpenDDE-AbAg
    print(f"=== R{R}: Submitting {len(designs)*2} scoring jobs ===")
    tracker = []
    for i, d in enumerate(designs):
        g = api(key, "/v1/predictions", {"model": "opendde-abag", "name": f"{d['name']}_g12d", "input": make_fasta(HLA, B2M, G12D, d["sequence"])})
        w = api(key, "/v1/predictions", {"model": "opendde-abag", "name": f"{d['name']}_wt", "input": make_fasta(HLA, B2M, WT, d["sequence"])})
        tracker.append({
            "design_name": d["name"], "sequence": d["sequence"], "length": d["length"],
            "g12d_job_id": g.get("id", "") if g else "", "wt_job_id": w.get("id", "") if w else "",
            "g12d_conf": 0.0, "wt_conf": 0.0, "delta": 0.0, "composite": 0.0,
        })
        if (i + 1) % 30 == 0:
            print(f"  Submitted {i+1}/{len(designs)}")

    # Phase 5: Harvest scores
    print(f"=== R{R}: Harvesting scores ===")
    for poll in range(60):
        done = 0
        for t in tracker:
            if t["delta"] != 0: done += 1; continue
            for jk, ck in [("g12d_job_id", "g12d_conf"), ("wt_job_id", "wt_conf")]:
                jid = t.get(jk, "")
                if not jid or t.get(ck, 0) > 0: continue
                r = api(key, f"/v1/jobs/{jid}")
                if r and r.get("status") == "succeeded":
                    res = api(key, f"/v1/jobs/{jid}/results")
                    if res and res.get("rows"):
                        t[ck] = float(res["rows"][0].get("confidence_score", 0))
            if t.get("g12d_conf", 0) > 0 and t.get("wt_conf", 0) > 0:
                t["delta"] = t["g12d_conf"] - t["wt_conf"]
                t["composite"] = t["delta"] * 10 + t["g12d_conf"]
                done += 1
        print(f"  Poll {poll+1}: {done}/{len(tracker)} scored")
        if done >= len(tracker): break
        time.sleep(60)

    with open(f"{outdir}/round{R}_sel_jobs.json", "w") as f:
        json.dump(tracker, f, indent=2)

    # Phase 6: Report
    scored = [t for t in tracker if t["delta"] != 0]
    selective = [t for t in scored if t["delta"] > 0.015 and t.get("wt_conf", 1) < 0.5]
    best = max(scored, key=lambda x: x["delta"]) if scored else None

    print(f"\n=== R{R} Results ===")
    print(f"Scored: {len(scored)}/{len(tracker)}")
    print(f"Selective (strict): {len(selective)}")
    if best:
        print(f"Best: {best['design_name']} delta={best['delta']:+.3f} g12d={best['g12d_conf']:.3f} wt={best['wt_conf']:.3f}")

    # Top 5
    top5 = sorted(scored, key=lambda x: x["delta"], reverse=True)[:5]
    for i, t in enumerate(top5):
        print(f"  {i+1}. {t['design_name']}: delta={t['delta']:+.3f} g12d={t['g12d_conf']:.3f} wt={t['wt_conf']:.3f}")

if __name__ == "__main__":
    main()
