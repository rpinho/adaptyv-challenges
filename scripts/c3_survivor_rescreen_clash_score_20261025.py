#!/usr/bin/env python3
"""CLASH SCORER for the C3 survivor 5-model re-screen (Modal outputs).

Metric source, per the orchestrator's instruction: the parser and contact primitive used by
`scripts/c3_challenger_model_pick_20261025.py::metric_one` **verbatim** -- i.e. the frozen
verifier `scripts/c3_round2_verify_20261025.py`:

    V.parse_pdb   ATOM records only, first altloc ("", "A"), fixed columns
    V.heavy       atoms whose name does not start with "H"
    V.contacts    counts heavy-atom PAIRS with d2 <= cutoff^2
    V.CLASH_A     2.0 A

`contacts()` returns a *count of atom pairs*, not a minimum distance, so the minimum is computed
here over exactly the same heavy-atom set (same parser, same altloc rule, same atom filter) and the
pair count is reported alongside it as a consistency check: clash_pairs > 0 exactly when
min_inter_dist <= CLASH_A.

Per design, per ranked model: min inter-chain heavy-atom distance, clash-pair count, iPTM.
Per design: n_clashing_models / 5 and a verdict.  >=1 clashing model of 5 => DISQUALIFIED.

The denominator is ALWAYS 5 (the protocol screens 5 models). If fewer than 5 models are present on
disk, that is reported as `models_on_disk: k`, the verdict says INCOMPLETE, and the design is not
silently treated as clean -- a rank-001-only directory cannot certify a 5-model claim.

Modes
  --mode calibrate   score the three designs with known recorded values (default; CPU only)
  --mode dir         score a pulled Modal output directory tree
  --mode selfcheck   assert clash_pairs>0 <=> min_dist<=2.0 on every scored model, then exit

CPU only. No GPU, no pod, no Modal call, no network. Writes only inside results/.../clash/.
"""
from __future__ import annotations

import argparse
import csv
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import c3_round2_verify_20261025 as V          # parser + contacts, used verbatim

OUT = ROOT / "results/c3_survivor_rescreen_20261025/clash"
INPUT = ROOT / "results/c3_survivor_rescreen_20261025/screen_input_20261025.csv"
ELIG = ROOT / "results/c3_v8_eligibility_20261025/eligibility.json"

# Designs with recorded values to reproduce. `expect_models` is what is actually on disk.
CALIBRATION = [
    # name,                   artifact dir,                                                   expect_models, recorded min A, recorded clash pairs
    ("B_26102611_s1",  "results/c3_round2_111_20261025/screen24/c/B_26102611_s1",              1, 2.671, 0),
    ("c3_bc_l57_fbcf76", "results/c3_pod_artifacts_20261025",                                  1, 2.330, 0),
    ("c3_glp1r_ecd_172", "results/c3_pod_artifacts_20261025",                                  1, 2.506, 0),
]
# the two pod-artifact files are flat: <name>_complex.pdb / <name>_scores.json
FLAT_NAMES = {"c3_bc_l57_fbcf76", "c3_glp1r_ecd_172"}


def min_interchain_distance(binder, target):
    """True minimum inter-chain heavy-atom distance, over V.heavy() atoms.

    Same atom set as V.contacts(): binder/target residues from V.parse_pdb, hydrogens dropped by
    V.heavy(). No cutoff -- this is the uncensored minimum, so every model reports a real number.
    Returns (d_min, binder_atom_label, target_atom_label) or (None, None, None) if no atoms.
    """
    best = (None, None, None)
    for bi, bres in enumerate(binder):
        for bname, bxyz in V.heavy(bres).items():
            for ti, tres in enumerate(target):
                for tname, txyz in V.heavy(tres).items():
                    dx = bxyz[0] - txyz[0]
                    dy = bxyz[1] - txyz[1]
                    dz = bxyz[2] - txyz[2]
                    d2 = dx * dx + dy * dy + dz * dz
                    if best[0] is None or d2 < best[0]:
                        # residue-numbered labels, matching eligibility.json's `closest_atoms` format
                        best = (d2, f"{bres['resname']}{bi+1}:{bname}",
                                f"{tres['resname']}{ti+1}:{tname}")
    if best[0] is None:
        return None, None, None
    return round(best[0] ** 0.5, 3), best[1], best[2]


