#!/usr/bin/env python3
"""Re-harvest and score a round whose designs were lost to the >= 80aa filter."""
import argparse, json, csv, os, sys, time, urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from c5_target import HLA, B2M, G12D, WT, fasta as target_fasta, verify, TARGETS, MIN_LEN

bad = verify()
if bad:
    sys.exit("verify failed: " + "\n".join(bad))

BASE = "https://api.japanfold.aiand.com"

def get_key():
    k = os.environ.get("JAPANFOLD_KEY", "")
    if not k:
        p = os.path.expanduser("~/.config/japanfold/key")
        if os.path.exists(p): k = open(p).read().strip()
    if not k: sys.exit("No API key")
    return k

def api(key, path, data=None):
    for attempt in range(3):
        try:
            headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
            if data:
                req = urllib.request.Request(f"{BASE}{path}", json.dumps(data).encode(), headers=headers)
            else:
                req = urllib.request.Request(f"{BASE}{path}", headers={"Authorization": f"Bearer {key}"})
            return json.loads(urllib.request.urlopen(req, timeout=60).read())
        except Exception as e:
            if attempt < 2: time.sleep(3)
            else: print(f"API error: {e}", file=sys.stderr); return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--round", type=int, required=True)
    parser.add_argument("--outdir", default="results/japanfold_pilot")
    args = parser.parse_args()
    R = args.round
    key = get_key()

    jobs_file = f"{args.outdir}/round{R}_jobs.json"
    if not os.path.exists(jobs_file):
        sys.exit(f"No jobs file: {jobs_file}")
    jobs = json.load(open(jobs_file))

    designs = []
    for j in jobs:
        jid = j.get("job_id", "")
        if not jid: continue
        r = api(key, f"/v1/jobs/{jid}/results")
        if not r: continue
        letter = j["name"].split("_")[-1]
        for i, d in enumerate(r.get("designs", [])):
            seq = d.get("designed_sequence", "")
            if seq and len(seq) >= MIN_LEN:
                designs.append({"name": f"c5_r{R}_{letter}_r{i}", "sequence": seq, "length": len(seq)})

    print(f"R{R}: {len(designs)} designs harvested")
    with open(f"{args.outdir}/round{R}_seqs.csv", "w") as f:
        w = csv.writer(f)
        w.writerow(["name", "sequence", "molecule_class"])
        for d in designs:
            w.writerow([d["name"], d["sequence"], "single_chain"])

    if not designs:
        print("No designs to score")
        return

    print(f"Submitting {len(designs)*3} scoring jobs...")
    tracker = []
    for d in designs:
        entry = {"design_name": d["name"], "sequence": d["sequence"], "length": d["length"]}
        for target in TARGETS:
            r = api(key, "/v1/predictions", {"model": "opendde-abag", "name": f"{d['name']}_{target}", "input": target_fasta(d["sequence"], target)})
            entry[f"{target}_job_id"] = r.get("id", "") if r else ""
            entry[f"{target}_conf"] = 0.0
        tracker.append(entry)

    for poll in range(60):
        done = 0
        for t in tracker:
            if t.get("delta", 0) != 0: done += 1; continue
            for target in TARGETS:
                jid = t.get(f"{target}_job_id", "")
                if not jid or t.get(f"{target}_conf", 0) != 0: continue
                r = api(key, f"/v1/jobs/{jid}")
                if r and r.get("status") == "succeeded":
                    res = api(key, f"/v1/jobs/{jid}/results")
                    if res and res.get("rows"):
                        t[f"{target}_conf"] = float(res["rows"][0].get("confidence_score", 0))
                elif r and r.get("status") == "failed":
                    t[f"{target}_conf"] = -1.0
            if all(t.get(f"{tgt}_conf", 0) != 0 for tgt in TARGETS):
                g, w = t["g12d_conf"], t["wt_conf"]
                t["delta"] = g - w if g > 0 and w > 0 else 0
                t["composite"] = t["delta"] * 10 - t.get("peptide_free_conf", 0) * 2 + g if t["delta"] != 0 else 0
                done += 1
        with open(f"{args.outdir}/round{R}_sel_jobs.json", "w") as f:
            json.dump(tracker, f, indent=2)
        print(f"  Poll {poll+1}: {done}/{len(tracker)} scored", flush=True)
        if done >= len(tracker): break
        time.sleep(30)

    scored = [t for t in tracker if t.get("delta", 0) != 0]
    scored.sort(key=lambda x: x.get("composite", 0), reverse=True)
    pep_dep = [t for t in scored if t["delta"] > 0 and t.get("peptide_free_conf", 1) < 0.5]

    print(f"\n=== R{R} RESULTS ===")
    print(f"Scored: {len(scored)}/{len(tracker)}")
    print(f"Peptide-dependent (delta>0, pf<0.5): {len(pep_dep)}")
    for i, t in enumerate(scored[:10]):
        pf = t.get("peptide_free_conf", 0)
        print(f"  {i+1}. {t['design_name']}: delta={t['delta']:+.3f} g12d={t['g12d_conf']:.3f} wt={t['wt_conf']:.3f} pf={pf:.3f} len={t['length']}")


if __name__ == "__main__":
    main()
