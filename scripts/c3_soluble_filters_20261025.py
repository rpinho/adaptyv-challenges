#!/usr/bin/env python3
"""Pre-registered C3 soluble / non-TM sequence filters (Kimi 2026-10-25 plan §2 step 3).

Single source of truth for the four hard eligibility conditions:

    canonical 20 AAs only
    max 19-residue Kyte-Doolittle window GRAVY  < 2.0
    overall GRAVY                               < 0.4
    charged fraction (KRDEH)                   >= 0.18

These are the SAME constants and functions used for the round-1 shortlist
(scripts/c3_screen_shortlist_20261024.py); they are not new thresholds.

Fail-closed: an empty sequence, a non-canonical residue, or a non-string input
raises FilterError instead of silently passing.
"""
import math

CANON = set("ACDEFGHIKLMNPQRSTVWY")
KD = {'A': 1.8, 'R': -4.5, 'N': -3.5, 'D': -3.5, 'C': 2.5, 'Q': -3.5, 'E': -3.5,
      'G': -0.4, 'H': -3.2, 'I': 4.5, 'L': 3.8, 'K': -3.9, 'M': 1.9, 'F': 2.8,
      'P': -1.6, 'S': -0.8, 'T': -0.7, 'W': -0.9, 'Y': -1.3, 'V': 4.2}

MAX19_LIMIT = 2.0
GRAVY_LIMIT = 0.4
CHARGED_FRAC_MIN = 0.18
WINDOW = 19
CHARGE_CLASSES = "KRDEH"


class FilterError(ValueError):
    """Input cannot be evaluated, so the candidate must be rejected (never passed)."""


def _validate(seq):
    if not isinstance(seq, str):
        raise FilterError(f"sequence is not a string ({type(seq).__name__})")
    if not seq:
        raise FilterError("sequence is empty")
    bad = sorted(set(seq) - CANON)
    if bad:
        raise FilterError(f"non-canonical residue(s): {bad}")


def gravy(seq):
    _validate(seq)
    return sum(KD[c] for c in seq) / len(seq)


def max_window_gravy(seq, w=WINDOW):
    _validate(seq)
    if len(seq) < w:
        return gravy(seq)
    return max(sum(KD[c] for c in seq[i:i + w]) / w for i in range(len(seq) - w + 1))


def charged_frac(seq):
    _validate(seq)
    return sum(seq.count(x) for x in CHARGE_CLASSES) / len(seq)


def metrics(seq):
    """All filter metrics for a sequence; raises FilterError if it cannot be scored."""
    _validate(seq)
    return {"length": len(seq), "gravy": gravy(seq),
            "max_hydro_window": max_window_gravy(seq),
            "charged_frac": charged_frac(seq)}


def failures(seq):
    """Return a list of failure reasons; empty list means the sequence passes."""
    try:
        m = metrics(seq)
    except FilterError as ex:
        return [f"unscoreable:{ex}"]
    why = []
    if not (m["gravy"] < GRAVY_LIMIT):
        why.append(f"gravy>={GRAVY_LIMIT} ({m['gravy']:.3f})")
    if not (m["max_hydro_window"] < MAX19_LIMIT):
        why.append(f"max19_window>={MAX19_LIMIT} ({m['max_hydro_window']:.3f})")
    if not (m["charged_frac"] >= CHARGED_FRAC_MIN):
        why.append(f"charged_frac<{CHARGED_FRAC_MIN} ({m['charged_frac']:.3f})")
    if any(math.isnan(v) for v in m.values() if isinstance(v, float)):
        why.append("unscoreable:nan")
    return why


def passes(seq):
    return not failures(seq)


if __name__ == "__main__":
    import json
    import sys
    for s in sys.argv[1:]:
        print(json.dumps({"sequence": s, "pass": passes(s), "reasons": failures(s),
                          "metrics": metrics(s) if passes(s) else None}))
