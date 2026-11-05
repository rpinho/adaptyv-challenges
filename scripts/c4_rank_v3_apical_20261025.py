#!/usr/bin/env python3
"""C4 direction-ranked candidates v3 — structural screen on the CORRECT apical construct.

WHY v3 EXISTS
v2 (`3370909a...`) ranked designs by iPTM/L6 computed on the 195-residue contiguous apical
domain (P02786 189-383), but computed its d_min / 2.0 A screen on the 154-residue stitched
surrogate in results/c4_rebuild_20261024/remote_pdbs/. Same binder, different receptor.
Measured on the correct construct, v2's 20 rows are 14/20 clean, not 20/20.

v3 changes EXACTLY ONE thing: the structural screen reads the apical PDBs. Every other rule is
identical to v2 — same inputs, same iPTM floor, same L6 sign gate, same ranking order, same
diversity rule, same 2.0 A threshold. v2 is preserved, never edited; v3 is a new versioned file.

CONTROL GATE (required, runs first)
Re-running v2's algorithm against the v2 PDB directory must reproduce the shipped v2 20-name
list AND its d_min values. If it does not, this script exits nonzero and writes nothing: that
would mean the v2 algorithm is not what produced the shipped file, and v3 could not be
attributed to a single changed input.

Astra's ruling (2026-10-25): correct the screening workflow, produce a versioned artifact,
preserve the original, and freeze the corrected cohort before the port gate and native pilot.

This is still a MODELLED readout on predicted complexes. It is evidence only, not a submission.
"""
from __future__ import annotations

import argparse
import csv
import glob
import importlib.util
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
AUDIT = ROOT / "results/c4_selection_audit_20261025/audit.json"
LINK = ROOT / "results/c4_linkage_audit_20261025/summary.json"
PREVIEW = ROOT / "results/c4_apical_preview_20261024.csv"
OUTDIR = ROOT / "results/c4_ranked_v3_apical_20261025"
SHIPPED_V2 = ROOT / "results/c4_ranked_20261025/c4_acid_ranked_20261025.csv"
SHIPPED_V2_JSON = ROOT / "results/c4_ranked_20261025/c4_acid_ranked_20261025.json"
SURROGATE_PDBS = ROOT / "results/c4_rebuild_20261024/remote_pdbs"
APICAL_PDBS = ROOT / "results/c4_apical_pdb_audit_20261025/all343"
CLASH_GATE_A = 2.0
SEQ_SOURCES = ["results/c4_acid_combined.csv", "results/c4_acid_r2_binders.csv",
               "results/c4_acid1_filtered.csv", "results/c4_acid2_filtered.csv",
               "results/c4_apical_preview_20261024.csv"]


