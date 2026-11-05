#!/usr/bin/env python3
"""Read-only feasibility audit for Astra's proposed 12-design C4 native pilot.

Question: do six distinct acid-OFF controls exist that satisfy the same
iPTM, 2.0 A distance, and deduplication screens as the ranked candidates, and
can they be matched one-to-one by target site?

The candidate sample is fixed by Astra's ruling as ranked positions
2, 6, 10, 13, 16 and 20 from the frozen 20-row L6-ranked file.

This script does NOT create or freeze a native-validation cohort. It writes a
feasibility record and a PROPOSED, NOT FROZEN control assignment. Nothing is
launched, submitted, or promoted.

Fail-closed checks:
  * frozen ranked CSV hash must match the recorded value;
  * the CSV order and the manifest's chosen_by_L6 order must agree;
  * every candidate and control must resolve to a canonical PDB with two chains;
  * the linkage sign controls in the selection audit must pass.

Deduplication uses the corrected symmetric predicate: TM = max(both
directions), coverage = paired columns / max(sequence lengths), with the frozen
threshold TM >= 0.65 AND coverage >= 0.80. Controls are required to be
independent of every ranked design and of each other.
"""
from __future__ import annotations

import csv
import hashlib
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from c3_clash_audit_independent_20261025 import (  # noqa: E402
    clashing_pairs,
    min_interchain_distance,
    parse_pdb,
)
from c4_rank_v2_sensitivity_20261025 import load_cw, v2_compare  # noqa: E402

RANKED = ROOT / "results/c4_ranked_20261025/c4_acid_ranked_20261025.csv"
RANKED_JSON = ROOT / "results/c4_ranked_20261025/c4_acid_ranked_20261025.json"
AUDIT = ROOT / "results/c4_selection_audit_20261025/audit.json"
PDB_DIR = ROOT / "results/c4_rebuild_20261024/remote_pdbs"
OUT = ROOT / "results/c4_native_pilot_control_feasibility_20261025"

RANKED_SHA = "3370909acebba7300e017f468107ff8f8ebd57c3463b7186a6a9e51b0a9d0a6f"
PILOT_RANKS = (2, 6, 10, 13, 16, 20)
IPTM_FLOOR = 0.60
DIST_FLOOR = 2.0
TM_MIN = 0.65
COV_MIN = 0.80


def sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def site_of(name: str) -> str:
    if "_site1_" in name:
        return "site1"
    if "_site2_" in name:
        return "site2"
    raise SystemExit(f"cannot determine target site for {name}")


def pdb_for(name: str) -> pathlib.Path:
    p = PDB_DIR / f"{name}_complex.pdb"
    if not p.exists():
        raise SystemExit(f"missing canonical PDB for {name}: {p}")
    return p


def measure_structure(name: str, cw) -> dict:
    p = pdb_for(name)
    chains = parse_pdb(p)
    if len(chains) != 2:
        raise SystemExit(f"{name}: {len(chains)} chains, expected 2")
    order = sorted(chains, key=lambda c: len(chains[c]))
    binder, target = chains[order[0]], chains[order[1]]
    pairs = clashing_pairs(binder, target, DIST_FLOOR)
    d_min, atom_a, atom_b = min_interchain_distance(binder, target, 6.0)
    rec = cw.load(p, name)
    if rec is None:
        raise SystemExit(f"{name}: fewer than 20 CA atoms")
    return {
        "name": name,
        "pdb": str(p.relative_to(ROOT)),
        "n_chains": len(chains),
        "n_clash_pairs": len(pairs),
        "clash_clean": not pairs,
        "d_min_A": d_min,
        "closest_atoms": [atom_a, atom_b] if atom_a else None,
        "_struct": rec,
    }


def near(a: dict, b: dict) -> dict | None:
    c = v2_compare(a["_struct"], b["_struct"])
    if c and c["tm"] >= TM_MIN and c["coverage"] >= COV_MIN:
        return c
    return None