def score_model(binder_expect, target_expect, scorep, pdbp):
    """One ranked model -> its clash measurement. Mirrors metric_one's assignment logic."""
    r = {"score_file": scorep.name if scorep else None,
         "pdb_file": pdbp.name if pdbp else None,
         "min_inter_dist": None, "clash_pairs": None, "clash_clean": None,
         "iptm": None, "status": "ok", "reasons": []}
    if scorep is not None:
        try:
            s = json.loads(scorep.read_text())
            r["iptm"] = s.get("iptm")
            r["ptm"] = s.get("ptm")
        except Exception as e:
            r["status"] = "bad_scores"; r["reasons"].append(f"scores unreadable: {e}")
    else:
        r["reasons"].append("no scores json")
    if pdbp is None:
        r["status"] = "no_pdb"; r["reasons"].append("no pdb")
        return r
    if not pdbp.exists():
        r["status"] = "no_pdb"; r["reasons"].append("pdb path missing")
        return r

    chains = V.parse_pdb(pdbp)
    if len(chains) != 2:
        r["status"] = "fail"
        r["reasons"].append(f"expected 2 chains, found {sorted(chains)}")
        return r
    by_seq = {c: V.seq_of(chains[c]) for c in chains}
    bids = [c for c, q in by_seq.items() if q == binder_expect]
    tids = [c for c, q in by_seq.items() if q == target_expect]
    if len(bids) != 1 or len(tids) != 1 or bids[0] == tids[0]:
        r["status"] = "fail"
        r["reasons"].append("chain assignment ambiguous")
        return r

    binder, target = chains[bids[0]], chains[tids[0]]
    r["binder_chain"], r["target_chain"] = bids[0], tids[0]
    r["sequence_bound"] = (V.seq_of(binder) == binder_expect and V.seq_of(target) == target_expect)
    if not r["sequence_bound"]:
        r["reasons"].append("sequence mismatch")

    dmin, batom, tatom = min_interchain_distance(binder, target)
    nclash, _ = V.contacts(binder, target, V.CLASH_A)
    r.update({"min_inter_dist": dmin, "closest_binder_atom": batom,
              "closest_target_atom": tatom, "clash_pairs": nclash,
              "clash_clean": nclash == 0,
              "clashes_lt2A": nclash})
    # consistency: the pair count and the minimum must agree about the 2.0 A line
    if dmin is not None:
        agree = (nclash > 0) == (dmin <= V.CLASH_A)
        r["count_min_agree"] = agree
        if not agree:
            r["status"] = "inconsistent"
            r["reasons"].append(f"clash_pairs={nclash} but min_dist={dmin}")
    if not r["clash_clean"]:
        r["reasons"].append(f"clash {nclash} pair(s), min {dmin} A < {V.CLASH_A} A")
    return r


def design_dirs(root: pathlib.Path, name: str):
    """Directories holding this design. If `root` is itself the design dir, return it."""
    if root.is_dir() and root.name == name:
        return [root]
    return sorted(p for p in root.glob(f"**/{name}") if p.is_dir())


def find_models(d: pathlib.Path):
    """{rank: (score_path, pdb_path or None)} for every ranked model present.

    Handles both the ColabFold raw naming and the distilled naming the Modal clone writes
    (scores_rank_001.json + complex_rank_001.pdb).
    """
    out = {}
    for p in sorted(d.glob("*scores_rank_*.json")):
        m = re.search(r"scores_rank_(\d+)", p.name)
        if not m:
            continue
        rank = int(m.group(1))
        stem = p.name.split("_scores_rank_")[0]
        cands = (sorted(d.glob(f"{stem}_unrelaxed_rank_{rank:03d}_*.pdb"))
                 or sorted(d.glob(f"{stem}_rank_{rank:03d}_*.pdb"))
                 or sorted(d.glob(f"complex_rank_{rank:03d}.pdb")))
        out[rank] = (p, cands[0] if cands else None)
    return out


