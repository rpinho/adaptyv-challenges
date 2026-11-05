#!/usr/bin/env python3
"""R22: Full pipeline — 10 maxlong (230-250aa) design jobs, harvest, score, harvest scoring."""

import json, os, sys, time, csv, urllib.request

API = "https://api.japanfold.aiand.com"
KEY = open(os.path.expanduser("~/.config/japanfold/key")).read().strip()
BASE = os.path.expanduser("~/dev/adaptyv-c4/results/japanfold_pilot")

HLA = "MAVMAPRTLLLLLSGALALTQTWAGSHSMRYFYTSVSRPGRGEPRFISVGYVDDTQFVRFDSDAASPREEPRAPWIEQEGPEYWDRNTQIFKTNTQTDRESLRNLRGYYNQSEAGSHTLQWMHGCELGPDGRFLRGYEQFAYDGKDYIALNEDLRSWTAADTAAQITQRKWEAAREAEQRRAYLEGECVEWLRRYLENGKETLQRADPPKTHVTHHPISDHEATLRCWALGFYPAEITLTWQRDGEDQTQDTELVETRPAGDRTFQKWAAVVVPSGEEQRYTCHVQHEGLPKPLTLRWEP"
B2M = "MIQRTPKIQVYSRHPAENGKSNFLNCYVSGFHPSDIEVDLLKNGERIEKVEKHSQLRESEHGFQSRIVFHKLDGKWELLVRDCLSTLSNWLHNETFIKEHTAEAAHEEITTIHGFMTSLTQETVNIFVKNTPETREISFKKGEDIEILVEKELTLR"
G12D = "VVVGADGVGK"
WT = "VVVGAGGVGK"

