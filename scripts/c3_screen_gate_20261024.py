#!/usr/bin/env python3
"""C3 AF2-multimer screen — promotion-gate analysis (local, no GPU).

Reads the consolidated AF2M scores and reports the gate decision. Does NOT write
v7 — it produces the evidence table; writing v7 is a separate, deliberate step and
only if the gate is cleanly met.

Floor: computed from the v6 **BindCraft** designs' OWN iPTM in THIS screen (same
protocol), reported alongside the audit's ~0.76 reference. A shortlist candidate
"clears the floor" only if iPTM >= max(0.76, min BindCraft iPTM in this screen) —
i.e. it must be at least as confident as the weakest existing BindCraft anchor under
the identical predictor, and at least the audit reference.
All eight v6 BindCraft anchors must have scores before the floor or any positive
gate can be issued; partial scores are informational only.

Redundant-variant slots (replaceable, from the diversity audit): the point-mutant
variants that add ~0 backbone diversity. BindCraft anchors and RFD4-already-selected
slots are NOT replaceable.
"""
import csv
import json
from pathlib import Path

ROOT = Path("/Users/ricardo/dev/adaptyv-c4")
SCORES = ROOT / "results/c3_screen_af2m_scores_20261024.json"
V6 = ROOT / "results/c3_submission_v6_20261023.csv"
AUDIT_FLOOR = 0.76

# point-mutant variant slots (redundant per audit §2 — replaceable)
VARIANT_PREFIXES = ("c3_v_",)


def main():
    if not SCORES.exists():
        print(f"Screen incomplete: no scores yet at {SCORES}. "
              "Run `modal run modal_af2m_c3_complex.py::fetch` first.")
        return
    rows = json.loads(SCORES.read_text())
    by_name = {r["name"]: r for r in rows}
    scored = {n: r for n, r in by_name.items() if isinstance(r.get("iptm"), (int, float))}

    v6_names = [r["name"] for r in csv.DictReader(open(V6))]
    bindcraft = [n for n in v6_names if n.startswith("c3_bc_")]
    variants = [n for n in v6_names if n.startswith(VARIANT_PREFIXES)]
    rfd4_sel = [n for n in v6_names if n.startswith("c3_glp1r_ecd_")]

    bc_iptm = [scored[n]["iptm"] for n in bindcraft if n in scored]
    missing_bindcraft = [n for n in bindcraft if n not in scored]
    anchors_complete = len(bindcraft) == len(set(bindcraft)) == 8 and not missing_bindcraft
    floor = max(AUDIT_FLOOR, min(bc_iptm)) if anchors_complete else None

    print(f"Scored {len(scored)}/{len(by_name)} complexes.")
    bc_scores_text = ", ".join(f"{score:.3f}" for score in bc_iptm)
    print(f"BindCraft v6 iPTM (this screen): {bc_scores_text}")
    if anchors_complete:
        print(f"Floor = max(audit {AUDIT_FLOOR}, min BindCraft {min(bc_iptm):.3f}) "
              f"= {floor:.3f}\n")
    else:
        print(f"Screen incomplete: scored {len(bc_iptm)}/{len(bindcraft)} v6 BindCraft anchors; "
              "all 8 distinct anchors are required. Floor unavailable.")
        print(f"Missing BindCraft scores: {', '.join(missing_bindcraft) or '(none listed)'}\n")

    print("=== v6 (current 20) under this screen ===")
    for n in v6_names:
        s = scored.get(n)
        tag = "BC" if n in bindcraft else ("VAR" if n in variants else "RFD4sel")
        print(f"  [{tag:>7s}] {n:<26s} iptm={s['iptm']:.3f} ptm={s.get('ptm',0):.3f} "
              f"plddt={s.get('mean_plddt') or 0:.1f}" if s else f"  [{tag:>7s}] {n:<26s} (no score)")

    print("\n=== RFD4 shortlist (candidates) ranked by iPTM ===")
    cand = sorted((r for r in rows if r.get("source") == "rfd4_shortlist"
                   and isinstance(r.get("iptm"), (int, float))),
                  key=lambda d: -d["iptm"])
    clears = []
    for r in cand:
        hit = "CLEARS" if floor is not None and r["iptm"] >= floor else ""
        if hit:
            clears.append(r)
        print(f"  {r['name']:<22s} iptm={r['iptm']:.3f} ptm={r.get('ptm',0):.3f} "
              f"plddt={r.get('mean_plddt') or 0:.1f}  {hit}")

    print(f"\n=== GATE ===")
    if floor is not None:
        print(f"Candidates clearing floor {floor:.3f}: {len(clears)}")
    print(f"Replaceable (redundant variant) slots: {variants}")
    if not anchors_complete:
        print("DECISION: screen incomplete → no candidate promoted; KEEP v6, no v7.")
    elif not clears:
        print("DECISION: no candidate clears the same-protocol floor → KEEP v6, no v7.")
    else:
        print("Candidates that CLEAR the floor (still require refold + CSV-integrity + "
              "defensible diversity-gain replacement before any v7):")
        for r in clears:
            print(f"  - {r['name']} (iptm={r['iptm']:.3f})")
        print("NOTE: clearing the floor is necessary, NOT sufficient. v7 only if a cleared "
              "candidate also passes refold/structural checks and replaces a redundant variant "
              "with a defensible diversity gain. A score alone does not justify v7.")


if __name__ == "__main__":
    main()
