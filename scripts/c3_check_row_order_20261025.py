#!/usr/bin/env python3
"""Row-order guard for the C3 candidate.

Why this exists: FAQ5 says the submission CSV must be ordered by preference, top row = highest
ranked. D's rows are exactly iPTM-descending (0 inversions). That ordering is a SCORED input, and a
stray spreadsheet re-save or a "sort A-Z" click would silently destroy it while leaving every other
check passing. This script checks nothing else, so it stays cheap and unambiguous.

Read-only. Touches nothing. Exit 0 = order preserved, exit 1 = order changed.
"""
import csv, json, sys

CAND = "results/c3_sprint_8h_20261025/c3_candidate_D_swap18_20261025.csv"
IPTM = "results/c3_sprint_8h_20261025/independent/iptm_fields_corrected.json"
EXPECTED_ORDER = [
    "p4_H8_81_100_910228_sd1", "p2_H8_65_80_910100_sd1", "p1_H8_52_64_910019_sd2",
    "p4_H8_81_100_910231_sd1", "p5_H4_65_80_910406_sd2", "p3_H8_81_100_910211_sd1",
    "p4_H8_52_64_910030_sd1", "p1_H8_52_64_910001_sd2", "p1_H8_52_64_910015_sd1",
    "p2_H8_65_80_910107_sd2", "p4_H8_65_80_910129_sd1", "p2_H8_65_80_910123_sd1",
    "p1_H8_52_64_910000_sd2", "p2_H8_65_80_910101_sd2", "p3_H8_81_100_910216_sd1",
    "p3_H8_81_100_910219_sd2", "p5_H4_81_100_910506_sd2", "p2_H8_65_80_910106_sd1",
]

rows = list(csv.DictReader(open(CAND)))
names = [r["name"] for r in rows]

if names != EXPECTED_ORDER:
    print("FAIL — row order changed.")
    for i, (a, b) in enumerate(zip(names, EXPECTED_ORDER), 1):
        if a != b:
            print(f"  first difference at row {i}: found {a!r}, expected {b!r}")
            break
    print("\nDo NOT upload without deciding whether this reordering is intentional.")
    print("FAQ5: the CSV is ordered by preference, top row highest. Order is a scored input.")
    sys.exit(1)

# Cross-check that the order is still consistent with iPTM descending.
by = {e["name"]: e["min5_iptm"] for e in json.load(open(IPTM))["per_design"]}
vals = [by[n] for n in names]
inversions = [(names[i], names[j]) for i in range(len(vals)) for j in range(i + 1, len(vals))
              if vals[i] < vals[j]]
if inversions:
    print(f"FAIL — order intact but no longer iPTM-descending ({len(inversions)} inversions).")
    sys.exit(1)

print(f"PASS — 18 rows in the recorded order (iPTM-descending, {vals[0]:.2f} -> {vals[-1]:.2f},")
print(f"       {len(vals) * (len(vals) - 1) // 2} pairs, 0 inversions). Order preserved.")
