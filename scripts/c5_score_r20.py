#!/usr/bin/env python3
import json, os, urllib.request, time, csv, sys

API = "https://api.japanfold.aiand.com"
KEY = open(os.path.expanduser("~/.config/japanfold/key")).read().strip()

HLA = "MAVMAPRTLLLLLSGALALTQTWAGSHSMRYFYTSVSRPGRGEPRFISVGYVDDTQFVRFDSDAASPREEPRAPWIEQEGPEYWDRNTQIFKTNTQTDRESLRNLRGYYNQSEAGSHTLQWMHGCELGPDGRFLRGYEQFAYDGKDYIALNEDLRSWTAADTAAQITQRKWEAAREAEQRRAYLEGECVEWLRRYLENGKETLQRADPPKTHVTHHPISDHEATLRCWALGFYPAEITLTWQRDGEDQTQDTELVETRPAGDRTFQKWAAVVVPSGEEQRYTCHVQHEGLPKPLTLRWEP"
B2M = "MIQRTPKIQVYSRHPAENGKSNFLNCYVSGFHPSDIEVDLLKNGERIEKVEKHSQLRESEHGFQSRIVFHKLDGKWELLVRDCLSTLSNWLHNETFIKEHTAEAAHEEITTIHGFMTSLTQETVNIFVKNTPETREISFKKGEDIEILVEKELTLR"
G12D = "VVVGADGVGK"
WT = "VVVGAGGVGK"

BASE = os.path.expanduser("~/dev/adaptyv-c4/results/japanfold_pilot")

# Read sequences
designs = []
with open(os.path.join(BASE, "round20_seqs.csv")) as f:
    reader = csv.DictReader(f)
    for row in reader:
        designs.append((row["name"], row["sequence"]))
print(f"Read {len(designs)} designs", flush=True)

def make_yaml(binder_seq, peptide):
    return f"""sequences:
  - protein:
      id: A
      sequence: {HLA}
  - protein:
      id: B
      sequence: {B2M}
  - protein:
      id: C
      sequence: {peptide}
  - protein:
      id: D
      sequence: {binder_seq}
"""

def submit(name, yaml_str):
    payload = json.dumps({"model": "opendde-abag", "name": name, "input": yaml_str}).encode()
    for attempt in range(3):
        try:
            req = urllib.request.Request(
                f"{API}/v1/predictions", data=payload,
                headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"})
            resp = urllib.request.urlopen(req, timeout=60)
            result = json.loads(resp.read())
            return result.get("id", result.get("job_id", ""))
        except Exception as e:
            if attempt < 2:
                time.sleep(5)
            else:
                return f"error: {str(e)[:80]}"
    return "error: max retries"

# Submit scoring jobs
scoring_jobs = []
errors = 0
for i, (name, seq) in enumerate(designs):
    for variant, peptide in [("g12d", G12D), ("wt", WT)]:
        job_id = submit(f"{name}_{variant}", make_yaml(seq, peptide))
        if job_id.startswith("error"):
            errors += 1
            scoring_jobs.append({"design": name, "variant": variant, "job_id": "", "status": job_id})
        else:
            scoring_jobs.append({"design": name, "variant": variant, "job_id": job_id, "status": "queued"})
    if (i + 1) % 20 == 0:
        print(f"  ...{(i+1)*2}/{len(designs)*2} jobs...", flush=True)
        time.sleep(1)

tracker_path = os.path.join(BASE, "round20_sel_jobs.json")
json.dump(scoring_jobs, open(tracker_path, "w"), indent=2)
ok = sum(1 for j in scoring_jobs if j["status"] == "queued")
print(f"\nSubmitted {ok} scoring jobs ({errors} errors)", flush=True)

# Wait for results
print("\nWaiting 120s for results...", flush=True)
time.sleep(120)

# Harvest
print("Harvesting...", flush=True)
succeeded = 0
for j in scoring_jobs:
    job_id = j.get("job_id", "")
    if not job_id or j["status"].startswith("error"):
        continue
    try:
        req = urllib.request.Request(
            f"{API}/v1/jobs/{job_id}/results",
            headers={"Authorization": f"Bearer {KEY}"})
        resp = urllib.request.urlopen(req, timeout=15)
        data = json.loads(resp.read())
        if data.get("ready", False):
            rows = data.get("rows", [])
            if rows:
                j["confidence"] = rows[0].get("confidence_score", None)
            j["status"] = "succeeded"
            succeeded += 1
    except:
        pass

json.dump(scoring_jobs, open(tracker_path, "w"), indent=2)
still_running = sum(1 for j in scoring_jobs if j["status"] == "queued")
print(f"Harvested: {succeeded} done, {still_running} still running", flush=True)

# Compute selectivity
pair_scores = {}
for j in scoring_jobs:
    d = j.get("design", "")
    v = j.get("variant", "")
    if d and v and j.get("status") == "succeeded" and j.get("confidence") is not None:
        if d not in pair_scores:
            pair_scores[d] = {}
        pair_scores[d][v] = j["confidence"]

selective = []
for name, scores in pair_scores.items():
    if "g12d" in scores and "wt" in scores:
        delta = scores["g12d"] - scores["wt"]
        comp = delta * 10 + scores["g12d"]
        if delta > 0.015 and scores["wt"] >= 0.5:
            selective.append((name, scores["g12d"], scores["wt"], delta, comp))

selective.sort(key=lambda x: -x[4])
print(f"\nR20: {len(pair_scores)} fully scored, {len(selective)} selective", flush=True)
if selective:
    print("\nTop 10:")
    for i, (name, g12d, wt, delta, comp) in enumerate(selective[:10], 1):
        print(f"  {i}. {name}: delta={delta:+.3f} comp={comp:.3f} wt={wt:.3f}")
    above = [s for s in selective if s[3] >= 0.200]
    print(f"\nAbove delta>=+0.200: {len(above)}")
    for name, g12d, wt, delta, comp in above:
        print(f"  {name}: delta={delta:+.3f} comp={comp:.3f}")
