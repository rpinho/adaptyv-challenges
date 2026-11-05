#!/usr/bin/env python3
"""Round 16: Big 3-wave BoltzGen campaign.

Wave 1: Redesign structural winners (high Boltz2 iptm)
Wave 2: Redesign delta champions (high selectivity)
Wave 3: Fresh scaffolds (unexplored length ranges)
"""

import json
import os
import sys
import time
import urllib.request

API = "https://api.japanfold.aiand.com"
KEY = open(os.path.expanduser("~/.config/japanfold/key")).read().strip()

HLA = "MAVMAPRTLLLLLSGALALTQTWAGSHSMRYFYTSVSRPGRGEPRFISVGYVDDTQFVRFDSDAASPREEPRAPWIEQEGPEYWDRNTQIFKTNTQTDRESLRNLRGYYNQSEAGSHTLQWMHGCELGPDGRFLRGYEQFAYDGKDYIALNEDLRSWTAADTAAQITQRKWEAAREAEQRRAYLEGECVEWLRRYLENGKETLQRADPPKTHVTHHPISDHEATLRCWALGFYPAEITLTWQRDGEDQTQDTELVETRPAGDRTFQKWAAVVVPSGEEQRYTCHVQHEGLPKPLTLRWEP"
B2M = "MIQRTPKIQVYSRHPAENGKSNFLNCYVSGFHPSDIEVDLLKNGERIEKVEKHSQLRESEHGFQSRIVFHKLDGKWELLVRDCLSTLSNWLHNETFIKEHTAEAAHEEITTIHGFMTSLTQETVNIFVKNTPETREISFKKGEDIEILVEKELTLR"
G12D = "VVVGADGVGK"

RESULTS_DIR = os.path.expanduser("~/dev/adaptyv-c4/results/japanfold_pilot")

# Read v16 sequences
V16_SEQS = {}
with open(os.path.expanduser("~/dev/adaptyv-c4/results/c5_submission_v16_20261101.csv")) as f:
    for line in f:
        parts = line.strip().split(",")
        if len(parts) >= 2 and parts[0] != "name":
            V16_SEQS[parts[0]] = parts[1]


def make_spec(length_min, length_max):
    """YAML spec for BoltzGen design with a binder length range."""
    return f"""entities:
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
      sequence: {length_min}..{length_max}
"""