def score_design(name, binder, target, d: pathlib.Path):
    models = find_models(d)
    per = []
    for rank in sorted(models):
        sc, pdb = models[rank]
        rec = score_model(binder, target, sc, pdb)
        rec["rank"] = rank
        per.append(rec)
    n_found = len(per)
    n_clash = sum(1 for r in per if r.get("clash_clean") is False)
    if n_clash > 0:
        verdict = "DISQUALIFIED"
        reason = f"clash in {n_clash} of 5 model(s)"
    elif n_found < 5:
        verdict = "INCOMPLETE"
        reason = f"only {n_found}/5 models on disk; cannot certify a 5-model claim"
    else:
        verdict = "PASS"
        reason = "clash-clean on all 5 models"
    return {"name": name, "design_dir": str(d), "models_on_disk": n_found,
            "models_expected": 5,
            "per_rank": per,
            "per_rank_min_dist": {r["rank"]: r["min_inter_dist"] for r in per},
            "n_clashing_models": n_clash,
            "n_clashing_of_five": f"{n_clash}/5",
            "verdict": verdict, "verdict_reason": reason}


def load_inputs():
    return {r["name"]: (r["binder"].strip(), r["target"].strip())
            for r in csv.DictReader(open(INPUT, newline=""))}


def calibrate():
    inputs = load_inputs()
    elig = {r["name"]: r for r in json.loads(ELIG.read_text())["rows"]}
    out, ok = [], True
    for name, rel, exp_models, exp_dmin, exp_pairs in CALIBRATION:
        binder, target = inputs[name]
        base = ROOT / rel
        if name in FLAT_NAMES:
            pdb = base / f"{name}_complex.pdb"
            sc = base / f"{name}_scores.json"
            rec = score_model(binder, target, sc, pdb)
            rec["rank"] = 1
            per = [rec]
            d = base
        else:
            d = design_dirs(base, name)[0]
            per = []
            for rank, (sc, pdb) in sorted(find_models(d).items()):
                rec = score_model(binder, target, sc, pdb)
                rec["rank"] = rank
                per.append(rec)
        got_models = len(per)
        got_dmin = per[0]["min_inter_dist"] if per else None
        got_pairs = per[0]["clash_pairs"] if per else None
        elig_dmin = elig[name]["min_interchain_dist"]
        checks = {
            "models_on_disk": got_models == exp_models,
            "min_dist_matches_recorded": (got_dmin is not None
                                          and abs(got_dmin - exp_dmin) <= 0.01),
            "clash_pairs_matches_recorded": got_pairs == exp_pairs,
            "matches_eligibility_json": (got_dmin is not None and elig_dmin is not None
                                         and abs(got_dmin - elig_dmin) <= 0.01),
        }
        passed = all(checks.values())
        ok &= passed
        out.append({"name": name, "design_dir": str(d), "models_on_disk": got_models,
                    "models_expected": exp_models,
                    "per_rank": per,
                    "per_rank_min_dist": {r["rank"]: r["min_inter_dist"] for r in per},
                    "n_clashing_models": sum(1 for r in per if r.get("clash_clean") is False),
                    "n_clashing_of_five": f"{sum(1 for r in per if r.get('clash_clean') is False)}/5",
                    "recorded_min_inter_dist": exp_dmin,
                    "recomputed_min_inter_dist": got_dmin,
                    "eligibility_min_inter_dist": elig_dmin,
                    "delta_vs_recorded": None if got_dmin is None else round(got_dmin - exp_dmin, 3),
                    "checks": checks,
                    # NOT "PASS": these artifacts are rank-001 only, so reproducing the recorded
                    # number says the metric is right, not that the design is 5-model clash-clean.
                    "verdict": "REPRODUCED" if passed else "CALIBRATION_FAILED",
                    "certification": ("not certifiable: {} of 5 models on disk".format(got_models)
                                      if got_models < 5 else "5-model certifiable")})
    return {"mode": "calibrate", "metric": "V.parse_pdb + V.heavy + V.CLASH_A (verbatim)",
            "clash_cutoff_a": V.CLASH_A, "all_reproduced": ok, "designs": out}


def score_dir(root: pathlib.Path):
    inputs = load_inputs()
    designs = []
    for name in inputs:
        binder, target = inputs[name]
        hits = design_dirs(root, name)
        if not hits:
            designs.append({"name": name, "design_dir": None, "models_on_disk": 0,
                            "models_expected": 5, "per_rank": [], "per_rank_min_dist": {},
                            "n_clashing_models": 0, "n_clashing_of_five": "0/5",
                            "verdict": "MISSING", "verdict_reason": "no output directory in pull"})
            continue
        designs.append(score_design(name, binder, target, hits[0]))
    return {"mode": "dir", "root": str(root), "metric": "V.parse_pdb + V.heavy + V.CLASH_A (verbatim)",
            "clash_cutoff_a": V.CLASH_A, "designs": designs}


