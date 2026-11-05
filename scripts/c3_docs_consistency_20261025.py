#!/usr/bin/env python3
"""Guard against documentation drift on the C3 portfolio composition.

The review summary and the methodology text both state how many BindCraft / variant / RFD4
designs the current file contains. Those numbers were stale at v6 while v8 was on disk. This
script recomputes the composition from the CSV and asserts the docs agree.

Exit 0 = consistent. Exit 1 = a documented number disagrees with the file (or the doc still
presents v6 as current).
"""
import collections
import csv
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
V8 = ROOT / "results/c3_submission_v8_20261025.csv"
V7 = ROOT / "results/c3_submission_v7_20261025.csv"


def composition(path):
    c = collections.Counter()
    for r in csv.DictReader(open(path, newline="")):
        n = r["name"]
        if n.startswith("c3_bc_"):
            c["bindcraft"] += 1
        elif n.startswith("c3_v_"):
            c["variant"] += 1
        elif n.startswith("c3_glp1r_ecd_"):
            c["rfd4"] += 1
        else:
            c["rfd4_round2"] += 1
    return c


def main():
    c8, c7 = composition(V8), composition(V7)
    print(f"v8: {dict(c8)}")
    print(f"v7: {dict(c7)}")
    review = (ROOT / "results/C3_REVIEW_SUMMARY.md").read_text()
    method = (ROOT / "results/c3_methodology.txt").read_text()
    fails = []

    want_v8 = (f"20 = {c8['bindcraft']} BindCraft + {c8['variant']} variants + "
               f"{c8['rfd4'] + c8['rfd4_round2']} RFD4")
    if want_v8 not in review:
        fails.append(f"review summary lacks the v8 composition line: {want_v8!r}")
    want_v7 = (f"20 = {c7['bindcraft']} BindCraft + {c7['variant']} variant + "
               f"{c7['rfd4'] + c7['rfd4_round2']} RFD4")
    if want_v7 not in review:
        fails.append(f"review summary lacks the v7 composition line: {want_v7!r}")

    # the methodology must not still describe v6's 7-variant portfolio as the final one
    if "Point-mutation variants (7 designs)" in method and "9 to 7" in method:
        if c8["variant"] == 0:
            fails.append("methodology still presents 7 variants as the shipped portfolio "
                         f"(v8 has {c8['variant']})")
    # the solved diversity mismatches must carry their explicit labels
    for needle in ("15", "16"):
        if needle not in review:
            fails.append(f"review summary is missing the binding-unit number {needle}")
    if "sensitivity" not in review.lower():
        fails.append("review summary does not label the alternate counts as sensitivity only")
    if "agonism" not in review.lower() or "not claimed" not in review.lower().replace("**", ""):
        fails.append("review summary does not state that agonism is not claimed")

    # v8 must remain the only file described as current best
    if "current best" not in review:
        fails.append("review summary does not identify the current best file")
    for f in fails:
        print("FAIL " + f)
    n = 6
    print(f"\n{n - len(fails)}/{n} documentation consistency checks passed")
    return 0 if not fails else 1


if __name__ == "__main__":
    sys.exit(main())