def load_module(name, rel):
    spec = importlib.util.spec_from_file_location(name, ROOT / rel)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def select(pool, pdb_dir, slots, clash, crosswalk):
    """v2's exact algorithm, parameterised only by which PDB directory is read."""
    chosen, rejected, measured, cache = [], [], {}, {}

    def pdb_for(n):
        if n not in cache:
            p = pathlib.Path(pdb_dir) / f"{n}_complex.pdb"
            cache[n] = p if p.exists() else None
        return cache[n]

    for r in pool:
        if len(chosen) >= slots:
            break
        p = pdb_for(r["name"])
        if p is None:
            rejected.append({"name": r["name"], "why": "no archived structure"})
            continue
        chains = clash.parse_pdb(p)
        if len(chains) != 2:
            rejected.append({"name": r["name"], "why": f"{len(chains)} chains"})
            continue
        order = sorted(chains, key=lambda c: len(chains[c]))
        n_clash = len(clash.clashing_pairs(chains[order[0]], chains[order[1]], CLASH_GATE_A))
        if n_clash:
            rejected.append({"name": r["name"], "why": "rank-001 clash",
                             "n_clash_pairs": n_clash})
            continue
        rec = crosswalk.load(p, r["name"])
        if rec is None:
            rejected.append({"name": r["name"], "why": "<20 CA"})
            continue
        dup = None
        for name, prior in measured.items():
            c = crosswalk.compare(rec, prior)
            if c and c["tm"] >= 0.65 and c["coverage"] >= 0.80:
                dup = {"name": name, "tm": c["tm"], "coverage": c["coverage"]}
                break
        if dup:
            rejected.append({"name": r["name"], "why": "near-identical to retained",
                             "to": dup["name"], "tm": dup["tm"],
                             "coverage": dup["coverage"]})
            continue
        dmin, _, _ = clash.min_interchain_distance(chains[order[0]], chains[order[1]], 6.0)
        chosen.append(dict(r, n_clash_pairs=0, d_min=round(float(dmin), 3)))
        measured[r["name"]] = rec
    return chosen, rejected, measured


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--slots", type=int, default=20)
    ap.add_argument("--iptm-floor", type=float, default=0.60)
    ap.add_argument("--out", default=str(OUTDIR / "c4_acid_ranked_v3_apical_20261025.csv"))
    ap.add_argument("--control-only", action="store_true")
    args = ap.parse_args()

    audit = json.loads(AUDIT.read_text())
    link = json.loads(LINK.read_text())
    if not link["controls"].get("all_ok"):
        sys.exit("sign controls FAILED; refusing to rank on an unvalidated sign convention")

    clash = load_module("clash", "scripts/c3_clash_audit_independent_20261025.py")
    crosswalk = load_module("cw", "scripts/c3_round2_cluster_crosswalk_20261025.py")

    recs = [r for r in audit["records"] if r.get("L6") is not None]
    pool = [r for r in recs
            if r.get("iptm") is not None and r["iptm"] >= args.iptm_floor and r["L6"] > 0]
    pool.sort(key=lambda r: (-r["L6"], -(r["iptm"] or 0), r["name"]))

    # ---- CONTROL: v2 algorithm on v2's PDBs must reproduce the shipped v2 file ----
    ctl_chosen, _, _ = select(pool, SURROGATE_PDBS, args.slots, clash, crosswalk)
    shipped_json = json.loads(SHIPPED_V2_JSON.read_text())
    shipped_names = [r["name"] for r in shipped_json["chosen_by_L6"]]
    shipped_dmin = {r["name"]: r["d_min_A"] for r in shipped_json["chosen_by_L6"]}
    ctl_names = [r["name"] for r in ctl_chosen]
    name_ok = ctl_names == shipped_names
    dmin_ok = all(abs(r["d_min"] - shipped_dmin[r["name"]]) < 0.02 for r in ctl_chosen)

    control = {"names_reproduced": name_ok, "dmin_reproduced": dmin_ok,
               "n_control": len(ctl_chosen), "n_shipped": len(shipped_names)}
    print(f"CONTROL v2-algorithm-on-v2-PDBs: names={name_ok} dmin={dmin_ok} "
          f"({len(ctl_chosen)}/{len(shipped_names)})")
    if not (name_ok and dmin_ok):
        print("CONTROL FAILED — v3 not written. The v2 algorithm does not reproduce v2.",
              file=sys.stderr)
        return 3
    if args.control_only:
        return 0

    # ---- v3: identical algorithm, apical PDBs ----
    chosen, rejected, measured = select(pool, APICAL_PDBS, args.slots, clash, crosswalk)

    seqs = {}
    for src in SEQ_SOURCES:
        p = ROOT / src
        if not p.exists():
            continue
        for row in csv.DictReader(open(p)):
            n = row.get("name")
            if n and n not in seqs and row.get("sequence"):
                seqs[n] = row["sequence"]
    missing = [r["name"] for r in chosen if r["name"] not in seqs]
    if missing:
        sys.exit(f"missing sequences for {len(missing)} chosen designs: {missing[:5]}")

    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["name", "sequence", "molecule_class"])
        for r in chosen:
            w.writerow([r["name"], seqs[r["name"]], "single_chain"])

    preview_names = {row["name"] for row in csv.DictReader(open(PREVIEW))}
    added = [r["name"] for r in chosen if r["name"] not in shipped_names]
    dropped = [n for n in shipped_names if n not in {r["name"] for r in chosen}]
    manifest = {
        "artifact": "EVIDENCE ONLY — not a submission; no promotion; supersedes v2 for PILOT "
                    "SELECTION only (Astra 2026-10-25)",
        "supersedes_for_pilot_selection": "results/c4_ranked_20261025/c4_acid_ranked_20261025.csv "
                                          "(3370909a...)",
        "what_changed": "ONLY the structural screen input directory: surrogate 154-residue PDBs "
                        "-> apical 195-residue PDBs. Every selection rule is identical to v2.",
        "control": control,
        "selection_rule": f"iPTM>=-{args.iptm_floor:.2f} AND L6>0, ranked by L6 desc then iPTM "
                          f"desc then name, take {args.slots}",
        "sign_controls": link["controls"],
        "n_consolidated_scored": len(recs),
        "n_eligible": sum(1 for r in recs if r.get("iptm") is not None
                          and r["iptm"] >= args.iptm_floor),
        "n_eligible_acid_on": len(pool),
        "slots_filled": len(chosen),
        "clash_gate_A": CLASH_GATE_A,
        "pdb_source": "results/c4_apical_pdb_audit_20261025/all343 "
                      "(Modal volume rfd4-runs/boltz2_c4_apical, chain B = 195)",
        "added_vs_v2": added,
        "dropped_vs_v2": dropped,
        "diversity_rejections": rejected,
        "out_csv": str(out.relative_to(ROOT)),
        "chosen_by_L6": [{"rank": i + 1, "name": r["name"], "L6": r["L6"],
                          "iptm": round(r["iptm"], 3), "d_min_A": r.get("d_min"),
                          "margin_A": round(float(r.get("d_min") or 0) - CLASH_GATE_A, 3),
                          "margin_band": ("borderline_2.0-2.2" if (r.get("d_min") or 0) < 2.2
                                          else "above_2.2"),
                          "in_preview": r["name"] in preview_names}
                         for i, r in enumerate(chosen)],
        "margin_summary": {
            "borderline_2.0-2.2": sum(1 for r in chosen if (r.get("d_min") or 0) < 2.2),
            "above_2.2": sum(1 for r in chosen if (r.get("d_min") or 0) >= 2.2),
            "min_A": min((r.get("d_min") or 0) for r in chosen),
            "max_A": max((r.get("d_min") or 0) for r in chosen),
        },
        "caveats": [
            "SELECTION ARTIFACT: the acid-ON rate and mean-L6 gain are guaranteed by ranking on L6",
            "2.0 A heavy-atom screen is atom-type-blind and permissive",
            "modelled PROPKA readout on predicted complexes, not experimental evidence",
            "cannot prove pH-conditional binding or release",
            "domain-only / non-native target construct",
            "v2 is preserved unchanged; this is a new versioned artifact",
            "a new artifact needs Ricardo approval before any use",
        ],
    }
    (OUTDIR / "c4_acid_ranked_v3_apical_20261025.json").write_text(
        json.dumps(manifest, indent=1) + "\n")
    print(f"wrote {len(chosen)} rows -> {out.name}")
    print(f"added vs v2: {added}")
    print(f"dropped vs v2: {dropped}")
    print(f"d_min range {manifest['margin_summary']['min_A']} - "
          f"{manifest['margin_summary']['max_A']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
