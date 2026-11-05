#!/usr/bin/env python3
"""Replacement-pool independence vs the SURVIVING 12 v8 rows (read-only, $0, CPU).

Why this exists: results/c3_replacement_pool_20261025.md measures the depth-arm pool
against all 20 v8 rows. Its own "what this does NOT settle" #2 says independence must be
re-measured against the 12 rows that would SURVIVE a filtered challenger, not assumed from
the arm's own dedup. This script measures exactly that, with the frozen rule.

Frozen rule (unchanged): near-identical iff TM >= 0.65 AND coverage >= 0.80.
Matrix: results/c3_r3_20261025/cross_tm_20261025.json (200 backbones x 20 v8 rows, complete).
Caveat (Astra 07:45): B_26102611_s1 has no binder PDB in backbone_pdb/, so it is absent from the
matrix. Missing comparisons are reported as INCOMPLETE, never as "clear". The dedicated gap
measurement lives in results/c3_survivor_gap_20261025/.
Writes: results/c3_replacement_independence_20261025/{summary.json,summary.md}
Nothing is written to any candidate CSV; no gate, score or ranking changes.
"""
import json, csv, pathlib, collections

ROOT = pathlib.Path(__file__).resolve().parents[1]
V8 = ROOT / "results/c3_submission_v8_20261025.csv"
MATRIX = ROOT / "results/c3_r3_20261025/cross_tm_20261025.json"
POOL = ROOT / "results/c3_wholeset_independence_20261025/per_backbone.json"
GAP = ROOT / "results/c3_survivor_gap_20261025/gap.json"
OUT = ROOT / "results/c3_replacement_independence_20261025"
TM_MIN, COV_MIN = 0.65, 0.80

# 8 flagged rows = 7 clash + 2 low-iPTM, 1 overlap. Source: c3_v8_eligibility_20261025/eligibility.md
FLAGGED = {
    "c3_bc_l70_7781fe", "c3_bc_l100_c674f8", "c3_bc_l99_e26aff", "c3_bc_l52_6950ff",
    "c3_bc_l100_4bd789", "c3_bc_l78_3d63fd", "c3_glp1r_ecd_29", "c3_glp1r_ecd_12",
}