def audit_pull(root: pathlib.Path):
    """Flag outputs written by the PRE-FIX Modal clone: valid iptm/ptm but no ranks 2-5.

    The fixed clone always writes `ranks_kept` into scores.json (line 173). Its absence proves the
    directory was written before the fix -- and `_valid_scores()` in the Modal script only checks
    iptm/ptm, so such a directory is treated as DONE and never regenerated. That makes it permanent.
    """
    out = {"root": str(root), "stale": [], "fine": [], "missing_scores": []}
    for d in sorted(p for p in root.glob("**/*") if p.is_dir()):
        sp = d / "scores.json"
        if not sp.exists():
            if (d / "scores_rank_001.json").exists() or (d / "complex_rank_001.pdb").exists():
                out["missing_scores"].append(str(d))
            continue
        try:
            rec = json.loads(sp.read_text())
        except Exception:
            out["missing_scores"].append(str(d))
            continue
        ranks = sorted(int(m.group(1)) for f in d.glob("scores_rank_*.json")
                       for m in [re.search(r"scores_rank_(\d+)", f.name)] if m)
        prov = "ranks_kept" in rec
        entry = {"design": d.name, "ranks_present": ranks,
                 "scores_has_ranks_kept": prov,
                 "iptm": rec.get("iptm")}
        # stale = written by pre-fix code, or claims 5 models but holds rank-001 only
        if (not prov) or (rec.get("num_models") == 5 and ranks != [1, 2, 3, 4, 5]):
            entry["why"] = ("scores.json lacks ranks_kept -> written by pre-fix clone"
                            if not prov else
                            f"num_models=5 but ranks on disk {ranks}")
            entry["consequence"] = ("predict() sees _valid_scores()==True and returns early; "
                                   "ranks 2-5 will NEVER be generated")
            out["stale"].append(entry)
        else:
            out["fine"].append(entry)
    out["ok"] = not out["stale"] and not out["missing_scores"]
    return out


def wide_calibration():
    """80-model positive/negative control against the R3 five-model cohort.

    The 3 primary calibrations are all clean structures, so a parser that UNDER-counts clashes would
    pass them. This replays all 16 R3 designs x 5 models (available via five_model_recovery) against
    their recorded clash counts -- 10 of those designs have >=1 clashing model, so both classes are
    represented. Agreement on a clashing model is the evidence that the metric detects what it claims.
    """
    rec = json.loads((ROOT / "results/c3_five_model_pick_20261025/per_model_metrics.json").read_text())
    r3p = ROOT / "results/c3_r3_20261025/screen_input_20261025.csv"
    r3 = {r["name"]: r for r in csv.DictReader(open(r3p, newline=""))}
    base = ROOT / "results/c3_r3_20261025/five_model_recovery"
    tot = agree = 0
    bad = []
    n_clashing_models = 0
    for design in rec:
        name = design["name"]
        if name not in r3:
            continue
        binder = r3[name]["binder"].strip()
        target = r3[name]["target"].strip()
        hits = [q for q in base.glob(f"*/{name}") if q.is_dir()]
        if not hits:
            continue
        models = find_models(hits[0])
        for m in design["per_model"]:
            mm = re.search(r"rank_(\d+)", m.get("pdb_file") or "")
            if not mm:
                continue
            rank = int(mm.group(1))
            if rank not in models:
                continue
            sc, pdb = models[rank]
            got = score_model(binder, target, sc, pdb)
            want = m.get("clashes_lt2A")
            tot += 1
            if want:
                n_clashing_models += 1
            if got["clash_pairs"] == want:
                agree += 1
            else:
                bad.append({"design": name, "rank": rank, "got": got["clash_pairs"],
                            "recorded": want, "min_dist": got["min_inter_dist"]})
    return {"models_compared": tot, "pair_counts_agree": agree, "mismatches": len(bad),
            "clashing_models_in_control": n_clashing_models,
            "both_classes_present": n_clashing_models > 0,
            "bad": bad, "ok": not bad and tot > 0}


def selfcheck(payloads):
    bad = []
    n = 0
    for p in payloads:
        for d in p["designs"]:
            for r in d.get("per_rank", []):
                if r.get("min_inter_dist") is None:
                    continue
                n += 1
                if not r.get("count_min_agree", False):
                    bad.append((d["name"], r["rank"], r["clash_pairs"], r["min_inter_dist"]))
    return {"models_checked": n, "disagreements": bad, "ok": not bad}


