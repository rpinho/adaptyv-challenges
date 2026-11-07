#!/usr/bin/env python3
"""Rescore existing C5 designs against the CORRECT HLA-A*11:01 target.

Reads eligible designs from scratchpad/c5_eligible_seqkeyed.json, scores each
against g12d, wt, and peptide_free using opendde-abag, saves results.
"""
import json, os, sys, time, urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from c5_target import HLA, B2M, G12D, WT, MIN_LEN, MAX_LEN, fasta, verify, TARGETS

bad = verify()
if bad:
    sys.exit("c5_target.py failed verification:\n  " + "\n  ".join(bad))

BASE = "https://api.japanfold.aiand.com"
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ELIGIBLE = os.path.join(REPO, "scratchpad/c5_eligible_seqkeyed.json")
OUTFILE = os.path.join(REPO, "scratchpad/c5_rescore_a1101.json")

def get_key():
    k = os.environ.get("JAPANFOLD_KEY", "")
    if not k:
        p = os.path.expanduser("~/.config/japanfold/key")
        if os.path.exists(p):
            k = open(p).read().strip()
    if not k:
        sys.exit("No API key")
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


def main():
    key = get_key()
    designs = json.load(open(ELIGIBLE))
    designs = [d for d in designs if MIN_LEN <= d.get("len", 0) <= MAX_LEN and d.get("seq")]
    print(f"Rescoring {len(designs)} designs against HLA-A*11:01 (3 targets each = {len(designs)*3} jobs)")

    # Load existing progress if any
    tracker = []
    if os.path.exists(OUTFILE):
        tracker = json.load(open(OUTFILE))
        print(f"  Resuming: {len(tracker)} entries already tracked")

    existing = {t["name"] for t in tracker}

    # Submit scoring jobs
    submitted = 0
    for d in designs:
        if d["name"] in existing:
            continue
        entry = {
            "name": d["name"],
            "seq": d["seq"],
            "len": d["len"],
            "old_delta": d.get("delta", 0),
        }
        for target in TARGETS:
            fasta_str = fasta(d["seq"], target)
            job_name = f"{d['name']}_a1101_{target}"
            r = api(key, "/v1/predictions", {
                "model": "opendde-abag",
                "name": job_name,
                "input": fasta_str,
            })
            jid = r.get("id", "") if r else ""
            entry[f"{target}_job_id"] = jid
            entry[f"{target}_conf"] = 0.0
            if not jid:
                print(f"  FAILED to submit {job_name}", file=sys.stderr)
            submitted += 1
            if submitted % 50 == 0:
                print(f"  Submitted {submitted} jobs...")

        tracker.append(entry)

    with open(OUTFILE, "w") as f:
        json.dump(tracker, f, indent=2)
    print(f"  Total submitted: {submitted} new jobs")

    # Poll for results
    print("Polling for results...")
    for poll in range(120):
        done = 0
        pending = 0
        for t in tracker:
            scored_targets = 0
            for target in TARGETS:
                jid = t.get(f"{target}_job_id", "")
                if not jid:
                    scored_targets += 1
                    continue
                if t.get(f"{target}_conf", 0) > 0:
                    scored_targets += 1
                    continue
                r = api(key, f"/v1/jobs/{jid}")
                if r and r.get("status") == "succeeded":
                    res = api(key, f"/v1/jobs/{jid}/results")
                    if res and res.get("rows"):
                        t[f"{target}_conf"] = float(res["rows"][0].get("confidence_score", 0))
                        scored_targets += 1
                elif r and r.get("status") == "failed":
                    t[f"{target}_conf"] = -1.0
                    scored_targets += 1
                else:
                    pending += 1
            if scored_targets == len(TARGETS):
                done += 1

        # Save progress each poll
        with open(OUTFILE, "w") as f:
            json.dump(tracker, f, indent=2)

        print(f"  Poll {poll+1}: {done}/{len(tracker)} fully scored, {pending} jobs pending")
        if done >= len(tracker):
            break
        time.sleep(30)

    # Compute deltas and report
    print("\n=== RESULTS (A*11:01 correct target) ===")
    for t in tracker:
        g = t.get("g12d_conf", 0)
        w = t.get("wt_conf", 0)
        pf = t.get("peptide_free_conf", 0)
        if g > 0 and w > 0:
            t["delta"] = g - w
        else:
            t["delta"] = 0.0
        t["peptide_free_binds"] = pf > 0

    scored = [t for t in tracker if t.get("delta", 0) != 0]
    scored.sort(key=lambda x: x["delta"], reverse=True)

    print(f"Scored: {len(scored)}/{len(tracker)}")

    # Ranking per challenge rules:
    # Tier 1: measurable G12D KD, no detectable WT binding (delta > 0, and wt_conf low)
    # Tier 2: peptide-dependent (no peptide-free binding)
    # Tier 3: affinity (lowest KD = highest g12d_conf)
    best_selective = [t for t in scored if t["delta"] > 0]
    best_peptide_dep = [t for t in best_selective if not t.get("peptide_free_binds")]

    print(f"\nTop 10 by delta (mutation specificity):")
    for i, t in enumerate(scored[:10]):
        pf = t.get("peptide_free_conf", 0)
        print(f"  {i+1}. {t['name']}: delta={t['delta']:+.3f} g12d={t['g12d_conf']:.3f} wt={t['wt_conf']:.3f} pf={pf:.3f} len={t['len']} (old_delta={t.get('old_delta',0):+.3f})")

    if best_peptide_dep:
        best_peptide_dep.sort(key=lambda x: x["delta"], reverse=True)
        print(f"\nTop 5 peptide-dependent (no peptide-free binding):")
        for i, t in enumerate(best_peptide_dep[:5]):
            pf = t.get("peptide_free_conf", 0)
            print(f"  {i+1}. {t['name']}: delta={t['delta']:+.3f} g12d={t['g12d_conf']:.3f} wt={t['wt_conf']:.3f} pf={pf:.3f} len={t['len']}")

    with open(OUTFILE, "w") as f:
        json.dump(tracker, f, indent=2)
    print(f"\nSaved to {OUTFILE}")


if __name__ == "__main__":
    main()