def api_call(method, path, data=None):
    url = f"{API}{path}"
    if data is not None:
        payload = json.dumps(data).encode()
        req = urllib.request.Request(url, data=payload,
            headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"})
    else:
        req = urllib.request.Request(url, headers={"Authorization": f"Bearer {KEY}"})
    for attempt in range(3):
        try:
            resp = urllib.request.urlopen(req, timeout=60)
            return json.loads(resp.read())
        except Exception as e:
            if attempt < 2:
                time.sleep(5)
            else:
                raise

# Phase 1: Submit 10 design jobs
print("=== Phase 1: Submit R22 Design Jobs ===")
spec_yaml = f"""entities:
  - protein:
      id: A
      sequence: {HLA}
  - protein:
      id: B
      sequence: {B2M}
  - protein:
      id: C
      sequence: {G12D}
  - protein:
      id: D
      sequence: 230..250
"""

jobs = []
letters = "abcdefghij"
for i, letter in enumerate(letters):
    name = f"c5_r22_maxlong_{letter}"
    try:
        result = api_call("POST", "/v1/designs", {
            "name": name,
            "protocol": "protein-redesign",
            "spec": spec_yaml,
            "params": {"num_designs": 10, "budget": 10},
        })
        job_id = result.get("id") or result.get("job_id") or result.get("prediction", {}).get("id", "???")
        jobs.append({"name": name, "job_id": job_id, "status": "queued"})
        print(f"  {name}: {job_id[:16]}...")
    except Exception as e:
        print(f"  {name}: FAILED - {e}")
        jobs.append({"name": name, "job_id": "", "status": f"error: {e}"})
    time.sleep(2)

json.dump(jobs, open(os.path.join(BASE, "round22_jobs.json"), "w"), indent=2)
print(f"Submitted {sum(1 for j in jobs if j['status']=='queued')}/10 design jobs")

# Phase 2: Poll until all done
print("\n=== Phase 2: Wait for Design Jobs ===")
while True:
    done = 0
    total_designs = 0
    for j in jobs:
        if j["status"] == "succeeded":
            done += 1
            continue
        job_id = j.get("job_id", "")
        if not job_id:
            continue
        try:
            data = api_call("GET", f"/v1/jobs/{job_id}/results")
            if data.get("ready", False):
                designs = data.get("designs", data.get("rows", []))
                j["status"] = "succeeded"
                j["num_designs"] = len(designs)
                done += 1
                total_designs += len(designs)
        except:
            pass

    json.dump(jobs, open(os.path.join(BASE, "round22_jobs.json"), "w"), indent=2)
    print(f"  Design progress: {done}/{len(jobs)} done")

    if done >= len([j for j in jobs if j.get("job_id")]):
        break
    time.sleep(60)

print(f"All design jobs complete")

# Phase 3: Harvest sequences
print("\n=== Phase 3: Harvest Sequences ===")
all_designs = []
for j in jobs:
    if j["status"] != "succeeded":
        continue
    try:
        data = api_call("GET", f"/v1/jobs/{j['job_id']}/results")
        designs = data.get("designs", data.get("rows", []))
        for idx, d in enumerate(designs):
            seq = d.get("designed_sequence", d.get("sequence", ""))
            if seq:
                all_designs.append((f"{j['name']}_r{idx}", seq))
    except Exception as e:
        print(f"  Error harvesting {j['name']}: {e}")

# Dedup
seen = {}
unique = []
for name, seq in all_designs:
    if seq not in seen:
        seen[seq] = name
        unique.append((name, seq))

csv_path = os.path.join(BASE, "round22_seqs.csv")
with open(csv_path, "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["name", "sequence"])
    for name, seq in unique:
        w.writerow([name, seq])

print(f"Harvested {len(all_designs)} designs, {len(unique)} unique")

# Phase 4: Submit scoring
print("\n=== Phase 4: Submit Scoring Jobs ===")
def make_scoring_yaml(binder_seq, peptide):
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

scoring_jobs = []
errors = 0
for i, (name, seq) in enumerate(unique):
    for variant, peptide in [("g12d", G12D), ("wt", WT)]:
        yaml_str = make_scoring_yaml(seq, peptide)
        try:
            result = api_call("POST", "/v1/predictions", {
                "model": "opendde-abag",
                "name": f"{name}_{variant}",
                "input": yaml_str,
            })
            job_id = result.get("id") or result.get("job_id", "")
            scoring_jobs.append({"design": name, "variant": variant, "job_id": job_id, "status": "queued"})
        except Exception as e:
            errors += 1
            scoring_jobs.append({"design": name, "variant": variant, "job_id": "", "status": f"error: {e}"})

    if (i + 1) % 20 == 0:
        print(f"  ...{(i+1)*2} scoring jobs...")
        time.sleep(1)

json.dump(scoring_jobs, open(os.path.join(BASE, "round22_sel_jobs.json"), "w"), indent=2)
print(f"Submitted {len(scoring_jobs) - errors} scoring jobs ({errors} errors)")

# Phase 5: Wait and harvest scoring
print("\n=== Phase 5: Wait for Scoring Results ===")
time.sleep(120)  # Initial wait

for poll in range(10):
    succeeded = 0
    running = 0
    for j in scoring_jobs:
        if j["status"] == "succeeded":
            succeeded += 1
            continue
        job_id = j.get("job_id", "")
        if not job_id or "error" in j.get("status", ""):
            continue
        try:
            data = api_call("GET", f"/v1/jobs/{job_id}/results")
            if data.get("ready", False):
                rows = data.get("rows", [])
                if rows:
                    j["confidence"] = rows[0].get("confidence_score", None)
                j["status"] = "succeeded"
                succeeded += 1
            else:
                running += 1
        except:
            running += 1

    json.dump(scoring_jobs, open(os.path.join(BASE, "round22_sel_jobs.json"), "w"), indent=2)
    print(f"  Scoring: {succeeded}/{len(scoring_jobs)} done, {running} running")

    if running == 0:
        break
    time.sleep(60)

# Phase 6: Compute selectivity
print("\n=== Phase 6: Selectivity Results ===")
designs = {}
for j in scoring_jobs:
    d = j.get("design", "")
    v = j.get("variant", "")
    if d and v and j.get("status") == "succeeded" and j.get("confidence") is not None:
        if d not in designs:
            designs[d] = {}
        designs[d][v] = j["confidence"]

selective = []
for name, scores in designs.items():
    if "g12d" in scores and "wt" in scores:
        delta = scores["g12d"] - scores["wt"]
        comp = delta * 10 + scores["g12d"]
        if delta > 0.015 and scores["wt"] >= 0.5:
            selective.append((name, scores["g12d"], scores["wt"], delta, comp))

selective.sort(key=lambda x: -x[4])
print(f"R22 FINAL: {len(designs)} fully scored, {len(selective)} selective")
print()
if selective:
    print("Top 10:")
    for i, (name, g12d, wt, delta, comp) in enumerate(selective[:10], 1):
        print(f"  {i:>2}. {name}: delta={delta:+.3f} comp={comp:.3f} wt={wt:.3f}")
    above = [s for s in selective if s[3] >= 0.200]
    print(f"\nAbove delta>=+0.200: {len(above)}")
    for n, g, w, d, c in above:
        print(f"  {n}: delta={d:+.3f} comp={c:.3f}")
else:
    print("No selective designs found.")

print("\nDone.")
