#!/usr/bin/env python3
"""Reproduce C4 L6 on the CORRECT 195-residue apical complexes.

WHY THIS EXISTS
The shipped C4 ranking (`results/c4_selection_audit_20261025/audit.json`) computed L6 from
results/c4_rebuild_20261024/remote_pdbs/ -- a 154-residue stitched receptor surrogate. The designs
were ranked on 195-residue apical iPTM. That mixes constructs in one ranking criterion.

This script re-scores every archived apical complex with the SAME scorer and parameters as the
original audit (`scripts/c4_linkage_audit_20261025.py`: chain B = binder, chain A = target,
pH 6.0 vs 7.4, min shift 0.1, PROPKA3). It does not change any scoring rule. It changes only which
receptor PDB is read.

FAIL-CLOSED
  * sign controls must pass before scoring anything real;
  * every PDB must have exactly 2 chains and a 195-CA receptor chain;
  * a design with a missing/unreadable complex is reported MISSING, never scored as 0;
  * every scored row is written with its receptor-chain length and input PDB sha256.

The 342 scored designs are all designs with an apical complex. `tfr1_c4_acid_site1_41` timed out in
the apical run and has no apical PDB; it remains explicitly MISSING and is never imputed.

By default this script VERIFIES the existing artifact and writes nothing. Pass --write to regenerate
it. Verification compares L6 to 0.0006 absolute (the artifact stores 4 decimals).

Read-only on inputs. CPU only. No GPU, no network.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import c4_linkage_audit_20261025 as A  # noqa: E402

APICAL_PDBS = ROOT / "results/c4_apical_pdb_audit_20261025/all343"
CONSOLIDATED = ROOT / "results/c4_apical_consolidated_results.json"
OUTDIR = ROOT / "results/c4_linkage_apical_20261025"
ARTIFACT = OUTDIR / "linkage_apical.json"
EXPECTED_RECEPTOR_CA = 195
# IMPORTANT: the original scorer's labels are inverted relative to construct semantics.
# In these complexes chain B is the 195-residue RECEPTOR and chain A is the ~70-residue BINDER.
# A.score(pdb, "B", "A") was the historical call and is preserved exactly so L6 is comparable.
# The labels only name which isolated chain is written to which temp file; the linkage itself
# sums over every titratable group present in both bound and free states on both chains.
SCORER_BINDER_LABEL = "B"
SCORER_TARGET_LABEL = "A"
RECEPTOR_CHAIN = "B"
BINDER_CHAIN = "A"


def chain_ca_counts(pdb: pathlib.Path) -> dict[str, int]:
    """Count CA atoms per chain from ATOM records only. No parsing heuristics."""
    counts: dict[str, int] = {}
    seen = set()
    with open(pdb) as fh:
        for line in fh:
            if not line.startswith("ATOM") or line[12:16].strip() != "CA":
                continue
            chain = line[21]
            key = (chain, line[22:26].strip(), line[26])
            if key in seen:
                continue
            seen.add(key)
            counts[chain] = counts.get(chain, 0) + 1
    return counts


def sha256(p: pathlib.Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--write", action="store_true", help="regenerate the artifact (default: verify only)")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    ctl = A.controls()
    print("sign controls:", json.dumps(ctl))
    if not ctl.get("all_ok"):
        print("SIGN CONTROLS FAILED - refusing to score", file=sys.stderr)
        return 3

    cons = json.loads(CONSOLIDATED.read_text())
    if cons.get("target_len") != EXPECTED_RECEPTOR_CA or cons.get("target") != "P02786_189-383_contiguous":
        print(f"consolidated target mismatch: {cons.get('target')} len={cons.get('target_len')}",
              file=sys.stderr)
        return 4

    all_names = [r["name"] for r in cons["results"]]
    errored = [{"name": r["name"], "error": r.get("error")} for r in cons["results"] if r.get("error")]
    design_names = [r["name"] for r in cons["results"] if not r.get("error")]
    pdbs = {f.name.removesuffix("_complex.pdb"): f for f in APICAL_PDBS.glob("*_complex.pdb")}
    missing_pdb = sorted(set(design_names) - set(pdbs))
    unexpected = sorted(set(pdbs) - set(design_names))
    if unexpected:
        print(f"PDBs without a consolidated design: {unexpected[:5]}", file=sys.stderr)
        return 5

    prior = {}
    if ARTIFACT.exists():
        prior = {r["name"]: r for r in json.loads(ARTIFACT.read_text())["records"]}

    names = sorted(pdbs) if not args.limit else sorted(pdbs)[: args.limit]
    records, fails = [], []
    for i, name in enumerate(names, 1):
        p = pdbs[name]
        counts = chain_ca_counts(p)
        if set(counts) != {RECEPTOR_CHAIN, BINDER_CHAIN}:
            fails.append({"name": name, "why": f"chains {sorted(counts)}"})
            continue
        if counts[RECEPTOR_CHAIN] != EXPECTED_RECEPTOR_CA:
            fails.append({"name": name, "why": f"receptor CA {counts[RECEPTOR_CHAIN]} != {EXPECTED_RECEPTOR_CA}"})
            continue
        s = A.score(str(p), SCORER_BINDER_LABEL, SCORER_TARGET_LABEL, 6.0, 7.4)
        if s is None:
            fails.append({"name": name, "why": "propka failed"})
            continue
        meta = next(r for r in cons["results"] if r["name"] == name)
        records.append(dict(name=name, L6=round(s["L"], 4), n_groups=s["n_groups"],
                            iptm=meta.get("iptm"), binder_ca=counts[BINDER_CHAIN],
                            receptor_ca=counts[RECEPTOR_CHAIN], pdb_sha256=sha256(p)))
        if i % 25 == 0:
            print(f"  scored {i}/{len(names)}")

    out = {"note": "L6 recomputed on the CORRECT 195-residue apical complexes",
           "method": "scripts/c4_linkage_audit_20261025.py score(); binder chain B, target chain A, pH 6.0/7.4",
           "source": "results/c4_apical_pdb_audit_20261025/all343",
           "target": cons["target"], "target_len": cons["target_len"],
           "sign_controls": ctl, "n": len(records), "fails": fails,
           "n_consolidated": len(all_names), "n_scored_designs": len(design_names),
           "designs_without_apical_pdb": [r["name"] for r in errored],
           "errored_in_consolidated": errored,
           "missing_apical_pdb_for_scored_design": missing_pdb, "records": records}

    if not args.write:
        problems = []
        if len(records) != len(names):
            problems.append(f"scored {len(records)}/{len(names)}")
        for r in records:
            old = prior.get(r["name"])
            if old is None:
                problems.append(f"not in artifact: {r['name']}")
            elif abs(old["L6"] - r["L6"]) > 0.0006:
                problems.append(f"{r['name']}: artifact {old['L6']} vs fresh {r['L6']}")
        if problems:
            print("VERIFY FAILED:", file=sys.stderr)
            for x in problems[:20]:
                print("  " + x, file=sys.stderr)
            return 6
        npos = sum(1 for r in records if r["L6"] > 0)
        print(f"VERIFY OK: {len(records)}/{len(names)} reproduced within 0.0006; "
              f"positive {npos}/{len(records)}; without apical PDB "
              f"{[r['name'] for r in errored]}")
        return 0

    OUTDIR.mkdir(parents=True, exist_ok=True)
    ARTIFACT.write_text(json.dumps(out, indent=1) + "\n")
    print(f"wrote {ARTIFACT.relative_to(ROOT)} ({len(records)} rows, {len(fails)} fails; "
          f"without apical PDB: {[r['name'] for r in errored]})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
