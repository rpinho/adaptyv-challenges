#!/usr/bin/env python3
"""Derive HONEST iPTM fields per design — because `per_design.json.rank1_iptm` is mislabeled.

WHY THIS EXISTS
---------------
`results/c3_pool_five_model_20261025/per_design.json` exposes a key named `rank1_iptm`.
It is NOT the rank-001 model's iPTM. It is the MAXIMUM iPTM across all five archived AF2m models.

Measured consequence: every ceiling in this project that was computed from that field and described
as "rank-001 gated" is mislabeled. The numbers are arithmetically correct for the question
"best of five", which is a WEAKER claim than "rank-001".

This script writes a derived, additive file. It does NOT touch the frozen per_design.json.

Output: results/c3_sprint_8h_20261025/independent/iptm_fields_corrected.json
  per design:  max5_iptm | rank1_iptm_true | min5_iptm | n_models | rank1_iptm_field | field_is_max5

Usage: python3 scripts/c3_iptm_fields_corrected_20261025.py [--selfcheck]
CPU only, no GPU, no network.
"""
from __future__ import annotations

import collections
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
POOL5 = ROOT / "results/c3_pool_five_model_20261025/per_design.json"
OUT = ROOT / "results/c3_sprint_8h_20261025/independent/iptm_fields_corrected.json"
TOL = 1e-9


def all5_iptm(root: pathlib.Path) -> dict[str, dict[int, float]]:
    """Per design -> {RANK: iptm} from the archived score JSONs.

    CRITICAL: the filename encodes BOTH rank and model:
        <name>_scores_rank_001_alphafold2_multimer_v3_model_5_seed_000.json
    ``rank_001`` can be ``model_5``. Indexing by MODEL id is a bug: it returns the
    rank-002 model whenever ColabFold ranked model 5 first. Parse the RANK.
    """
    import re
    GOT: dict[str, dict[int, float]] = collections.defaultdict(dict)
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
            GOT[f.parent.name][int(mm.group(1))] = v
    return GOT


def build() -> dict:
    pool = json.load(open(POOL5))
    got = all5_iptm(ROOT)
    rows = []
    for r in pool:
        n = r["name"]
        m = got.get(n, {})
        field = r.get("rank1_iptm")
        rec = {
            "name": n,
            "n_models": len(m),
            "rank1_iptm_field": field,
            "max5_iptm": max(m.values()) if m else None,
            "rank1_iptm_true": m.get(1),
            "min5_iptm": min(m.values()) if m else None,
        }
        rec["field_equals_rank1"] = (
            None if (field is None or rec["rank1_iptm_true"] is None)
            else abs(field - rec["rank1_iptm_true"]) <= TOL
        )
        rec["field_is_max5"] = (
            None if (field is None or rec["max5_iptm"] is None)
            else abs(field - rec["max5_iptm"]) <= TOL
        )
        rows.append(rec)

    with5 = [r for r in rows if r["n_models"] >= 5]
    field_is_max5 = sum(1 for r in with5 if r["field_is_max5"])
    field_is_rank1 = sum(
        1 for r in with5
        if r["rank1_iptm_true"] is not None
        and r["rank1_iptm_field"] is not None
        and abs(r["rank1_iptm_field"] - r["rank1_iptm_true"]) <= TOL
    )
    diff = [r for r in with5 if not r["field_is_max5"]]
    worst = max(
        with5,
        key=lambda r: (r["rank1_iptm_field"] or 0) - (r["min5_iptm"] or 0),
    ) if with5 else None

    return {
        "note": (
            "`rank1_iptm` in per_design.json IS the rank-001 model's iPTM (83/83 verified). "
            "It also EQUALS the maximum of the five models for 82/83 designs, so a rank-1 iPTM "
            "gate behaves as a best-of-five gate in disguise. An earlier version of this file "
            "wrongly claimed the field was not rank-001; that was a model-vs-rank indexing bug."
        ),
        "source_pool": "results/c3_pool_five_model_20261025/per_design.json",
        "designs_total": len(rows),
        "designs_with_5_models": len(with5),
        "field_equals_max5": field_is_max5,
        "field_equals_true_rank1": field_is_rank1,
        "field_not_max5_count": len(diff),
        "field_not_max5": [r["name"] for r in diff],
        "worst_optimism": worst,
        "per_design": rows,
    }


def selfcheck(d: dict) -> int:
    """Assert the CORRECTED truth.

    History: v1 of this script indexed models by MODEL id and "found" the field differing
    from rank-001 for 36/83 designs. That was the bug, not the field. The archived filename
    is <name>_scores_rank_001_..._model_5_...: rank_001 is often model_5. Parsing rank gives
    83/83 agreement.
    """
    fails = []
    with5 = [r for r in d["per_design"] if r["n_models"] >= 5]
    if len(with5) == 0:
        fails.append("no designs with 5 models found")

    for r in with5:
        if r["max5_iptm"] + TOL < (r["rank1_iptm_true"] or 0):
            fails.append(f"{r['name']}: max5 < rank1_true")
        if r["max5_iptm"] + TOL < (r["min5_iptm"] or 0):
            fails.append(f"{r['name']}: max5 < min5")
        if r["min5_iptm"] - TOL > (r["rank1_iptm_true"] or 0):
            fails.append(f"{r['name']}: min5 > rank1_true")

    n_r1 = sum(1 for r in with5 if r.get("field_equals_rank1"))
    n_mx = sum(1 for r in with5 if r["field_is_max5"])
    n_diff = sum(
        1 for r in with5
        if r["rank1_iptm_true"] is not None
        and r["rank1_iptm_field"] is not None
        and abs(r["rank1_iptm_field"] - r["rank1_iptm_true"]) > TOL
    )

    # 1. the field IS rank-001: must hold for every design
    if n_r1 != len(with5):
        fails.append(f"field != true rank-001 for {len(with5)-n_r1} designs; expected 0")
    # 2. rank-001 == max-of-five for all but a handful
    if n_mx < len(with5) - 3:
        fails.append(f"field == max5 only {n_mx}/{len(with5)}, expected >= len-3")
    # 3. and NOT the 36 this script wrongly reported
    if n_diff > 3:
        fails.append(f"field != rank-001 for {n_diff}; the 36/83 claim was a MODEL-INDEXING BUG")

    print(f"designs with 5 models      : {len(with5)}")
    print(f"field == true rank-001     : {n_r1}/{len(with5)}   <-- must be all")
    print(f"rank-001 == max-of-five    : {n_mx}/{len(with5)}")
    print(f"field != true rank-001     : {n_diff}/{len(with5)}   <-- was falsely 36/83")
    if fails:
        print("\nSELFCHECK FAIL:")
        for f in fails:
            print("  -", f)
        return 1
    print("\nSELFCHECK PASS")
    return 0


def main() -> int:
    d = build()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(d, indent=1) + "\n")
    print(f"wrote {OUT.relative_to(ROOT)}")
    if "--selfcheck" in sys.argv:
        return selfcheck(d)
    print(json.dumps({k: v for k, v in d.items() if k != "per_design"}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
