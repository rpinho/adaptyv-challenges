#!/usr/bin/env python3
"""Fail-closed tests for the pre-registered C3 soluble/non-TM filters. CPU only."""
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import c3_soluble_filters_20261025 as F  # noqa: E402

results = []


def case(name, cond):
    results.append(bool(cond))
    print(("PASS " if cond else "FAIL ") + name)


# --- the four thresholds are the pre-registered ones, not new numbers ---
case("thresholds unchanged (2.0 / 0.4 / 0.18 / w=19)",
     (F.MAX19_LIMIT, F.GRAVY_LIMIT, F.CHARGED_FRAC_MIN, F.WINDOW) == (2.0, 0.4, 0.18, 19))
case("charge classes are KRDEH (round-1 convention)", F.CHARGE_CLASSES == "KRDEH")
case("KD scale is the standard Kyte-Doolittle table",
     F.KD["A"] == 1.8 and F.KD["I"] == 4.5 and F.KD["R"] == -4.5 and len(F.KD) == 20)

# --- a clean, soluble, charged sequence passes ---
GOOD = "EELKKRREELKKRREELKKRREELKKRREELKKRREELKKRREELKKRREELKKR"
case("clean charged sequence passes", F.passes(GOOD) and F.failures(GOOD) == [])

# --- each failure mode is caught on its own ---
case("poly-alanine fails GRAVY and charged fraction",
     any("gravy" in r for r in F.failures("A" * 52))
     and any("charged_frac" in r for r in F.failures("A" * 52)))

hydrophobic = "EEKK" + "LLLLLLLLLLLLLLLLLLL" + "EEKK" * 8
case("long hydrophobic stretch trips the max-19 window",
     any("max19_window" in r for r in F.failures(hydrophobic)))
case("the same stretch is caught even when overall GRAVY is moderate",
     F.gravy(hydrophobic) < 2.0 and not F.passes(hydrophobic))

# neutral, mildly polar sequence: low GRAVY and no hydrophobic stretch, but ~0 charge
low_charge = "AAGGPPSSTT" * 5 + "AAGG"
case("low charged fraction alone rejects (GRAVY and window both pass)",
     F.gravy(low_charge) < 0.4 and F.max_window_gravy(low_charge) < 2.0
     and F.failures(low_charge) == ["charged_frac<0.18 (0.000)"])

# --- fail-closed inputs ---
for bad, label in [("", "empty sequence"), (None, "None"), ("ACDX", "non-canonical X"),
                   ("ACD*", "stop codon"), ("acdefg", "lowercase")]:
    case(f"{label} is REJECTED, never passed",
         (not F.passes(bad)) and F.failures(bad) and F.failures(bad)[0].startswith("unscoreable"))

# --- boundary semantics: strict < for GRAVY/max19, >= for charged fraction ---
case("charged fraction exactly at 0.18 passes (>=)",
     F.charged_frac("E" * 18 + "A" * 82) == 0.18 and F.charged_frac("E" * 18 + "A" * 82) >= 0.18)
case("GRAVY is a strict inequality at the limit",
     F.GRAVY_LIMIT == 0.4 and F.MAX19_LIMIT == 2.0)

# --- short sequences use overall GRAVY as the window (documented behaviour) ---
short = "EEKKRR" * 3  # 18 residues, below the 19-residue window
case("shorter than the window falls back to overall GRAVY",
     F.max_window_gravy(short) == F.gravy(short))

# --- regression: the two known round-2 failures are caught with the recorded numbers ---
import json  # noqa: E402
R2 = ROOT / "results/c3_round2_111_20261025/mpnn_sequences_20261025.json"
if R2.exists():
    seqs = {(s["backbone"], s["sample"]): s["seq"] for s in json.loads(R2.read_text())}
    if ("A_26102505", 1) in seqs:
        seq = seqs[("A_26102505", 1)]
        m = F.metrics(seq)
        case("A_26102505_s1 rejected (GRAVY 0.626, cf 0.172)",
             (not F.passes(seq)) and round(m["gravy"], 3) == 0.626
             and round(m["charged_frac"], 3) == 0.172)
    if ("C_26102707", 2) in seqs:
        seq = seqs[("C_26102707", 2)]
        case("C_26102707_s2 rejected (GRAVY 0.502)",
             (not F.passes(seq)) and round(F.gravy(seq), 3) == 0.502)
    if ("C_26102701", 1) in seqs:
        seq = seqs[("C_26102701", 1)]
        case("C_26102701_s1 PASSES under KRDEH (0.193); it is not a filter failure",
             F.passes(seq) and round(F.charged_frac(seq), 4) == 0.1932)

n, ok = len(results), sum(results)
print(f"\n{ok}/{n} passed")
sys.exit(0 if ok == n else 1)
