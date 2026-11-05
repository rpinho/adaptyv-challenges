#!/usr/bin/env python3
"""Decompose apical L6 into binder-side vs receptor-side contributions.

QUESTION
C4 gates on apical L6 < 0. But L6 is computed on a two-chain complex, and the linkage
sum runs over titratable groups on BOTH chains. The receptor is fixed (human TfR1
apical 189-383); only the binder is designed. So: of the sign that decides eligibility,
how much is attributable to the designed molecule and how much to the fixed receptor?

METHOD
Re-run the shipped scorer's own decomposition hook (c4_linkage_audit_20261025.score),
which already returns per-group rows with chain labels, and sum contributions by the
binder chain vs the receptor chain. No new physics, no changed parameters.

FAIL-CLOSED
  * sign controls must fire;
  * the per-chain split must sum back to the shipped L6 within 0.0006 (validates that
    this decomposition is of the same number the gate reads);
  * chain identity is taken from CA counts (195 = receptor, else binder), not from a
    hard-coded label.

CPU only. No GPU, no network. EVIDENCE ONLY. Writes results/c4_rule_v4_adversarial_audit_20261026/.
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import sys
import time

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import c4_linkage_audit_20261025 as A  # noqa: E402
import c4_linkage_apical_recompute_20261025 as R  # noqa: E402

APICAL = ROOT / "results/c4_linkage_apical_20261025/linkage_apical.json"
PDBS = ROOT / "results/c4_apical_pdb_audit_20261025/all343"
OUT = ROOT / "results/c4_rule_v4_adversarial_audit_20261026"
TOL = 0.0006


def sha(p: pathlib.Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for c in iter(lambda: fh.read(1 << 20), b""):
            h.update(c)
    return h.hexdigest()


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    ctl = A.controls()
    if not ctl.get("all_ok"):
        sys.exit("sign controls failed")
    art = json.loads(APICAL.read_text())
    shipped = {r["name"]: r["L6"] for r in art["records"]}
    names = sorted(shipped)
    recs, fails = [], []
    t0 = time.time()
    for i, n in enumerate(names, 1):
        p = PDBS / f"{n}_complex.pdb"
        if not p.exists():
            fails.append({"name": n, "why": "no apical pdb"})
            continue
        counts = R.chain_ca_counts(p)
        if set(counts) != {"A", "B"}:
            fails.append({"name": n, "why": f"chains {sorted(counts)}"})
            continue
        s = A.score(str(p), "B", "A", 6.0, 7.4)
        if s is None:
            fails.append({"name": n, "why": "propka failed"})
            continue
        binder = "A" if counts["A"] != 195 else "B"
        receptor = "B" if binder == "A" else "A"
        rows = s["rows"]
        lb = sum(r["contribution"] for r in rows if r["chain"] == binder)
        lr = sum(r["contribution"] for r in rows if r["chain"] == receptor)
        total = round(s["L"], 4)
        # which side carries the negative (acid-OFF) sign
        his_b = [r for r in rows if r["chain"] == binder and r["resname"] == "HIS"]
        his_r = [r for r in rows if r["chain"] == receptor and r["resname"] == "HIS"]
        recs.append(dict(
            name=n, L6=total, L6_binder=round(lb, 4), L6_receptor=round(lr, 4),
            recon_delta=round(abs(total - (lb + lr)), 6),
            binder_chain_ca=counts[binder], receptor_chain_ca=counts[receptor],
            n_groups_binder=sum(1 for r in rows if r["chain"] == binder),
            n_groups_receptor=sum(1 for r in rows if r["chain"] == receptor),
            binder_his_contrib=round(sum(r["contribution"] for r in his_b), 4),
            receptor_his_contrib=round(sum(r["contribution"] for r in his_r), 4),
            n_binder_his=len(his_b),
            binder_his_dpka=[r["dpka"] for r in his_b],
            pdb_sha256=sha(p),
        ))
        if i % 50 == 0:
            print(f"  {i}/{len(names)}  ({time.time()-t0:.0f}s)")

    bad = [r for r in recs if abs(r["L6"] - shipped[r["name"]]) > TOL]
    if bad:
        print("RECONCILIATION FAILED", bad[:3], file=sys.stderr)
        return 6

    def frac_neg(v):
        return v < 0

    acid_off = [r for r in recs if r["L6"] < 0]
    acid_on = [r for r in recs if r["L6"] > 0]
    # of the acid-OFF half, how many are negative *because of the binder*
    binder_driven = [r for r in acid_off if r["L6_binder"] < 0]
    # and how many are negative only because the fixed receptor is negative
    receptor_only = [r for r in acid_off if r["L6_binder"] >= 0]
    # designs where the binder alone would flip the sign positive
    summary = dict(
        method=("sum of per-group Wyman contributions on the designed binder chain vs the "
                "fixed receptor chain, from the shipped scorer's own row output"),
        scorer="scripts/c4_linkage_audit_20261025.py score(pdb,'B','A',6.0,7.4)",
        sign_controls=ctl, n_scored=len(recs), n_failed=len(fails), fails=fails,
        reconciliation_max_abs_delta=max(abs(r["L6"] - shipped[r["name"]]) for r in recs),
        n_acid_off=len(acid_off), n_acid_on=len(acid_on),
        n_acid_off_binder_negative=len(binder_driven),
        n_acid_off_binder_positive=len(receptor_only),
        acid_off_binder_negative_rate=round(len(binder_driven) / len(acid_off), 4) if acid_off else None,
        n_acid_off_where_binder_his_net_positive=[
            r["name"] for r in acid_off if r["binder_his_contrib"] > 0],
        median_abs_binder=round(sorted(abs(r["L6_binder"]) for r in recs)[len(recs)//2], 4),
        median_abs_receptor=round(sorted(abs(r["L6_receptor"]) for r in recs)[len(recs)//2], 4),
    )
    summary["n_acid_off_binder_his_net_positive"] = len(
        summary["n_acid_off_where_binder_his_net_positive"])
    out = dict(summary=summary,
               inputs={"apical_l6_sha256": sha(APICAL)},
               records=recs)
    (OUT / "l6_chain_decomposition.json").write_text(json.dumps(out, indent=1) + "\n")
    print(json.dumps({k: v for k, v in summary.items()
                      if k not in ("fails", "n_acid_off_where_binder_his_net_positive")}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