def submit_design(name, spec, num_designs=10, budget=10):
    """Submit a BoltzGen design job."""
    payload = json.dumps({
        "name": name,
        "protocol": "protein-redesign",
        "spec": spec,
        "params": {
            "num_designs": num_designs,
            "budget": budget,
        },
    }).encode()

    req = urllib.request.Request(
        f"{API}/v1/designs",
        data=payload,
        headers={
            "Authorization": f"Bearer {KEY}",
            "Content-Type": "application/json",
        },
    )

    for attempt in range(3):
        try:
            resp = urllib.request.urlopen(req, timeout=30)
            data = json.loads(resp.read())
            job_id = data.get("id") or data.get("job_id") or data.get("prediction", {}).get("id", "???")
            return job_id
        except Exception as e:
            if attempt < 2:
                print(f"  Retry {attempt+1} for {name}: {e}")
                time.sleep(3)
            else:
                print(f"  FAILED {name}: {e}")
                return None


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "all"

    # Wave 1: Structural winners (high iptm)
    wave1_parents = [
        ("groove_r2", "c5_r10_rfd4_groove_s42_d2_r2"),       # iptm=0.900
        ("denovo_r5", "c5_r11_r8_denovo_c6_c7_29_s1_gs1.466_r4_r5"),  # iptm=0.873
        ("d6ctx_r5", "c5_r4_rfd4_d6ctx_s5_d0_r5"),           # iptm=0.854
        ("nanobody_r1", "c5_r10_r9_nanobody_s1_r1_r4_r1"),   # iptm=0.808
        ("nterm_r1", "c5_r7_rfd4_nterm_s7_d1_r1"),            # iptm=0.803
    ]

    # Wave 2: Delta champions (high selectivity)
    wave2_parents = [
        ("alt_test", "c5_r13_alt_test_d3_r7_r0"),             # delta=+0.223
        ("test_d3", "c5_r11_rfd4_test_d3_r8"),                # delta=+0.214
        ("groove_r7", "c5_r10_rfd4_groove_s42_d2_r7"),         # delta=+0.205
    ]

    # Wave 3: Fresh scaffolds (unexplored length ranges)
    wave3_specs = [
        ("vshort_a", 40, 60),
        ("vshort_b", 40, 60),
        ("vshort_c", 40, 60),
        ("midlong_a", 130, 170),
        ("midlong_b", 130, 170),
        ("midlong_c", 130, 170),
        ("vlong_a", 180, 250),
        ("vlong_b", 180, 250),
    ]

    all_jobs = {"wave1_struct": [], "wave2_delta": [], "wave3_fresh": []}

    # ---- Wave 1: Redesign structural winners at similar length ----
    if mode in ("all", "wave1"):
        print("=== Wave 1: Structural Winners ===")
        for short_name, parent_name in wave1_parents:
            seq = V16_SEQS.get(parent_name)
            if not seq:
                print(f"  SKIP {parent_name}: sequence not in v16")
                continue
            L = len(seq)
            lmin, lmax = max(L - 10, 30), L + 10
            job_name = f"c5_r16_struct_{short_name}"
            spec = make_spec(lmin, lmax)
            print(f"  Submitting {job_name} (parent={parent_name}, range={lmin}-{lmax})...")
            job_id = submit_design(job_name, spec, num_designs=10, budget=10)
            if job_id:
                all_jobs["wave1_struct"].append({
                    "name": job_name,
                    "parent": parent_name,
                    "job_id": job_id,
                    "status": "queued",
                    "length_range": f"{lmin}-{lmax}",
                })
                print(f"    -> {job_id}")
            time.sleep(1)

    # ---- Wave 2: Redesign delta champions at similar length ----
    if mode in ("all", "wave2"):
        print("\n=== Wave 2: Delta Champions ===")
        for short_name, parent_name in wave2_parents:
            seq = V16_SEQS.get(parent_name)
            if not seq:
                print(f"  SKIP {parent_name}: sequence not in v16")
                continue
            L = len(seq)
            lmin, lmax = max(L - 10, 30), L + 10
            job_name = f"c5_r16_delta_{short_name}"
            spec = make_spec(lmin, lmax)
            print(f"  Submitting {job_name} (parent={parent_name}, range={lmin}-{lmax})...")
            job_id = submit_design(job_name, spec, num_designs=10, budget=10)
            if job_id:
                all_jobs["wave2_delta"].append({
                    "name": job_name,
                    "parent": parent_name,
                    "job_id": job_id,
                    "status": "queued",
                    "length_range": f"{lmin}-{lmax}",
                })
                print(f"    -> {job_id}")
            time.sleep(1)

    # ---- Wave 3: Fresh scaffolds at unexplored lengths ----
    if mode in ("all", "wave3"):
        print("\n=== Wave 3: Fresh Scaffolds ===")
        for short_name, lmin, lmax in wave3_specs:
            job_name = f"c5_r16_fresh_{short_name}"
            spec = make_spec(lmin, lmax)
            print(f"  Submitting {job_name} (length={lmin}-{lmax})...")
            job_id = submit_design(job_name, spec, num_designs=10, budget=10)
            if job_id:
                all_jobs["wave3_fresh"].append({
                    "name": job_name,
                    "job_id": job_id,
                    "status": "queued",
                    "length_range": f"{lmin}-{lmax}",
                })
                print(f"    -> {job_id}")
            time.sleep(1)

    # Save trackers
    for wave_name, jobs in all_jobs.items():
        if jobs:
            path = os.path.join(RESULTS_DIR, f"round16_{wave_name}_jobs.json")
            json.dump(jobs, open(path, "w"), indent=2)
            print(f"\nSaved {len(jobs)} jobs to {path}")

    # Summary
    total = sum(len(j) for j in all_jobs.values())
    print(f"\n{'='*60}")
    print(f"TOTAL: {total} jobs submitted across 3 waves")
    print(f"  Wave 1 (structural): {len(all_jobs['wave1_struct'])} jobs")
    print(f"  Wave 2 (delta):      {len(all_jobs['wave2_delta'])} jobs")
    print(f"  Wave 3 (fresh):      {len(all_jobs['wave3_fresh'])} jobs")
    print(f"Expected designs: ~{total * 10}")
    print(f"Estimated cost: ~${total * 0.50:.0f}-${total * 2:.0f}")


if __name__ == "__main__":
    main()