def table(designs):
    """Plain-text table. Formatted with .format() to stay readable under Python 3.9."""
    lines = ["{:<22} {:>4} {:>9} {:>6} {:>6} {:>6}".format(
        "design", "rank", "min_dist", "pairs", "clean", "iptm"), "-" * 60]
    for d in designs:
        if not d.get("per_rank"):
            lines.append("{:<22} {:>4} {:>9} {:>6} {:>6} {:>6}   [{}]".format(
                d["name"], "--", "--", "--", "--", "--", d["verdict"]))
            continue
        for r in d["per_rank"]:
            iptm = r.get("iptm")
            iptm_s = "{:.3f}".format(iptm) if isinstance(iptm, (int, float)) else "--"
            lines.append("{:<22} {:>4} {:>9} {:>6} {:>6} {:>6}".format(
                d["name"], r["rank"], str(r["min_inter_dist"]), str(r["clash_pairs"]),
                str(r["clash_clean"]), iptm_s))
        lines.append("{:<22} {:>4} -> n_clashing {}, models on disk {}/5, {}".format(
            "", "", d["n_clashing_of_five"], d["models_on_disk"], d["verdict"]))
        lines.append("")
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--mode", default="calibrate",
                    choices=["calibrate", "dir", "selfcheck", "audit-pull", "wide-calibrate"])
    ap.add_argument("--root", default=str(ROOT / "results/c3_survivor_rescreen_20261025/modal_pull"))
    ap.add_argument("--json-out", default=None)
    args = ap.parse_args()

    OUT.mkdir(parents=True, exist_ok=True)
    if args.mode == "calibrate":
        payload = calibrate()
        target = pathlib.Path(args.json_out or OUT / "calibration.json")
    elif args.mode == "wide-calibrate":
        res = wide_calibration()
        (OUT / "wide_calibration.json").write_text(json.dumps(res, indent=1) + "\n")
        print(json.dumps({k: res[k] for k in ("models_compared", "pair_counts_agree",
                                             "mismatches", "clashing_models_in_control",
                                             "both_classes_present", "ok")}, indent=1))
        return 0 if res["ok"] else 8
    elif args.mode == "audit-pull":
        res = audit_pull(pathlib.Path(args.root))
        (OUT / "pull_audit.json").write_text(json.dumps(res, indent=1) + "\n")
        print(json.dumps({"ok": res["ok"], "n_stale": len(res["stale"]),
                          "stale": res["stale"], "fine": [e["design"] for e in res["fine"]],
                          "missing_scores": res["missing_scores"]}, indent=1))
        return 0 if res["ok"] else 7
    elif args.mode == "dir":
        payload = score_dir(pathlib.Path(args.root))
        target = pathlib.Path(args.json_out or OUT / "clash_scores.json")
    else:
        payloads = []
        cal = OUT / "calibration.json"
        if cal.exists():
            payloads.append(json.loads(cal.read_text()))
        sc = OUT / "clash_scores.json"
        if sc.exists():
            payloads.append(json.loads(sc.read_text()))
        res = selfcheck(payloads)
        print(json.dumps(res, indent=1))
        return 0 if res["ok"] else 1

    payload["table"] = table(payload["designs"])
    if args.mode == "dir":
        ds = payload["designs"]
        payload["summary"] = {
            "n_designs": len(ds),
            "n_scored_at_least_one_model": sum(1 for d in ds if d["models_on_disk"] > 0),
            "n_complete_5_of_5": sum(1 for d in ds if d["models_on_disk"] == 5),
            "n_disqualified": sum(1 for d in ds if d["verdict"] == "DISQUALIFIED"),
            "n_pass": sum(1 for d in ds if d["verdict"] == "PASS"),
            "n_incomplete": sum(1 for d in ds if d["verdict"] == "INCOMPLETE"),
            "n_missing": sum(1 for d in ds if d["verdict"] == "MISSING"),
        }
    target.write_text(json.dumps(payload, indent=1) + "\n")
    print(payload["table"])
    if args.mode == "dir":
        print("summary:", json.dumps(payload["summary"]))
    if args.mode == "calibrate":
        print("all_reproduced:", payload["all_reproduced"])
        return 0 if payload["all_reproduced"] else 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