def main():
    v8 = [r["name"] for r in csv.DictReader(open(V8))]
    assert len(v8) == 20, len(v8)
    assert FLAGGED <= set(v8), sorted(FLAGGED - set(v8))
    surviving = [n for n in v8 if n not in FLAGGED]
    m = json.load(open(MATRIX))
    pairs = m["pairs"]
    pool = json.load(open(POOL))
    # Supplementary per-backbone TM/coverage against survivors absent from the frozen matrix.
    gap_lookup = {}
    if GAP.exists():
        gd = json.load(open(GAP))
        for k, v in gd.get("pools", {}).items():
            for bb, rec in v.get("per_backbone", {}).items():
                if rec.get("status") == "MEASURED":
                    gap_lookup.setdefault(bb, {})[gd["survivor"]] = rec

    def nearest(backbone, targets):
        """Return (hits, closest, missing).

        Astra 07:45: a target absent from the frozen matrix must be reported as MISSING,
        never treated as "not near-identical". B_26102611_s1 is absent for this exact
        reason (no binder PDB in backbone_pdb/), so the earlier "clear of all 12" figure
        was really "clear of the 11 measured survivors".
        """
        row = pairs[backbone]
        hits, best, missing = [], None, []
        for t in targets:
            rec = row.get(t)
            if not rec or rec.get("tm") is None:
                # Fill from the dedicated survivor-gap run when that comparison was measured
                # there (B_26102611_s1 is absent from the frozen matrix for structural reasons).
                g = gap_lookup.get(backbone, {}).get(t)
                if g and g.get("status") == "MEASURED":
                    rec = {"tm": g["tm"], "coverage": g["coverage"], "source": "survivor_gap"}
                else:
                    missing.append(t)
                    continue
            tm, cov = rec["tm"], rec["coverage"]
            if best is None or tm > best["tm"]:
                best = {"target": t, "tm": tm, "coverage": cov}
            if tm >= TM_MIN and cov >= COV_MIN:
                hits.append({"target": t, "tm": tm, "coverage": cov})
        return hits, best, missing

    summary = {"rule": "near-identical iff TM>=0.65 AND coverage>=0.80 (frozen)",
               "matrix": str(MATRIX.relative_to(ROOT)),
               "matrix_complete": m.get("complete"),
               "matrix_backbones": len(pairs),
               "v8_rows": len(v8), "flagged_rows": len(FLAGGED),
               "surviving_rows": len(surviving), "surviving_names": surviving,
               "survivor_gap_source": str(GAP.relative_to(ROOT)) if GAP.exists() else "none",
               "survivor_gap_loaded": bool(gap_lookup), "pools": {}}

    for key in ("depth_pass", "depth_hq"):
        entries = pool[key]
        in_surv, in_flag = [], []
        bb_new, bb_hit = set(), set()
        per_bb = {}
        for e in entries:
            bb = e["backbone"]
            sh, sbest, smiss = nearest(bb, surviving)
            fh, fbest, _fmiss = nearest(bb, sorted(FLAGGED))
            if sh:
                in_surv.append(bb); bb_hit.add(bb)
            else:
                bb_new.add(bb)
            if fh:
                in_flag.append(bb)
            per_bb[bb] = {"sequences": e.get("sequences"),
                          "near_identical_surviving": [h["target"] for h in sh],
                          "max_tm_surviving": sbest["tm"] if sbest else None,
                          "closest_surviving": sbest["target"] if sbest else None,
                          "missing_surviving_comparisons": smiss,
                          "near_identical_flagged": [h["target"] for h in fh],
                          "max_tm_flagged": fbest["tm"] if fbest else None}
        nbb = len(entries)
        # Completeness: a backbone is only "clear" if EVERY survivor was actually measured.
        incomplete = {bb: v["missing_surviving_comparisons"] for bb, v in per_bb.items()
                      if v["missing_surviving_comparisons"]}
        summary["pools"][key] = {
            "label": key,
            "backbones": nbb,
            "backbones_near_identical_to_surviving": len(bb_hit),
            # None when any comparison is missing: "clear" would be an unmeasured claim.
            "backbones_clear_of_surviving": len(bb_new) if not incomplete else None,
            "backbones_clear_of_measured_survivors_only": len(bb_new),
            "completeness": "COMPLETE" if not incomplete else "INCOMPLETE",
            "incomplete_backbones": len(incomplete),
            "incomplete_detail": {bb: m for bb, m in list(incomplete.items())[:5]},
            "backbones_near_identical_to_flagged": len(in_flag),
            "fraction_backbones_clear_of_surviving": (round(len(bb_new) / nbb, 4)
                                                      if nbb and not incomplete else None),
            "per_backbone": per_bb,
        }
    OUT.mkdir(parents=True, exist_ok=True)
    json.dump(summary, open(OUT / "summary.json", "w"), indent=1)

    lines = ["# Replacement-pool independence vs the SURVIVING 12 v8 rows — $0, read-only", "",
             "**Question the pool document left open:** if the 8 flagged rows are dropped and a",
             "challenger is drawn from the depth arm, is the *replacement* set structurally distinct",
             "from the 12 rows that remain — measured against those 12, not against all 20?", "",
             f"- frozen rule: `{summary['rule']}`",
             f"- matrix: `{summary['matrix']}` — complete={summary['matrix_complete']}, "
             f"{summary['matrix_backbones']} backbones x {summary['v8_rows']} v8 rows",
             f"- survivor gap: `{summary.get('survivor_gap_source','none')}` "
             f"(comparisons absent from the matrix, measured separately)",
             f"- surviving rows ({len(surviving)}): {', '.join(f'`{n}`' for n in surviving)}", "",
             "| pool | backbones | near-identical to a survivor | clear of all 12 | % clear | completeness | near-identical to a flagged row |",
             "|---|---:|---:|---:|---:|---|---:|"]
    for key, v in summary["pools"].items():
        clear = v["backbones_clear_of_surviving"]
        pct = v["fraction_backbones_clear_of_surviving"]
        clear_s = "INCOMPLETE" if clear is None else str(clear)
        pct_s = "—" if pct is None else f"{pct*100:.1f}%"
        lines.append(f"| {key} | {v['backbones']} | {v['backbones_near_identical_to_surviving']} | "
                     f"{clear_s} | {pct_s} | {v['completeness']} | "
                     f"{v['backbones_near_identical_to_flagged']} |")
    lines += ["", "**Completeness.** A backbone counts as clear only when every survivor comparison was",
              "actually measured. If any comparison is absent from the frozen matrix, this table reports",
              "INCOMPLETE for that pool and makes no clearance claim (Astra, 07:45).", ""]
    lines += ["## What this does and does not settle", "",
              "**Does:** answers the replacement-side independence question with a measured number against the",
              "actual surviving set. A challenger selected from this fraction could avoid near-duplicating the",
              "surviving 12 under the frozen pairwise rule; whether it improves portfolio coverage or",
              "composition remains unestablished.",
              "**Does not:** change the gate, authorise a challenger, or establish binding/agonism. Any",
              "challenger remains RICARDO-APPROVAL. It also does not resolve the contested v7cc-vs-global",
              "independence-unit definition (dossier requirement 4), which stays a promotion blocker.",
              "", "Status: PROPOSED evidence only. No CSV written; v8 byte-identical.", ""]
    (OUT / "summary.md").write_text("\n".join(lines))
    print(json.dumps({k: {kk: vv for kk, vv in v.items() if kk != "per_backbone"}
                      for k, v in summary["pools"].items()}, indent=1))

if __name__ == "__main__":
    main()
