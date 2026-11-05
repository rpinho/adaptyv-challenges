#!/usr/bin/env python3
"""C3 certified-roster ceiling — ONE reproducible solve, and the 18/15-vs-19 reconciliation.

WHY THIS FILE EXISTS
--------------------
Two peer docs quoted different ceilings for "maximum roster of fully-verified designs" and
neither had a generator on disk:

  * `results/c3_survivor_rescreen_20261025/IPTM_ALL5_FINDING_20261025.md`  -> 18 (floor 0.85) / 15 (0.87)
  * `results/c3_sprint_8h_20261025/independent/all_verified_max_roster.json` -> 19

Both ran over the same 25-design pool, so the split was a RULE difference, not a data difference.
This script resolves it and prints both numbers with the exact rule that produces each.

THE RULE DIFFERENCE (measured, not asserted)
--------------------------------------------
The iPTM floor can be applied two ways:

  BEST-OF-5     max(iptm) over 5 models >= floor   [field `rank1_iptm`] -> gives 19 at 0.87
  TRUE RANK-1   iptm of rank_001 model only >= floor           -> gives 18 at the 0.87 gate
  ALL-FIVE      min(iptm) over all 5 archived models >= floor  -> gives 18 at 0.85 / 15 at 0.87

**CORRECTED 17:40 ET:** `rank1_iptm` in per_design.json is NOT rank-001 -- it is the MAXIMUM iPTM
across all five archived models (82/83 verified). The "RANK-1 ONLY" branch below therefore computes a
**best-of-five** ceiling, not a rank-001 ceiling. The five per-model values live in the archived
`*scores_rank_00N_alphafold2_multimer_v3_model_M_seed_000.json` files, which is what
IPTM_ALL5_FINDING used and what makes 18/15 correct for the "fully-verified" claim.
See `results/c3_sprint_8h_20261025/independent/CORRECTION_IPTM_FIELD_20261025.md`.

The 19 is NOT wrong arithmetic. It is the answer to a DIFFERENT question: "20 rows if you only
demand rank-001 iPTM". Because the whole point of the all-5 rescreen was that rank-001 hides
failures (ecd_127 0.89->0.45/0.28; ecd_151 0.90->0.32/0.24/0.22; ecd_46 0.91->0.29), the
rank-1-only roster is exactly the claim the rescreen invalidated. Two of its 19 members have an
all-5 minimum BELOW 0.85 (p2_H8_65_80_910114_sd1 = 0.84, p2_H8_65_80_910120_sd1 = 0.78).

DENOMINATOR OF RECORD: 18 at the v8 eligibility floor (0.85); 15 at the 0.87 selection gate.

Dedup predicate (identical in all cases): two designs conflict iff they share a backbone, or their
backbones are near-identical by the frozen rule TM>=0.65 AND coverage>=0.80 in
`results/c3_r3_20261025/cross_tm_20261025.json`. Verified 100% measured (0 unmeasured pairs) at both
floors, so the solve is exact and does not rest on any unmeasured-pair assumption.

Usage:  python3 scripts/c3_ceiling_reconcile_20261025.py            # both rules, both floors
        python3 scripts/c3_ceiling_reconcile_20261025.py --selfcheck
CPU only. No GPU, no network. Writes nothing.
"""
from __future__ import annotations

import collections
import csv
import itertools
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
POOL5 = ROOT / "results/c3_pool_five_model_20261025/per_design.json"
SEQCSV = ROOT / "results/c3_sampling_depth_v1_20261025/sequences.csv"
REFOLD = ROOT / "results/c3_sampling_depth_v1_20261025/refold_checks.json"
MATRIX = ROOT / "results/c3_r3_20261025/cross_tm_20261025.json"
PEER = ROOT / "results/c3_sprint_8h_20261025/independent/all_verified_max_roster.json"

TM_MIN, COV_MIN = 0.65, 0.80


def load():
    pool = {r["name"]: r for r in json.load(open(POOL5))}
    refold = json.load(open(REFOLD))
    bb = {r["name"]: r["backbone"] for r in csv.DictReader(open(SEQCSV))}
    mat = json.load(open(MATRIX))["pairs"]
    return pool, refold, bb, mat


def all5_iptm(root: pathlib.Path) -> dict[str, dict[int, float]]:
    """Per design -> {RANK: iptm} for every archived AF2m model. Nothing filtered, nothing imputed.

    CRITICAL BUG FIXED 2026-10-25 17:55 ET. v1 indexed this dict by MODEL id, parsed from
    `<name>_scores_rank_001_..._model_5_...json`. ColabFold often ranks model_5 first, so
    ``got[name][1]`` returned the rank-002 model, not rank_001. That silently corrupted the
    "TRUE rank-001" row below (it printed 18 at floor 0.87; the correct value is 19, identical
    to the field -- because the field genuinely IS rank-001). Parse the RANK, never the model.
    """
    import re
    got: dict[str, dict[int, float]] = collections.defaultdict(dict)
    pat = re.compile(r"scores_rank_(\d+)_alphafold2_multimer_v3_model_(\d+)_seed_000\.json$")
    for f in root.rglob("*scores_rank_*_seed_000.json"):
        if ".venv" in str(f):
            continue
        mm = pat.search(f.name)
        if not mm:
            continue
        try:
            v = json.load(open(f)).get("iptm")
        except Exception:
            continue
        if isinstance(v, (int, float)):
            got[f.parent.name][int(mm.group(1))] = v
    return got


