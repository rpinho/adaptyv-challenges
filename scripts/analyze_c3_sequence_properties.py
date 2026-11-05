#!/usr/bin/env python3
"""Reproduce C3 sequence metrics; no affinity or agonism predictor is implied.

Run from any directory:
  uv run --with biopython==1.86 python scripts/analyze_c3_sequence_properties.py
  # Or: python -m pip install biopython==1.86
  #     python scripts/analyze_c3_sequence_properties.py --input designs.csv

Input: CSV with name,sequence columns. Defaults to the existing 20-design C3
submission. Adds the exact, unmodified GLP-1 sequence supplied in the question.

Secondary structure: explicitly defined Chou-Fasman-style implementation using
1978 propensities, not ProteinAnalysis.secondary_structure_fraction (which is
only a residue-composition heuristic). Nucleate H with >=4/6 P_alpha>100,
E with >=3/5 P_beta>100; extend while the new end tetrapeptide mean is >=100.
Retain H segments with mean P_alpha>103 and P_alpha>P_beta, E segments with
mean P_beta>105 and P_beta>P_alpha. Resolve contiguous H/E overlap using mean
propensities in the overlap. Four-residue turns require product(f_i)>0.000075,
mean P_turn>100 and >mean P_alpha and P_beta; assign all four to C. Unassigned
residues are C. This is an old heuristic with implementation-dependent results,
not a calibrated probability or a substitute for structure-derived DSSP.

Hydrophobic moment: Eisenberg normalized consensus scale, 100 degrees/residue,
divided by length. Report whole-chain hypothetical helix and maximum over
proline-free 18-residue windows (five ideal helix turns). Neither proves that
the sequence is helical, nor that its hydrophobic face contacts GLP1R. Maxima
have length-selection bias. GRAVY instead uses Kyte-Doolittle hydropathy.

Instability index uses all 400 Guruprasad dipeptide weights in Biopython.
The traditional cutoff is 40; it does not measure folding free energy,
aggregation, serum half-life, or affinity. Aliphatic index is not a measured Tm.
Charge KR-DE is a composition count, NOT a pH-dependent net charge; also report
Biopython charge at pH 7.4 (free termini assumed).

References:
  https://pubmed.ncbi.nlm.nih.gov/364941/
  https://doi.org/10.1073/pnas.81.1.140
  https://web.expasy.org/protparam/protparam-doc.html
  https://biopython.org/docs/1.86/api/Bio.SeqUtils.ProtParam.html
"""

import argparse
import csv
import json
import math
from pathlib import Path

import Bio
from Bio.SeqUtils import ProtParamData
from Bio.SeqUtils.ProtParam import ProteinAnalysis

ROOT = Path(__file__).resolve().parents[1]
GLP1 = "HAEGTFTSDVSSYLEGQAAKEFIAWLVKGR"
AA = "ACDEFGHIKLMNPQRSTVWY"
# P_alpha, P_beta, P_turn, followed by four positional beta-turn frequencies.
CF = {
    "A": (142, 83, 66, .060, .076, .035, .058),
    "C": (70, 119, 119, .149, .050, .117, .128),
    "D": (101, 54, 146, .147, .110, .179, .081),
    "E": (151, 37, 74, .056, .060, .077, .064),
    "F": (113, 138, 60, .059, .041, .065, .065),
    "G": (57, 75, 156, .102, .085, .190, .152),
    "H": (100, 87, 95, .140, .047, .093, .054),
    "I": (108, 160, 47, .043, .034, .013, .056),
    "K": (114, 74, 101, .055, .115, .072, .095),
    "L": (121, 130, 59, .061, .025, .036, .070),
    "M": (145, 105, 60, .068, .082, .014, .055),
    "N": (67, 89, 156, .161, .083, .191, .091),
    "P": (57, 55, 152, .102, .301, .034, .068),
    "Q": (111, 110, 98, .074, .098, .037, .098),
    "R": (98, 93, 95, .070, .106, .099, .085),
    "S": (77, 75, 143, .120, .139, .125, .106),
    "T": (83, 119, 96, .086, .108, .065, .079),
    "V": (106, 170, 50, .062, .048, .028, .053),
    "W": (108, 137, 96, .077, .013, .064, .167),
    "Y": (69, 147, 114, .082, .065, .114, .125),
}
EISENBERG = ProtParamData.gravy_scales["Eisenberg"]


def mean(values):
    return sum(values) / len(values)


def contiguous_runs(mask):
    start = None
    for i, flag in enumerate([*mask, False]):
        if flag and start is None:
            start = i
        elif not flag and start is not None:
            yield start, i  # zero-based, half-open
            start = None


