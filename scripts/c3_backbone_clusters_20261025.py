#!/usr/bin/env python3
"""Backbone independence for C3 (Kimi plan §1.3 / audit item 3).

Computes, for every pair of C3 rows (v6's 20 + the 24 shortlist candidates), the
TM-score and coverage of their BINDER backbones using tmtools, then records the pairs
that are "near-identical" under the pre-registered rule:

    identical  iff  TM >= 0.65 AND coverage >= 0.80

Output: results/c3_backbone_clusters_20261025.json
  {"pairs": {"A": {"B": {"tm": .., "coverage": ..}}}, "near_identical": [...],
   "independent_count": {...}}

Backbones come from the AF2M complex artifacts (binder chain = shorter chain), so
every row is measured from the same model type. Chain pairs with fewer than 20
common residues are recorded as {tm: 0, coverage: 0} (cannot be identical).
"""
import csv
import glob
import json
import pathlib
import sys

ROOT = pathlib.Path("/Users/ricardo/dev/adaptyv-c4")
ART = ROOT / "results/c3_pod_artifacts_20261025"
V6 = ROOT / "results/c3_submission_v6_20261023.csv"
SHORT = ROOT / "results/c3_screen_shortlist_20261024.csv"
OUT = ROOT / "results/c3_backbone_clusters_20261025.json"

AA3_TO_1 = {
    "ALA": "A", "ARG": "R", "ASN": "N", "ASP": "D", "CYS": "C", "GLN": "Q",
    "GLU": "E", "GLY": "G", "HIS": "H", "ILE": "I", "LEU": "L", "LYS": "K",
    "MET": "M", "PHE": "F", "PRO": "P", "SER": "S", "THR": "T", "TRP": "W",
    "TYR": "Y", "VAL": "V", "MSE": "M", "SEC": "U", "PYL": "O",
}


def one_letter(names):
    """tmtools.tm_align requires one-letter sequence strings, not residue names."""
    return "".join(AA3_TO_1.get(n, "X") for n in names)


def read_binder(path):
    """Coordinates + residue names of the shorter chain (the binder)."""
    chains, order = {}, {}
    for line in open(path):
        if line.startswith("ATOM") and line[16].strip() in ("", "A"):
            ch = line[21]
            key = (int(line[22:26]), line[26].strip())
            new = key not in chains.get(ch, {})
            chains.setdefault(ch, {})
            if new:
                chains[ch][key] = []
                order.setdefault(ch, []).append(key)
            chains[ch][key].append((line[12:16].strip(), line[17:20].strip(),
                                    (float(line[30:38]), float(line[38:46]), float(line[46:54]))))
    small = min(chains, key=lambda c: len(chains[c]))
    return order[small], chains[small]


def main():
    try:
        import numpy as np
        from tmtools import tm_align
    except Exception as ex:
        print(f"tmtools unavailable ({ex}); cannot compute backbone independence", file=sys.stderr)
        return 4

    v6 = {r["name"] for r in csv.DictReader(open(V6))}
    short = {r["name"] for r in csv.DictReader(open(SHORT))}
    want = v6 | short
    backbones = {}
    for pdb in sorted(glob.glob(str(ART / "*_complex.pdb"))):
        name = pathlib.Path(pdb).name[: -len("_complex.pdb")]
        if name not in want:
            continue
        keys, residues = read_binder(pdb)
        ca = [a for a in (next((x for x in residues[k] if x[0] == "CA"), None) for k in keys) if a]
        names = [a[1] for a in ca]
        coords = np.array([a[2] for a in ca], dtype=float)
        if len(coords) >= 20:
            backbones[name] = (names, coords)

    names = sorted(backbones)
    print(f"backbones: {len(names)} (of {len(want)} rows)")
    pairs, near = {}, []
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            na, ca = backbones[a]
            nb, cb = backbones[b]
            sa, sb = one_letter(na), one_letter(nb)
            if "X" in (sa + sb):
                pairs.setdefault(a, {})[b] = {"tm": 0.0, "coverage": 0.0,
                                              "skipped": "non-standard residue"}
                pairs.setdefault(b, {})[a] = pairs[a][b]
                continue
            r = tm_align(ca, cb, sa, sb)
            # coverage = fraction of each chain that participates in the alignment;
            # take the smaller of the two so "near-identical" cannot be inflated by
            # aligning a long chain onto a short one.
            aln_a, aln_b = r.seqxA, r.seqyA
            cov_a = sum(c != "-" for c in aln_a) / max(len(sa), 1)
            cov_b = sum(c != "-" for c in aln_b) / max(len(sb), 1)
            tm = float(r.tm_norm_chain2)
            cov = min(cov_a, cov_b)
            pairs.setdefault(a, {})[b] = {"tm": round(tm, 4), "coverage": round(cov, 4)}
            pairs.setdefault(b, {})[a] = {"tm": round(tm, 4), "coverage": round(cov, 4)}
            if tm >= 0.65 and cov >= 0.80:
                near.append({"a": a, "b": b, "tm": round(tm, 4), "coverage": round(cov, 4)})

    def independent_count(group):
        g = [n for n in group if n in backbones]
        n_ind = 0
        for n in g:
            if not any(p["b"] == n or p["a"] == n for p in near):
                n_ind += 1
        return n_ind

    out = {
        "rule": "identical iff TM>=0.65 AND coverage>=0.80",
        "rows_measured": len(backbones),
        "rows_expected": len(want),
        "pairs": pairs,
        "near_identical": near,
        "v6_independent_count": independent_count(sorted(v6)),
        "note": ("Coverage/TM from tmtools on binder-chain C-alpha traces of the AF2M "
                 "complex artifacts. Used only to test whether a promoted set gains an "
                 "independent backbone."),
    }
    OUT.write_text(json.dumps(out, indent=2))
    print(f"near-identical pairs: {len(near)}; v6 independent backbones: {out['v6_independent_count']}")
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