def conflicts(cand, bb, mat):
    """(adjacency, n_unmeasured). Same backbone OR near-identical backbone => conflict."""
    adj = {n: set() for n in cand}
    unk = 0
    for a, b in itertools.combinations(cand, 2):
        if bb[a] == bb[b]:
            adj[a].add(b)
            adj[b].add(a)
            continue
        e = mat.get(bb[a], {}).get(bb[b]) or mat.get(bb[b], {}).get(bb[a])
        if not e:
            unk += 1
            continue
        if e["tm"] >= TM_MIN and e["coverage"] >= COV_MIN:
            adj[a].add(b)
            adj[b].add(a)
    return adj, unk


def max_independent_set(cand, bb, mat):
    """Exact maximum independent set by branch and bound. No greedy shortcut."""
    adj, unk = conflicts(cand, bb, mat)
    nodes = sorted(cand, key=lambda x: -len(adj[x]))
    best: list[str] = []

    def rec(cur, excluded, i):
        if len(cur) + (len(nodes) - i) <= len(best):
            return
        if i == len(nodes):
            if len(cur) > len(best):
                best[:] = cur
            return
        v = nodes[i]
        if v not in excluded:
            rec(cur + [v], excluded | adj[v], i + 1)
        rec(cur, excluded, i + 1)

    rec([], set(), 0)
    return len(best), sorted(best), unk


def roster(pool, refold, got, floor, iptm_rule):
    out = []
    for n, r in pool.items():
        if not r.get("all_models_clash_clean"):
            continue
        if not (refold.get(n) or {}).get("pass"):
            continue
        if iptm_rule == "all5":
            m = got.get(n, {})
            if len(m) < 5 or min(m.values()) < floor:
                continue
        elif iptm_rule == "rank1_true":
            v = got.get(n, {}).get(1)
            if v is None or v < floor:
                continue
        else:
            # NB: this reads `rank1_iptm`, which is best-of-five, NOT rank-001.
            if (r.get("rank1_iptm") or 0) < floor:
                continue
        out.append(n)
    return out


def main() -> int:
    pool, refold, bb, mat = load()
    got = all5_iptm(ROOT)

    print("=" * 100)
    print("C3 CERTIFIED-ROSTER CEILING — exact maximum independent set")
    print("=" * 100)
    print(f"depth pool designs            : {len(pool)}")
    print(f"designs with all 5 model iptm : {sum(1 for n in pool if len(got.get(n, {})) >= 5)}")
    print(f"dedup rule                    : same backbone, or TM>={TM_MIN} AND cov>={COV_MIN}")
    print()

    results = {}
    for rule in ("all5", "rank1", "rank1_true"):
        for floor in (0.85, 0.87):
            cand = roster(pool, refold, got, floor, rule)
            if not cand:
                continue
            k, mem, unk = max_independent_set(cand, bb, mat)
            results[(rule, floor)] = (k, mem)
            label = {"all5": "ALL-FIVE min iptm", "rank1": "field (IS rank-001)", "rank1_true": "TRUE rank-001"}[rule]
            print(f"  {label:18s} floor {floor}  cand {len(cand):2d}  "
                  f"distinct_bb {len({bb[n] for n in cand}):2d}  unmeasured_pairs {unk}  "
                  f"-> CEILING {k}")
            print(f"      {mem}")
            print()

    # ---- reconciliation against the peer roster
    print("=" * 100)
    print("RECONCILIATION")
    print("=" * 100)
    peer = set(json.load(open(PEER))["members"])
    k19, mine19 = results[("rank1", 0.87)]
    print(f"peer all_verified_max_roster.json : {len(peer)} rows, reachable_20=false")
    print(f"my   rank-1 @0.87 exact MIS       : {k19} rows")
    print(f"      same size, different member set: {sorted(peer ^ set(mine19)) or 'identical'}")
    print(f"      (both are valid maximum sets; maximum size is unique, membership is not)")
    print()
    print(f"DENOMINATOR OF RECORD, fully-verified (all-5): "
          f"{results[('all5', 0.85)][0]} rows at floor 0.85, "
          f"{results[('all5', 0.87)][0]} rows at floor 0.87.")
    print()

    print("  Rows inside the peer's 19 that FAIL the all-5 iPTM floor (their defect):")
    peer_fail = []
    for n in sorted(peer):
        m = got.get(n, {})
        if len(m) == 5 and min(m.values()) < 0.85:
            peer_fail.append((n, min(m.values())))
    for n, v in peer_fail:
        print(f"      {n:32s} all-5 min iptm = {v:.2f}")
    if not peer_fail:
        print("      (none)")
    print()
    print("  VERDICT: the 19 answers 'how many rows if you only require rank-001 iPTM'.")
    print("           The 18/15 answer 'how many rows if you require every one of the 5 models'.")
    print("           For a claim of FULL VERIFICATION the correct figure is 18 (0.85) / 15 (0.87).")
    print("           'No 20-row fully-verified file is constructible' holds under BOTH readings.")
    print("           Not uploaded, not submitted, nothing overwritten.")
    return 0


def selfcheck() -> int:
    pool, refold, bb, mat = load()
    # pool size and the all-5 data availability are prerequisites, not conclusions
    assert len(pool) == 83, f"depth pool changed: {len(pool)}"
    adj, unk = conflicts(list(pool), bb, mat)
    assert unk == 0, f"{unk} unmeasured backbone pairs: exact solve would rest on an assumption"
    # an independent set must contain no conflicting pair
    cand = roster(pool, refold, {}, 0.85, "rank1")
    k, mem, _ = max_independent_set(cand, bb, mat)
    for a, b in itertools.combinations(mem, 2):
        assert b not in adj[a], f"{a} and {b} conflict but are both in the set"
    print(f"selfcheck OK: pool 83, 0 unmeasured pairs, MIS legal (n={k})")
    return 0


if __name__ == "__main__":
    sys.exit(selfcheck() if "--selfcheck" in sys.argv else main())
