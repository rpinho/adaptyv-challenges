#!/usr/bin/env python3
"""E3 cohort admission: verify each generated 111-mer complex, stage MPNN-ready PDBs.

Same construct/geometry/structural checks as round 2 (imported, not reimplemented), so the
E3 cohort is admitted under the identical pre-registered rules. Writes a NEW file
(results/c3_e3_111_20261025/admission.json); never touches round-2 or round-1 evidence.

Verified RFD4 quirk: output CIFs contain hydrogen rows with NaN coords and one unplaced
F111:OXT; construct.verify handles both and still fails closed on a real wrong-length CIF.
"""
import argparse
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import c3_round2_construct_20261025 as construct  # noqa: E402
import c3_refold_check_20261025 as checks  # noqa: E402

E3 = ROOT / "results/c3_e3_20261025"   # own namespace; never write into another lane's dir
BINS = {"52_64": (52, 64), "65_80": (65, 80), "81_100": (81, 100)}
ARMS = {"ctrl": 26103000, "subA": 26103100, "subB": 26103200}
GROOVE = json.loads((ROOT / "results/c3_groove_reference_20261025.json").read_text())
GROOVE_SET = set(GROOVE["groove_residues_1based"])


def seq_of(residues):
    return "".join(checks.AA3.get(r["resname"], "X") for r in residues)


def admit(cif, arm, bin_key, seed):
    name = f"E3_{arm}_{bin_key}_{seed}"
    rec = {"name": name, "arm": arm, "bin": bin_key, "seed": seed,
           "cif": str(cif.relative_to(ROOT)), "intended_len": list(BINS[bin_key])}
    try:
        rec["construct"] = {k: v for k, v in construct.verify(cif).items()
                            if k in ("target_length", "unplaced_atoms",
                                     "target_sequence_sha256", "ca_distance_min",
                                     "ca_distance_max")}
    except AssertionError as e:
        rec.update(pass_=False, reason=f"construct: {e}")
        return rec
    pdb = E3 / "complex_pdbs" / f"{name}.pdb"
    pdb.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([sys.executable, str(ROOT / "scripts/cif_to_pdb_20261025.py"),
                    str(cif), str(pdb)], check=True, capture_output=True)
    ch = checks.parse_pdb(str(pdb))
    if len(ch) != 2:
        rec.update(pass_=False, reason=f"expected 2 chains, found {sorted(ch)}")
        return rec
    binder = min(ch.values(), key=len)
    target = [c for c in ch.values() if c is not binder][0]
    bseq = seq_of(binder)
    plddt = [b for res in binder for b in res["bfac"].values()]
    rec.update(
        binder_sequence=bseq, binder_len=len(binder), target_len=len(target),
        binder_sequence_sha256=checks._seqsha(bseq),
        target_sequence_sha256=checks._seqsha(seq_of(target)),
        binder_mean_plddt=round(sum(plddt) / len(plddt), 2) if plddt else 0.0)
    lo, hi = BINS[bin_key]
    reasons = []
    if not (lo <= len(binder) <= hi):
        reasons.append(f"binder length {len(binder)} outside {lo}-{hi}")
    if len(target) != 111:
        reasons.append(f"target length {len(target)} != 111")
    rec["pass_"] = not reasons
    if reasons:
        rec["reason"] = "; ".join(reasons)
    return rec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", action="store_true")
    ap.add_argument("--arms", default="ctrl,subA,subB")
    a = ap.parse_args()
    rows, seen = [], {}
    for arm in [x for x in a.arms.split(",") if x]:
        for bin_key in BINS:
            for off in range(24):
                want = ("52_64" if off <= 7 else "65_80" if off <= 15 else "81_100")
                if want != bin_key:
                    continue
                seed = str(ARMS[arm] + off)
                want = f"e3_{arm}_{bin_key}_{seed}"
                dirs = [d for d in (E3 / "pulled").rglob(want) if d.is_dir()]
                hits = sorted(c for d in dirs
                              for c in d.glob("inference_samples/*/*_generated.cif"))
                if not hits:
                    rows.append({"name": f"E3_{arm}_{bin_key}_{seed}", "arm": arm,
                                 "bin": bin_key, "seed": seed, "pass_": False,
                                 "reason": "missing output"})
                    continue
                if len(hits) > 1:
                    rows.append({"name": f"E3_{arm}_{bin_key}_{seed}", "arm": arm,
                                 "bin": bin_key, "seed": seed, "pass_": False,
                                 "reason": f"{len(hits)} CIFs in one seed dir"})
                    continue
                rec = admit(hits[0], arm, bin_key, seed)
                if rec.get("pass_"):
                    s = rec["binder_sequence"]
                    if s in seen:
                        rec["pass_"] = False
                        rec["reason"] = f"duplicate binder sequence of {seen[s]}"
                    else:
                        seen[s] = rec["name"]
                rows.append(rec)
    E3.mkdir(parents=True, exist_ok=True)
    out = E3 / "admission.json"
    out.write_text(json.dumps(rows, indent=1) + "\n")
    for arm in [x for x in a.arms.split(",") if x]:
        sel = [r for r in rows if r["arm"] == arm]
        ok = sum(1 for r in sel if r.get("pass_"))
        print(f"arm {arm}: {ok}/{len(sel)} admitted")
        for r in sel:
            if not r.get("pass_"):
                print(f"  REJECT {r['name']}: {r.get('reason')}")
    ok = sum(1 for r in rows if r.get("pass_"))
    print(f"TOTAL {ok}/{len(rows)} admitted -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