def chou_fasman(seq):
    """Return an H/E/C assignment; detailed variant is specified above."""
    a, b, t = ([CF[x][k] for x in seq] for k in range(3))
    masks = []
    for prop, other, width, required, cutoff in (
        (a, b, 6, 4, 103), (b, a, 5, 3, 105)
    ):
        mask = [False] * len(seq)
        for i in range(len(seq) - width + 1):
            if sum(p > 100 for p in prop[i:i + width]) < required:
                continue
            lo, hi = i, i + width
            while lo > 0 and mean(prop[lo - 1:lo + 3]) >= 100:
                lo -= 1
            while hi < len(seq) and mean(prop[hi - 3:hi + 1]) >= 100:
                hi += 1
            if mean(prop[lo:hi]) > cutoff and mean(prop[lo:hi]) > mean(other[lo:hi]):
                mask[lo:hi] = [True] * (hi - lo)
        masks.append(mask)
    h, e = masks
    assignment = ["H" if h[i] else "E" if e[i] else "C" for i in range(len(seq))]
    for lo, hi in contiguous_runs([x and y for x, y in zip(h, e)]):
        state = "H" if mean(a[lo:hi]) >= mean(b[lo:hi]) else "E"
        assignment[lo:hi] = [state] * (hi - lo)
    for i in range(len(seq) - 3):
        product = math.prod(CF[seq[i + j]][3 + j] for j in range(4))
        mt = mean(t[i:i + 4])
        if product > .000075 and mt > 100 and mt > max(mean(a[i:i + 4]), mean(b[i:i + 4])):
            assignment[i:i + 4] = ["C"] * 4
    return "".join(assignment)


def hydrophobic_moment(seq, degrees=100):
    angle = math.radians(degrees)
    x = sum(EISENBERG[aa] * math.cos(i * angle) for i, aa in enumerate(seq))
    y = sum(EISENBERG[aa] * math.sin(i * angle) for i, aa in enumerate(seq))
    return math.hypot(x, y) / len(seq)


def strongest_window(seq, width, score, exclude_proline=False):
    candidates = [(score(seq[i:i + width]), i) for i in range(len(seq) - width + 1)
                  if not exclude_proline or "P" not in seq[i:i + width]]
    if not candidates:
        return None, None, None, ""
    # Break ties by earliest sequence position.
    value, start = max(candidates, key=lambda item: (item[0], -item[1]))
    return value, start + 1, start + width, seq[start:start + width]


def metrics(name, seq):
    seq = "".join(seq.split()).upper()
    if not seq or set(seq) - set(AA):
        raise ValueError(f"{name}: empty sequence or nonstandard amino acids")
    p = ProteinAnalysis(seq)
    n = len(seq)
    ss = chou_fasman(seq)
    moment18, mlo, mhi, mseq = strongest_window(seq, 18, hydrophobic_moment, True)
    hydro19, glo, ghi, gseq = strongest_window(seq, 19, lambda s: mean([ProtParamData.kd[x] for x in s]))
    counts = p.count_amino_acids()
    return {
        "name": name, "length": n,
        "charge_KR_DE": sum(counts[x] for x in "KR") - sum(counts[x] for x in "DE"),
        "charge_pH7_4_free_termini": p.charge_at_pH(7.4),
        "CF_helix_pct": 100 * ss.count("H") / n,
        "CF_sheet_pct": 100 * ss.count("E") / n,
        "CF_coil_pct": 100 * ss.count("C") / n,
        "muH_whole_Eisenberg100": hydrophobic_moment(seq),
        "muH_max18_noP_Eisenberg100": moment18,
        "muH18_start": mlo, "muH18_end": mhi, "muH18_sequence": mseq,
        "instability_index": p.instability_index(),
        "aliphatic_index": 100 * (counts["A"] + 2.9 * counts["V"] + 3.9 * (counts["I"] + counts["L"])) / n,
        "GRAVY_KyteDoolittle": p.gravy(),
        "max19_GRAVY": hydro19, "max19_start": glo, "max19_end": ghi, "max19_sequence": gseq,
        "aromatic_FWY_pct": 100 * sum(counts[x] for x in "FWY") / n,
        "hydrophobic_AVILMFWY_pct": 100 * sum(counts[x] for x in "AVILMFWY") / n,
        "His_count": counts["H"], "Pro_count": counts["P"],
        "CF_assignment": ss, "sequence": seq,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=ROOT / "results/c3_submission_v3_20261023.csv")
    parser.add_argument("--output", type=Path, default=ROOT / "results/c3_sequence_properties_20261023.csv")
    args = parser.parse_args()
    with args.input.open(newline="") as f:
        designs = list(csv.DictReader(f))
    names = [r["name"] for r in designs]
    if len(names) != len(set(names)) or "native_GLP1_supplied" in names:
        raise ValueError("Design names must be unique and distinct from the GLP-1 reference")
    rows = [metrics(r["name"], r["sequence"]) for r in designs]
    rows.append(metrics("native_GLP1_supplied", GLP1))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=rows[0])
        writer.writeheader()
        writer.writerows(rows)
    metadata = {"input": str(args.input.resolve()), "biopython": Bio.__version__,
                "method_notes": __doc__, "Eisenberg_scale": EISENBERG,
                "Chou_Fasman_table": CF, "design_count": len(designs)}
    args.output.with_suffix(".metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")
    print("name,length,KR-DE,H%,E%,C%,muH_whole,muH_max18_noP,II,AI,GRAVY")
    for r in rows:
        print(f"{r['name']},{r['length']},{r['charge_KR_DE']},"
              f"{r['CF_helix_pct']:.1f},{r['CF_sheet_pct']:.1f},{r['CF_coil_pct']:.1f},"
              f"{r['muH_whole_Eisenberg100']:.3f},{r['muH_max18_noP_Eisenberg100'] or 0:.3f},"
              f"{r['instability_index']:.2f},{r['aliphatic_index']:.2f},{r['GRAVY_KyteDoolittle']:.3f}")
    print(f"Saved {len(rows)} rows to {args.output}")


if __name__ == "__main__":
    main()
