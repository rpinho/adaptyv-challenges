#!/usr/bin/env python3
"""E3 novelty CROSS-CHECK — an independent second implementation of the novelty metric.

The E3 lane owns `results/c3_e3_111_20261025/novelty_20261025.json`
(`scripts/c3_e3_recover_novelty_20261025.py`). This tool must NOT overwrite it: it writes
`novelty_independent_20261025.json` alongside, so the two implementations can be compared.
Agreement is evidence; a disagreement is a finding.

Astra's E3 acceptance is "novel eligible designs per generated backbone and GPU-hour", not max
iPTM. This tool computes exactly that first half on CPU, from the designed backbones:

  * TM-align every E3 backbone against the frozen round-1 (44) and round-2 (36) universes
  * near-identical = TM >= 0.65 AND coverage >= 0.80 (the unchanged rule)
  * report per arm: generated, novel (near-identical to nothing outside E3), duplicate-of-existing,
    and the nearest existing design for each

Inputs are the E3 backbone PDBs pulled from the pods. If none are present yet, the tool says so
and exits 2 (INCOMPLETE) rather than pretending to have measured anything.
"""
import glob
import json
import pathlib
import sys

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from c3_backbone_clusters_20261025 import one_letter, read_binder  # noqa: E402

try:
    from tmtools import tm_align
except ImportError:  # pragma: no cover
    tm_align = None

ROOT = pathlib.Path(__file__).resolve().parents[1]
E3 = ROOT / "results/c3_e3_111_20261025"
R1 = ROOT / "results/c3_round2_111_20261025/backbone_pdb"
R2 = R1
BASE = ROOT / "results/c3_r1_44_backbones"
OUT = E3 / "novelty_independent_20261025.json"
TM_MIN, COV_MIN = 0.65, 0.80


def load(pdb_paths):
    out = {}
    for p in pdb_paths:
        keys, residues = read_binder(str(p))
        ca = [next((x for x in residues[k] if x[0] == "CA"), None) for k in keys]
        ca = [c for c in ca if c]
        if len(ca) < 20:
            continue
        out[pathlib.Path(p).stem] = (one_letter([c[1] for c in ca]),
                                     np.array([c[2] for c in ca], dtype=float))
    return out


def main():
    e3_paths = sorted(glob.glob(str(E3 / "backbone_pdb/*.pdb")))
    if not e3_paths:
        print(f"INCOMPLETE: no E3 backbones at {E3 / 'backbone_pdb'} — nothing measured")
        return 2
    if tm_align is None:
        print("INCOMPLETE: tmtools not installed in this interpreter", file=sys.stderr)
        return 2
    e3 = load(e3_paths)
    # existing universe: round-2 designed backbones + any archived round-1 set
    ref = load(sorted(glob.glob(str(R2 / "*.pdb"))))
    for extra in ("results/c3_r1_backbone_pdb", "results/backbones", "results/c3_round1_backbones"):
        ref.update(load(sorted(glob.glob(str(ROOT / extra / "*.pdb")))))
    print(f"E3 backbones: {len(e3)}; reference backbones: {len(ref)}")

    records = []
    for name, (sa, ca) in sorted(e3.items()):
        best = (0.0, None, 0.0)
        for rn, (sb, cb) in ref.items():
            r = tm_align(ca, cb, sa, sb)
            cov = min(sum(c != "-" for c in r.seqxA) / len(sa),
                      sum(c != "-" for c in r.seqyA) / len(sb))
            # same accessor as c3_round2_clusters_20261025.py: the normalised TM for the
            # reference chain (chain 2 in that script's convention)
            tm = float(r.tm_norm_chain2)
            if tm > best[0]:
                best = (tm, rn, cov)
        near = best[0] >= TM_MIN and best[2] >= COV_MIN
        arm = name.split("_")[1] if name.startswith("e3_") else "unknown"
        records.append({"name": name, "arm": arm,
                        "nearest_reference": best[1], "nearest_tm": round(best[0], 4),
                        "nearest_coverage": round(best[2], 4),
                        "near_identical_to_existing": bool(near),
                        "novel": not near})
    by_arm = {}
    for r in records:
        a = by_arm.setdefault(r["arm"], {"generated": 0, "novel": 0, "duplicate": 0})
        a["generated"] += 1
        a["novel" if r["novel"] else "duplicate"] += 1
    out = {"rule": f"near-identical iff TM>={TM_MIN} AND coverage>={COV_MIN}",
           "n_e3": len(e3), "n_reference": len(ref),
           "by_arm": {k: {**v, "novel_fraction": round(v["novel"] / v["generated"], 3)}
                      for k, v in sorted(by_arm.items())},
           "records": records}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, indent=2) + "\n")
    print(json.dumps(out["by_arm"], indent=2))
    try:
        shown = OUT.relative_to(ROOT)
    except ValueError:
        shown = OUT
    print(f"wrote {shown}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
