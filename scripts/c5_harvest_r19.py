import json, os, urllib.request, time, csv, sys

API = "https://api.japanfold.aiand.com"
KEY = open(os.path.expanduser("~/.config/japanfold/key")).read().strip()

HLA = "MAVMAPRTLLLLLSGALALTQTWAGSHSMRYFYTSVSRPGRGEPRFISVGYVDDTQFVRFDSDAASPREEPRAPWIEQEGPEYWDRNTQIFKTNTQTDRESLRNLRGYYNQSEAGSHTLQWMHGCELGPDGRFLRGYEQFAYDGKDYIALNEDLRSWTAADTAAQITQRKWEAAREAEQRRAYLEGECVEWLRRYLENGKETLQRADPPKTHVTHHPISDHEATLRCWALGFYPAEITLTWQRDGEDQTQDTELVETRPAGDRTFQKWAAVVVPSGEEQRYTCHVQHEGLPKPLTLRWEP"
B2M = "MIQRTPKIQVYSRHPAENGKSNFLNCYVSGFHPSDIEVDLLKNGERIEKVEKHSQLRESEHGFQSRIVFHKLDGKWELLVRDCLSTLSNWLHNETFIKEHTAEAAHEEITTIHGFMTSLTQETVNIFVKNTPETREISFKKGEDIEILVEKELTLR"
G12D = "VVVGADGVGK"
WT = "VVVGAGGVGK"

BASE = os.path.expanduser("~/dev/adaptyv-c4/results/japanfold_pilot")


def api_get(url, retries=3):
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"Authorization": f"Bearer {KEY}"})
            resp = urllib.request.urlopen(req, timeout=60)
            return json.loads(resp.read())
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(5)
            else:
                raise


def api_post(url, payload, retries=3):
    for attempt in range(retries):
        try:
            data = json.dumps(payload).encode()
            req = urllib.request.Request(
                url, data=data,
                headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"}
            )
            resp = urllib.request.urlopen(req, timeout=60)
            return json.loads(resp.read())
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(5)
            else:
                raise


# Step 1-3: Harvest designs
jobs = json.load(open(os.path.join(BASE, "round19_jobs.json")))
all_designs = []
for j in jobs:
    job_id = j["job_id"]
    name_prefix = j["name"]
    data = api_get(f"{API}/v1/jobs/{job_id}/results")
    designs = data.get("designs", data.get("rows", []))
    for idx, d in enumerate(designs):
        seq = d.get("designed_sequence", d.get("sequence", ""))
        if seq:
            all_designs.append((f"{name_prefix}_r{idx}", seq))
    print(f"Harvested {name_prefix}: {len(designs)} designs")

print(f"Total harvested: {len(all_designs)}")

# Step 4: Deduplicate and save
seen = {}
unique = []
for name, seq in all_designs:
    if seq not in seen:
        seen[seq] = name
        unique.append((name, seq))

print(f"Unique: {len(unique)} (removed {len(all_designs) - len(unique)} dupes)")

csv_path = os.path.join(BASE, "round19_seqs.csv")
with open(csv_path, "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["name", "sequence"])
    for name, seq in unique:
        w.writerow([name, seq])
print(f"Saved to round19_seqs.csv")

# Step 5: Submit scoring
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


scoring_jobs = []
errors = 0
count = 0

for name, seq in unique:
    for variant, peptide in [("g12d", G12D), ("wt", WT)]:
        job_name = f"{name}_{variant}"
        yaml_str = make_yaml(seq, peptide)
        try:
            result = api_post(f"{API}/v1/predictions", {
                "model": "opendde-abag",
                "name": job_name,
                "input": yaml_str
            })
            job_id = result.get("id", result.get("job_id", ""))
            scoring_jobs.append({
                "design": name, "variant": variant,
                "job_id": job_id, "status": "queued"
            })
        except Exception as e:
            errors += 1
            scoring_jobs.append({
                "design": name, "variant": variant,
                "job_id": "", "status": f"error: {str(e)[:80]}"
            })

        count += 1
        if count % 40 == 0:
            print(f"  ...{count} scoring jobs submitted...")
            time.sleep(1)

# Step 6: Save tracker
tracker_path = os.path.join(BASE, "round19_sel_jobs.json")
json.dump(scoring_jobs, open(tracker_path, "w"), indent=2)

ok = sum(1 for j in scoring_jobs if j["status"] == "queued")
print(f"\nSubmitted {ok} scoring jobs ({errors} errors)")
print(f"Tracker saved to round19_sel_jobs.json")
