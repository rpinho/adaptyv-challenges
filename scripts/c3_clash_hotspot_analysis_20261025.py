#!/usr/bin/env python3
"""HYPOTHESIS TEST: do the <2 A inter-chain clashes land ON the RFD4 hotspot atoms?

Read-only, CPU. Parses the actual hotspot selectors from configs/rfd4/c3_ecd111_r2_*.yaml and
classifies every clashing pair from the 26 launched AF2M complexes as:
  hotspot_atom      the clashing TARGET atom is one of the atoms RFD4 was told to contact
  hotspot_residue   same residue as a hotspot, different atom
  groove_other      inside the frozen groove set, not a hotspot residue
  outside           outside the groove set
If hotspot_atom dominates, the hotspot conditioning itself is a plausible driver of the clash
phenotype — a testable, falsifiable statement, NOT a proven mechanism.
"""
import collections
import glob
import json
import math
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from c3_refold_check_20261025 import parse_pdb, heavy_atoms  # noqa: E402

R2 = ROOT / "results/c3_round2_111_20261025"
OUT = R2 / "clash_hotspot_analysis_20261025.json"


def parse_hotspots():
    """Residue -> set of atom names, from every round-2 config (they share one hotspot list)."""
    sel = re.compile(r"sel\('F/\*/(\d+)/\[([A-Z0-9,]+)\]'\)")
    out = {}
    for cfg in sorted((ROOT / "configs/rfd4").glob("c3_ecd111_r2_*.yaml")):
        for m in sel.finditer(cfg.read_text()):
            out.setdefault(int(m.group(1)), set()).update(m.group(2).split(","))
    return out


def main():
    hs = parse_hotspots()
    groove = set(json.loads((ROOT / "results/c3_groove_reference_20261025.json").read_text())
                 ["groove_residues_1based"])
    counts = collections.Counter()
    by_design = collections.defaultdict(collections.Counter)
    atom_hits = collections.Counter()
    examples = []
    designs = 0
    # The two post-selection replacements exist in BOTH screen24/e/ and screen24/rep/
    # (the rep pull is deliberate). Deduplicate by design name or their clashes count twice.
    seen = set()
    for pdb in sorted(glob.glob(str(R2 / "screen24/*/*/complex_rank_001.pdb"))):
        name = pathlib.Path(pdb).parent.name
        if name in seen:
            continue
        seen.add(name)
        ch = parse_pdb(pdb)
        if len(ch) != 2:
            continue
        small = min(ch, key=lambda c: len(ch[c]))
        large = [c for c in ch if c != small][0]
        found = False
        for ra in ch[small]:
            for j, rb in enumerate(ch[large]):
                for an, ax in heavy_atoms(ra).items():
                    for bn, bx in heavy_atoms(rb).items():
                        if math.dist(ax, bx) >= 2.0:
                            continue
                        found = True
                        resno = j + 1
                        if resno in hs and bn in hs[resno]:
                            kind = "hotspot_atom"
                            atom_hits[f"{resno}:{bn}"] += 1
                        elif resno in hs:
                            kind = "hotspot_residue"
                        elif resno in groove:
                            kind = "groove_other"
                        else:
                            kind = "outside"
                        counts[kind] += 1
                        by_design[name][kind] += 1
                        if len(examples) < 25:
                            examples.append({"design": name, "class": kind,
                                             "binder": f"{ra['resname']}{an}",
                                             "target": f"{rb['resname']}{resno}:{bn}",
                                             "dist_A": round(math.dist(ax, bx), 2)})
        designs += found
    total = sum(counts.values())
    out = {
        "n_designs_scanned": len(seen),
        "rule": "heavy-atom inter-chain distance < 2.0 A (pre-registered clash rule, unchanged)",
        "designs_with_clashes": designs,
        "clash_pairs": total,
        "by_class": dict(counts),
        "fraction_hotspot_atom": round(counts["hotspot_atom"] / total, 3) if total else None,
        "fraction_hotspot_or_hotspot_atom":
            round((counts["hotspot_atom"] + counts["hotspot_residue"]) / total, 3) if total else None,
        "hotspot_atoms_involved": dict(atom_hits.most_common()),
        "hotspot_definition": {str(k): sorted(v) for k, v in sorted(hs.items())},
        "groove_residues_1based": sorted(groove),
        "examples": examples,
        "interpretation": ("Descriptive only. A high hotspot_atom share is consistent with hotspot "
                           "conditioning concentrating binder atoms at the specified target atoms; "
                           "it does not prove causation and does not change any gate."),
    }
    OUT.write_text(json.dumps(out, indent=2) + "\n")
    print(json.dumps({k: out[k] for k in ("designs_with_clashes", "clash_pairs", "by_class",
                                          "fraction_hotspot_atom", "fraction_hotspot_or_hotspot_atom",
                                          "hotspot_atoms_involved")}, indent=2))
    print(f"\nwrote {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
