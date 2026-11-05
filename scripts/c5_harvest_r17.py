import json, os, urllib.request, time, csv, sys

API = "https://api.japanfold.aiand.com"
KEY = open(os.path.expanduser("~/.config/japanfold/key")).read().strip()

HLA = "MAVMAPRTLLLLLSGALALTQTWAGSHSMRYFYTSVSRPGRGEPRFISVGYVDDTQFVRFDSDAASPREEPRAPWIEQEGPEYWDRNTQIFKTNTQTDRESLRNLRGYYNQSEAGSHTLQWMHGCELGPDGRFLRGYEQFAYDGKDYIALNEDLRSWTAADTAAQITQRKWEAAREAEQRRAYLEGECVEWLRRYLENGKETLQRADPPKTHVTHHPISDHEATLRCWALGFYPAEITLTWQRDGEDQTQDTELVETRPAGDRTFQKWAAVVVPSGEEQRYTCHVQHEGLPKPLTLRWEP"
B2M = "MIQRTPKIQVYSRHPAENGKSNFLNCYVSGFHPSDIEVDLLKNGERIEKVEKHSQLRESEHGFQSRIVFHKLDGKWELLVRDCLSTLSNWLHNETFIKEHTAEAAHEEITTIHGFMTSLTQETVNIFVKNTPETREISFKKGEDIEILVEKELTLR"
G12D = "VVVGADGVGK"
WT = "VVVGAGGVGK"

BASE = os.path.expanduser("~/dev/adaptyv-c4/results/japanfold_pilot")

wave_files = [
    "round17_cross_jobs.json",
    "round17_bplus_jobs.json",
    "round17_ultrashort_jobs.json",
    "round17_denovo_jobs.json",
]

# Step 1: Harvest all designs
all_designs = []
for wf in wave_files:
    path = os.path.join(BASE, wf)
    jobs = json.load(open(path))
    for j in jobs:
        job_id = j["job_id"]
        name_prefix = j["name"]
        req = urllib.request.Request(
            f"{API}/v1/jobs/{job_id}/results",
            headers={"Authorization": f"Bearer {KEY}"}
        )
        resp = urllib.request.urlopen(req, timeout=30)
        data = json.loads(resp.read())
        designs = data.get("designs", data.get("rows", []))
        for idx, d in enumerate(designs):
            seq = d.get("designed_sequence", d.get("sequence", ""))
            if not seq:
                continue
            dname = f"{name_prefix}_r{idx}"
            all_designs.append((dname, seq))
    print(f"Harvested {wf}: {len(jobs)} jobs", flush=True)

print(f"Total harvested: {len(all_designs)}", flush=True)

# Step 2: Deduplicate
seen_seqs = {}
unique = []
dupes = 0
for name, seq in all_designs:
    if seq in seen_seqs:
        dupes += 1
        continue
    seen_seqs[seq] = name
    unique.append((name, seq))

print(f"Unique designs: {len(unique)} (removed {dupes} duplicates)", flush=True)

# Step 3: Save CSV
csv_path = os.path.join(BASE, "round17_seqs.csv")
with open(csv_path, "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["name", "sequence"])
    for name, seq in unique:
        w.writerow([name, seq])
print(f"Saved {len(unique)} sequences to round17_seqs.csv", flush=True)

# Step 4: Submit scoring jobs
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

def submit_prediction(name, yaml_str):
    payload = json.dumps({
        "model": "opendde-abag",
        "name": name,
        "input": yaml_str
    }).encode()
    req = urllib.request.Request(
        f"{API}/v1/predictions",
        data=payload,
        headers={
            "Authorization": f"Bearer {KEY}",
            "Content-Type": "application/json"
        }
    )
    resp = urllib.request.urlopen(req, timeout=30)
    result = json.loads(resp.read())
    return result.get("id", result.get("job_id", ""))

scoring_jobs = []
errors = 0
batch_count = 0

for i, (name, seq) in enumerate(unique):
    for variant, peptide in [("g12d", G12D), ("wt", WT)]:
        job_name = f"{name}_{variant}"
        yaml_str = make_yaml(seq, peptide)
        try:
            job_id = submit_prediction(job_name, yaml_str)
            scoring_jobs.append({
                "design": name,
                "variant": variant,
                "job_id": job_id,
                "status": "queued"
            })
        except Exception as e:
            errors += 1
            scoring_jobs.append({
                "design": name,
                "variant": variant,
                "job_id": "",
                "status": f"error: {str(e)[:80]}"
            })

    batch_count += 2
    if batch_count % 40 == 0:
        print(f"  ...{batch_count} scoring jobs ({i+1}/{len(unique)} designs)...", flush=True)
        time.sleep(0.5)

# Step 5: Save tracker
tracker_path = os.path.join(BASE, "round17_sel_jobs.json")
json.dump(scoring_jobs, open(tracker_path, "w"), indent=2)

ok = sum(1 for j in scoring_jobs if j["status"] == "queued")
print(f"\nSubmitted {ok} scoring jobs ({errors} errors)", flush=True)
print(f"Tracker saved to round17_sel_jobs.json", flush=True)
