#!/usr/bin/env python3
"""Cross-set backbone TM/coverage: round-2 designs vs every v7 row (CPU only).

The promotion gate's independent-backbone check (Kimi §3.4 rule 10) is only valid if the
pair map actually CONTAINS every (candidate, retained-row) relationship. The existing
results/c3_backbone_clusters_20261025.json covers the original 44 rows only, so a round-2
candidate looked up there resolves to {} and is silently counted as independent. This
script measures those missing pairs with the SAME convention (tmtools tm_align on binder
C-alpha traces, near-identical iff TM>=0.65 AND coverage>=0.80).

Sources (binder chain A of each designed/AF2M complex PDB):
  round 2 : results/c3_round2_111_20261025/backbone_pdb/<backbone>.pdb
  retained: results/c3_pod_artifacts_20261025/<name>_complex.pdb

Output: results/c3_round2_111_20261025/cross_tm_20261025.json
"""
import json
import pathlib
import sys

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from c3_backbone_clusters_20261025 import one_letter, read_binder  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
R2 = ROOT / "results/c3_round2_111_20261025"
R1_DIR = ROOT / "results/c3_pod_artifacts_20261025"
OUT = R2 / "cross_tm_20261025.json"
TM_MIN, COV_MIN = 0.65, 0.80
MIN_COORDS = 20


def load(path):
    keys, residues = read_binder(str(path))
    ca = [(k, next((x for x in residues[k] if x[0] == "CA"), None)) for k in keys]
    ca = [c for c in ca if c[1]]
    names = [c[1][1] for c in ca]
    coords = np.array([c[1][2] for c in ca], dtype=float)
    if len(coords) < MIN_COORDS:
        raise ValueError(f"{path}: only {len(coords)} CA atoms")
    return one_letter(names), coords


def main():
    try:
        from tmtools import tm_align
    except Exception as ex:  # fail closed: no measurement, no independence claim
        print(f"tmtools unavailable ({ex}); cannot measure cross-set independence", file=sys.stderr)
        return 2

    r2 = {}
    for pdb in sorted((R2 / "backbone_pdb").glob("*.pdb")):
        r2[pdb.stem] = load(pdb)
    r1 = {}
    for pdb in sorted(R1_DIR.glob("*_complex.pdb")):
        r1[pdb.name[: -len("_complex.pdb")]] = load(pdb)
    print(f"round-2 backbones: {len(r2)}   retained round-1 complexes: {len(r1)}")
    if not r2 or not r1:
        print("missing input set", file=sys.stderr)
        return 2

    out = {}
    for a, (sa, ca) in sorted(r2.items()):
        out[a] = {}
        for b, (sb, cb) in sorted(r1.items()):
            r = tm_align(ca, cb, sa, sb)
            cov = min(sum(c != "-" for c in r.seqxA) / len(sa),
                      sum(c != "-" for c in r.seqyA) / len(sb))
            tm = float(r.tm_norm_chain2)
            out[a][b] = {"tm": round(tm, 4), "coverage": round(cov, 4),
                         "near_identical": bool(tm >= TM_MIN and cov >= COV_MIN)}
    near = {a: sorted(b for b, v in d.items() if v["near_identical"]) for a, d in out.items()}
    OUT.write_text(json.dumps(
        {"rule": f"near-identical iff TM>={TM_MIN} AND coverage>={COV_MIN}; "
                 "tmtools tm_align on binder C-alpha traces (same convention as "
                 "c3_backbone_clusters_20261025.py)",
         "n_round2": len(r2), "n_retained": len(r1),
         "pairs": out, "near_identical": near}, indent=1) + "\n")
    n_near = sum(len(v) for v in near.values())
    print(f"measured {len(r2) * len(r1)} cross pairs; {n_near} near-identical")
    for a in sorted(near):
        if near[a]:
            print(f"  {a}: near {near[a]}")
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