def assignments(cands: list[dict], controls: list[dict],
                incompatible: set[frozenset[str]]) -> list[dict]:
    """All injective, mutually independent control->candidate assignments for one site."""
    out = []

    def walk(i: int, used: set[str], chosen: list[tuple[dict, dict]], iptm_sum: float,
             dist_sum: float, selected_controls: list[dict]) -> None:
        if i == len(cands):
            out.append({
                "pairs": list(chosen),
                "iptm_sum": iptm_sum,
                "dist_sum": dist_sum,
                "score": (round(iptm_sum, 6), round(dist_sum, 6),
                          tuple((c["rank"], k["name"]) for c, k in chosen)),
            })
            return
        cand = cands[i]
        for ctl in controls:
            if ctl["name"] in used:
                continue
            if any(frozenset((ctl["name"], prior["name"])) in incompatible
                   for prior in selected_controls):
                continue
            used.add(ctl["name"])
            chosen.append((cand, ctl))
            selected_controls.append(ctl)
            walk(i + 1, used, chosen,
                 iptm_sum + abs(cand["iptm"] - ctl["iptm"]),
                 dist_sum + abs(cand["d_min_A"] - ctl["d_min_A"]),
                 selected_controls)
            selected_controls.pop()
            chosen.pop()
            used.remove(ctl["name"])

    walk(0, set(), [], 0.0, 0.0, [])
    return out


def main() -> int:
    got = sha256(RANKED)
    if got != RANKED_SHA:
        print(f"FAIL: ranked CSV hash {got} != {RANKED_SHA}", file=sys.stderr)
        return 2

    with RANKED.open(newline="") as fh:
        ranked_rows = list(csv.DictReader(fh))
    meta = json.loads(RANKED_JSON.read_text())
    if [r["name"] for r in ranked_rows] != [r["name"] for r in meta["chosen_by_L6"]]:
        print("FAIL: ranked CSV order disagrees with chosen_by_L6", file=sys.stderr)
        return 2

    audit = json.loads(AUDIT.read_text())
    if not audit["summary"]["sign_controls"].get("all_ok"):
        print("FAIL: linkage sign controls did not pass", file=sys.stderr)
        return 2
    records = {r["name"]: r for r in audit["records"]}
    by_rank = {r["rank"]: r for r in meta["chosen_by_L6"]}

    cands = []
    for rank in PILOT_RANKS:
        row = by_rank[rank]
        rec = records[row["name"]]
        cands.append({
            "rank": rank,
            "name": row["name"],
            "site": site_of(row["name"]),
            "iptm": float(rec["iptm"]),
            "L6": float(rec["L6"]),
            "d_min_A": float(row["d_min_A"]),
        })
    if not all(c["L6"] > 0 and c["iptm"] >= IPTM_FLOOR and c["d_min_A"] >= DIST_FLOOR
               for c in cands):
        print("FAIL: a pilot candidate does not satisfy the frozen selection rule", file=sys.stderr)
        return 2

    ranked_names = {r["name"] for r in ranked_rows}
    cw = load_cw()

    ranked_struct = {}
    for name in sorted(ranked_names):
        ranked_struct[name] = measure_structure(name, cw)["_struct"]

    pool, excluded = [], []
    for name, rec in sorted(records.items()):
        if name in ranked_names:
            continue
        if rec.get("iptm") is None or rec.get("L6") is None:
            excluded.append({"name": name, "why": "missing iPTM or L6"})
            continue
        if rec["L6"] > 0:
            continue
        if rec["iptm"] < IPTM_FLOOR:
            continue
        m = measure_structure(name, cw)
        if not m["clash_clean"]:
            excluded.append({"name": name, "why": "rank-001 clash under 2.0 A screen",
                             "n_clash_pairs": m["n_clash_pairs"], "d_min_A": m["d_min_A"]})
            continue
        hits = []
        for rn, rs in ranked_struct.items():
            c = v2_compare(m["_struct"], rs)
            if c and c["tm"] >= TM_MIN and c["coverage"] >= COV_MIN:
                hits.append({"ranked": rn, **c})
        if hits:
            excluded.append({"name": name, "why": "near-identical to a ranked design",
                             "hits": hits})
            continue
        pool.append({
            "name": name,
            "site": site_of(name),
            "iptm": float(rec["iptm"]),
            "L6": float(rec["L6"]),
            "d_min_A": m["d_min_A"],
            "closest_atoms": m["closest_atoms"],
            "_struct": m["_struct"],
        })

    site1 = [c for c in pool if c["site"] == "site1"]
    site2 = [c for c in pool if c["site"] == "site2"]
    need1 = sum(c["site"] == "site1" for c in cands)
    need2 = sum(c["site"] == "site2" for c in cands)
    feasible_by_count = len(site1) >= need1 and len(site2) >= need2

    proposal = None
    pair_details = []
    n_assign1 = n_assign2 = 0
    if feasible_by_count:
        c1 = [c for c in cands if c["site"] == "site1"]
        c2 = [c for c in cands if c["site"] == "site2"]
        incompatible = {frozenset((a["name"], b["name"]))
                        for i, a in enumerate(pool) for b in pool[i + 1:] if near(a, b)}
        a1 = assignments(c1, site1, incompatible)
        a2 = assignments(c2, site2, incompatible)
        n_assign1, n_assign2 = len(a1), len(a2)
        best = None
        for x in a1:
            for y in a2:
                if any(frozenset((k1["name"], k2["name"])) in incompatible
                       for _, k1 in x["pairs"] for _, k2 in y["pairs"]):
                    continue
                score = (round(x["iptm_sum"] + y["iptm_sum"], 6),
                         round(x["dist_sum"] + y["dist_sum"], 6),
                         tuple((c["rank"], k["name"]) for c, k in x["pairs"] + y["pairs"]))
                if best is None or score < best[0]:
                    best = (score, x["pairs"] + y["pairs"])
        if best is not None:
            proposal = []
            for cand, ctl in sorted(best[1], key=lambda p: p[0]["rank"]):
                proposal.append({
                    "candidate_rank": cand["rank"],
                    "candidate": cand["name"],
                    "candidate_iptm": cand["iptm"],
                    "candidate_d_min_A": cand["d_min_A"],
                    "site": cand["site"],
                    "control": ctl["name"],
                    "control_iptm": ctl["iptm"],
                    "control_L6": ctl["L6"],
                    "control_d_min_A": ctl["d_min_A"],
                    "abs_iptm_diff": round(abs(cand["iptm"] - ctl["iptm"]), 4),
                    "abs_dist_diff_A": round(abs(cand["d_min_A"] - ctl["d_min_A"]), 4),
                })
            pair_details = proposal

    summary = {
        "audit": "c4_native_pilot_control_feasibility_20261025",
        "status": "READ-ONLY FEASIBILITY AUDIT - no cohort frozen, no compute launched",
        "question": "Do six site-matched acid-OFF controls exist for Astra's 12-design pilot?",
        "pilot_candidates": cands,
        "pilot_ranks": list(PILOT_RANKS),
        "control_definition": {
            "source": "the same 343-design scored pool",
            "L6": "<= 0 (acid-OFF by the audit's sign convention)",
            "iptm_floor": IPTM_FLOOR,
            "distance_floor_A": DIST_FLOOR,
            "dedup": "symmetric max-TM and true paired coverage; near if TM>=0.65 and coverage>=0.80",
            "independence": "control must be independent of every ranked design and every other selected control",
            "site_matching": "one-to-one within target site",
            "matching_objective": "minimize total absolute iPTM difference, then total absolute d_min difference, then identifiers",
        },
        "pool": {
            "n_ranked": len(ranked_names),
            "n_controls_after_all_screens": len(pool),
            "site1": len(site1),
            "site2": len(site2),
            "needed_site1": need1,
            "needed_site2": need2,
            "feasible_by_count": feasible_by_count,
        },
        "excluded_candidates_for_control_role": excluded,
        "eligible_controls": [{k: v for k, v in c.items() if k != "_struct"} for c in pool],
        "assignment_counts": {"site1": n_assign1, "site2": n_assign2},
        "proposed_assignment": proposal,
        "proposal_is_not_frozen": True,
        "limitations": [
            "This tests control availability only; it is not evidence that any design binds or releases at a particular pH.",
            "The 2.0 A distance screen is atom-type-blind and permissive.",
            "All structures are predicted; no native result exists.",
            "The candidate sample is a fixed diagnostic set, not a statistically representative sample of all 20.",
            "Structural deduplication does not establish statistical independence of matched pairs.",
            "A control-free-of-ranked-near-duplicates requirement is stricter than Astra's minimum wording; it prevents the pilot comparison from reusing a ranked scaffold.",
        ],
        "input_hashes": {"ranked_csv": got},
    }

    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "feasibility.json").write_text(json.dumps(summary, indent=1) + "\n")

    if proposal:
        with (OUT / "proposed_controls_NOT_FROZEN.csv").open("w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=list(proposal[0]))
            w.writeheader()
            w.writerows(proposal)

    lines = [
        "# C4 native pilot — control feasibility audit",
        "",
        "**READ-ONLY. No cohort frozen, no native run launched, nothing submitted.**",
        "",
        "Tests whether the six acid-OFF controls specified by Astra exist in the stored 343-design pool.",
        "",
        "## Result",
        "",
        f"- eligible controls after all screens: **{len(pool)}** "
        f"(site1 **{len(site1)}**, site2 **{len(site2)}**)",
        f"- pilot need: site1 **{need1}**, site2 **{need2}**",
        f"- feasible by count: **{'YES' if feasible_by_count else 'NO'}**",
        f"- injective site-local assignments: site1 **{n_assign1}**, site2 **{n_assign2}**",
        f"- matched six-pair assignment found: **{'YES' if proposal else 'NO'}**",
        "",
    ]
    if proposal:
        lines += [
            "## Proposed matching (NOT FROZEN)",
            "",
            "| rank | candidate | site | iPTM | d_min (A) | control | iPTM | d_min (A) | |diPTM| | |dd| |",
            "|---:|---|---|---:|---:|---|---:|---:|---:|---:|",
        ]
        for p in proposal:
            lines.append(
                f"| {p['candidate_rank']} | `{p['candidate']}` | {p['site']} | "
                f"{p['candidate_iptm']:.3f} | {p['candidate_d_min_A']:.3f} | "
                f"`{p['control']}` | {p['control_iptm']:.3f} | {p['control_d_min_A']:.3f} | "
                f"{p['abs_iptm_diff']:.3f} | {p['abs_dist_diff_A']:.3f} |"
            )
        lines += [
            "",
            f"- total absolute iPTM difference: **{sum(p['abs_iptm_diff'] for p in proposal):.3f}**",
            f"- total absolute distance difference: **{sum(p['abs_dist_diff_A'] for p in proposal):.3f} A**",
            f"- largest single iPTM gap: **{max(p['abs_iptm_diff'] for p in proposal):.3f}**",
            "",
        ]
    lines += [
        "## Scope",
        "",
        "This establishes availability and a deterministic matching under the stated screens. "
        "It does not establish experimental binding, pH selectivity, or that the pilot will be adequately powered.",
        "",
        "Deduplication uses the corrected symmetric rule (max-TM, true paired coverage), not the shipped "
        "directional predicate. Controls are also required to be independent of all 20 ranked designs, "
        "which is stricter than the minimum wording and prevents scaffold reuse.",
        "",
        "The proposed identities are **not frozen**. Freezing them requires a decision record and, before "
        "any native work, a validated port plus Ricardo's authorization.",
        "",
        f"Input: ranked CSV `{got}`.",
    ]
    (OUT / "feasibility.md").write_text("\n".join(lines) + "\n")

    print(f"eligible controls {len(pool)} (site1 {len(site1)}, site2 {len(site2)}); "
          f"need {need1}/{need2}; feasible={feasible_by_count}; proposal={bool(proposal)}")
    if proposal:
        print(f"assignment: site1={n_assign1}, site2={n_assign2}; "
              f"sum|diptm|={sum(p['abs_iptm_diff'] for p in proposal):.3f}; "
              f"max|diptm|={max(p['abs_iptm_diff'] for p in proposal):.3f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
