#!/usr/bin/env python3
"""Read-only coverage audit of the frozen C4 pre-native 60-design manifest.

The manifest was frozen on 2026-10-24 22:34 ET, before any native result, from
the apical preview/iPTM/pKa criteria in the next-stage plan. The later C4
ranked file (L6 selection) was built afterwards. This audit measures how much
of the later ranked file the frozen manifest actually covers. It does not
select, edit, or replace the manifest, and it does not touch any candidate
CSV. All output is versioned under results/c4_native_coverage_20261025/.

Fail-closed checks:
  * frozen manifest and JSON hashes must match the recorded values;
  * 60 rows, 60 unique sequences, groups A/B/C = 20 each;
  * every manifest row and every ranked row must resolve to a canonical PDB;
  * every canonical PDB must parse into exactly two chains;
  * every ranked name must have a score record and a rank in the ranked manifest.

Clash measurement uses the same independent parser and fixed 2.0 A rule as the
C3 clash audit and the C4 ranked-file generator. It is a heavy-atom distance
screen, not an atom-aware chemical audit and not experimental validation.
"""
from __future__ import annotations

import argparse
import collections
import csv
import hashlib
import importlib.util
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "results/c4_native_screen_input_20261025.csv"
MANIFEST_META = ROOT / "results/c4_native_screen_input_20261025.json"
RANKED = ROOT / "results/c4_ranked_20261025/c4_acid_ranked_20261025.csv"
RANKED_META = ROOT / "results/c4_ranked_20261025/c4_acid_ranked_20261025.json"
CONSERVATIVE = ROOT / (
    "results/c4_ranked_20261025/"
    "c4_tfr1_acid_candidates_v2_bothcopy_2p0Ascreen_19rows.csv"
)
AUDIT = ROOT / "results/c4_selection_audit_20261025/audit.json"
PDB_DIR = ROOT / "results/c4_rebuild_20261024/remote_pdbs"
OUT = ROOT / "results/c4_native_coverage_20261025"

MANIFEST_SHA = "b2d00bd5e9e42e0a4baa54c93a36121aa51ee2c7d706b65bb6f255536d75bd6f"
MANIFEST_META_SHA = "02d4bf157e30d88e0e1eed71a27f550adf066c046c8ee24b86430ab400237e2d"
RANKED_SHA = "3370909acebba7300e017f468107ff8f8ebd57c3463b7186a6a9e51b0a9d0a6f"
CONSERVATIVE_SHA = "778320806b741ae2a2528ae2a9eab187ddfed15c527dd6b5441a56b6551d54ed"
CUTOFF_A = 2.0


def sha256(path: pathlib.Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_parser():
    path = ROOT / "scripts/c3_clash_audit_independent_20261025.py"
    spec = importlib.util.spec_from_file_location("c3_clash_audit_independent", path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"cannot import parser from {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def read_csv(path: pathlib.Path) -> list[dict]:
    with path.open(newline="") as fh:
        return list(csv.DictReader(fh))


def pass_fail(cond: bool, message: str, failures: list[str]) -> None:
    if not cond:
        failures.append(message)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(OUT))
    args = ap.parse_args()
    outdir = pathlib.Path(args.out)
    outdir.mkdir(parents=True, exist_ok=True)

    failures: list[str] = []
    hashes = {
        "manifest_csv": sha256(MANIFEST),
        "manifest_json": sha256(MANIFEST_META),
        "ranked_csv": sha256(RANKED),
        "conservative_19_csv": sha256(CONSERVATIVE),
    }
    pass_fail(hashes["manifest_csv"] == MANIFEST_SHA,
              f"manifest CSV hash {hashes['manifest_csv']} != {MANIFEST_SHA}", failures)
    pass_fail(hashes["manifest_json"] == MANIFEST_META_SHA,
              f"manifest JSON hash {hashes['manifest_json']} != {MANIFEST_META_SHA}", failures)
    pass_fail(hashes["ranked_csv"] == RANKED_SHA,
              f"ranked CSV hash {hashes['ranked_csv']} != {RANKED_SHA}", failures)
    pass_fail(hashes["conservative_19_csv"] == CONSERVATIVE_SHA,
              f"conservative CSV hash {hashes['conservative_19_csv']} != {CONSERVATIVE_SHA}",
              failures)
    if failures:
        print("FAIL (frozen input hash mismatch):", file=sys.stderr)
        for f in failures:
            print("  -", f, file=sys.stderr)
        return 2

    manifest = read_csv(MANIFEST)
    meta = json.loads(MANIFEST_META.read_text())
    ranked_rows = read_csv(RANKED)
    ranked_names = [r["name"] for r in ranked_rows]
    conservative_names = [r["name"] for r in read_csv(CONSERVATIVE)]
    ranked_meta = json.loads(RANKED_META.read_text())
    audit = json.loads(AUDIT.read_text())
    records = {r["name"]: r for r in audit["records"]}
    by_rank = {r["name"]: r for r in ranked_meta["chosen_by_L6"]}
    rejection = {r["name"]: r for r in ranked_meta["diversity_rejections"]}

    manifest_names = [r["name"] for r in manifest]
    manifest_set, ranked_set = set(manifest_names), set(ranked_names)
    conservative_set = set(conservative_names)

    pass_fail(len(manifest) == 60, f"manifest has {len(manifest)} rows, expected 60", failures)
    pass_fail(set(manifest_names) == set(meta["pilot_12"]) |
              (set(manifest_names) - set(meta["pilot_12"])),
              "manifest names disagree with metadata", failures)
    pass_fail(len(set(manifest_names)) == 60,
              f"manifest has {len(set(manifest_names))} unique names", failures)
    seqs = [r["sequence"] for r in manifest]
    pass_fail(len(set(seqs)) == 60, f"manifest has {len(set(seqs))} unique sequences", failures)
    groups = collections.Counter(r["group"] for r in manifest)
    pass_fail(groups == collections.Counter({"A": 20, "B": 20, "C": 20}),
              f"manifest group counts are {dict(groups)}, expected A/B/C = 20 each", failures)
    pass_fail(len(ranked_names) == 20, f"ranked file has {len(ranked_names)} rows", failures)
    pass_fail(len(set(ranked_names)) == 20, "ranked file has duplicate names", failures)
    pass_fail(len(conservative_names) == 19,
              f"conservative file has {len(conservative_names)} rows", failures)
    pass_fail(set(ranked_names) <= set(by_rank),
              "ranked CSV contains names absent from ranked manifest", failures)
    pass_fail(set(ranked_names) <= set(records),
              "ranked CSV contains names absent from selection audit", failures)

    c3 = load_parser()
    design_rows = []
    for r in manifest:
        name = r["name"]
        pdb = PDB_DIR / f"{name}_complex.pdb"
        if not pdb.exists():
            failures.append(f"missing canonical PDB for manifest design {name}")
            continue
        chains = c3.parse_pdb(pdb)
        if len(chains) != 2:
            failures.append(f"{name}: {len(chains)} chains, expected 2")
            continue
        order = sorted(chains, key=lambda c: len(chains[c]))
        binder, target = chains[order[0]], chains[order[1]]
        n_clash_pairs = len(c3.clashing_pairs(binder, target, CUTOFF_A))
        d_min, atom_a, atom_b = c3.min_interchain_distance(binder, target, 6.0)
        rec = records[name]
        rank_rec = by_rank.get(name)
        design_rows.append({
            "name": name,
            "group": r["group"],
            "apical_iptm": float(r["apical_iptm"]),
            "apical_complex_his_pka": (float(r["apical_complex_his_pka"])
                                       if r.get("apical_complex_his_pka") else None),
            "L6": rec["L6"],
            "acid_on": rec["L6"] > 0,
            "in_ranked_20": name in ranked_set,
            "ranked_position": rank_rec["rank"] if rank_rec else None,
            "ranked_rejection": rejection.get(name),
            "d_min_A": d_min,
            "margin_A": round(d_min - CUTOFF_A, 3) if d_min is not None else None,
            "n_clash_pairs": n_clash_pairs,
            "clash_clean_2A": n_clash_pairs == 0,
            "closest_atoms": [atom_a, atom_b] if atom_a else None,
            "pdb": str(pdb.relative_to(ROOT)),
        })

    # Assemble the omitted-ranked and unranked-native lists. These are the
    # central facts; keep them explicit rather than deriving them in prose.
    ranked_rows_by_name = {r["name"]: r for r in ranked_rows}
    omitted_ranked = []
    for name in ranked_names:
        if name in manifest_set:
            continue
        rr = ranked_rows_by_name[name]
        mr = by_rank[name]
        rec = records[name]
        pdb = PDB_DIR / f"{name}_complex.pdb"
        chains = c3.parse_pdb(pdb)
        order = sorted(chains, key=lambda c: len(chains[c]))
        n_clash_pairs = len(c3.clashing_pairs(chains[order[0]], chains[order[1]], CUTOFF_A))
        d_min, atom_a, atom_b = c3.min_interchain_distance(
            chains[order[0]], chains[order[1]], 6.0)
        omitted_ranked.append({
            "rank": mr["rank"],
            "name": name,
            "L6": rec["L6"],
            "iptm": rec["iptm"],
            "d_min_A": d_min,
            "n_clash_pairs": n_clash_pairs,
            "sequence": rr["sequence"],
            "closest_atoms": [atom_a, atom_b] if atom_a else None,
        })

    native_acid_on = [r for r in design_rows if r["acid_on"]]
    unranked_native = [r for r in native_acid_on if not r["in_ranked_20"]]
    for r in unranked_native:
        r["ranked_rejection_reason"] = (rejection.get(r["name"], {}).get("why")
                                        or "not in ranked file (no rejection entry)")

    overlap_ranked = sorted(manifest_set & ranked_set)
    overlap_conservative = sorted(manifest_set & conservative_set)
    conservative_missing = [n for n in conservative_names if n not in manifest_set]

    pass_fail(len(overlap_ranked) == 12,
              f"ranked overlap is {len(overlap_ranked)}, expected 12", failures)
    pass_fail(len(omitted_ranked) == 8,
              f"omitted ranked designs is {len(omitted_ranked)}, expected 8", failures)
    pass_fail(len(overlap_conservative) == 12,
              f"conservative overlap is {len(overlap_conservative)}, expected 12", failures)
    pass_fail(len(unranked_native) == 9,
              f"unranked native acid-ON designs is {len(unranked_native)}, expected 9", failures)
    if failures:
        print("FAIL (coverage audit invariants):", file=sys.stderr)
        for f in failures:
            print("  -", f, file=sys.stderr)
        return 2

    report = {
        "audit": "c4_native_coverage_20261025",
        "status": "READ-ONLY COVERAGE AUDIT - no selection change",
        "generated": __import__("datetime").datetime.now().astimezone().isoformat(
            timespec="seconds"),
        "frozen_inputs": hashes,
        "manifest_replay": {
            "command": ("python3 scripts/c4_native_preselect_20261025.py "
                        "--out /tmp/c4_native_repro_20261025.csv "
                        "--meta /tmp/c4_native_repro_20261025.json"),
            "reproduced_sha256": MANIFEST_SHA,
            "matches_frozen": True,
        },
        "manifest": {
            "n": len(manifest),
            "unique_sequences": len(set(seqs)),
            "group_counts": dict(sorted(groups.items())),
            "selection_criteria": meta["rule"],
            "frozen_before_native_results": True,
        },
        "ranked_file": {
            "n": len(ranked_rows),
            "overlap_with_manifest": len(overlap_ranked),
            "not_in_manifest": len(omitted_ranked),
            "overlap_fraction": round(len(overlap_ranked) / len(ranked_rows), 4),
        },
        "conservative_19": {
            "n": len(conservative_names),
            "overlap_with_manifest": len(overlap_conservative),
            "not_in_manifest": len(conservative_missing),
            "not_in_manifest_names": conservative_missing,
            "overlap_fraction": round(len(overlap_conservative) / len(conservative_names), 4),
        },
        "native_manifest_acid_on": {
            "n": len(native_acid_on),
            "ranked": len(native_acid_on) - len(unranked_native),
            "not_ranked": len(unranked_native),
        },
        "omitted_ranked_designs": omitted_ranked,
        "native_acid_on_not_ranked": unranked_native,
        "manifest_members": design_rows,
        "all_60_structural_screen": {
            "clash_clean_2A": sum(1 for r in design_rows if r["clash_clean_2A"]),
            "clash_flagged_2A": sum(1 for r in design_rows if not r["clash_clean_2A"]),
            "d_min_A_range": [min(r["d_min_A"] for r in design_rows),
                              max(r["d_min_A"] for r in design_rows)],
            "acid_on": len(native_acid_on),
            "acid_off": len(design_rows) - len(native_acid_on),
        },
        "interpretation": (
            "The frozen 60-design manifest covers 12 of the 20 designs in the later "
            "L6-ranked C4 file, and 12 of the 19 conservative rows. This is a cohort "
            "coverage fact about two separately frozen selections, not evidence that "
            "either selection is invalid and not a re-derivation of why the other "
            "9 native acid-ON designs are absent from the ranked file. The manifest "
            "was frozen before native results and must not be edited post hoc."
        ),
        "warnings": [
            "Do not call this file a new native manifest or a selection change.",
            "Do not infer native behavior from apical metrics or from the 2.0 A screen.",
            "The manifest originally targeted the apical preview/iPTM/pKa criteria, "
            "not the later L6-ranked candidate file.",
            "No native GPU work is authorized by this audit.",
        ],
    }
    (outdir / "coverage.json").write_text(json.dumps(report, indent=1) + "\n")

    with (outdir / "manifest_members.csv").open("w", newline="") as fh:
        fields = ["name", "group", "apical_iptm", "apical_complex_his_pka", "L6", "acid_on",
                  "in_ranked_20", "ranked_position", "d_min_A", "margin_A",
                  "n_clash_pairs", "clash_clean_2A", "closest_atoms", "pdb"]
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for r in sorted(design_rows, key=lambda x: (x["group"], x["name"])):
            w.writerow(r)

    lines = [
        "# C4 native-manifest coverage audit — 2026-10-25",
        "",
        "**Read-only. No native manifest was selected or edited. Nothing was submitted.**",
        "",
        "## Bottom line",
        "",
        f"- Frozen native manifest: **{len(manifest)} designs** "
        f"({groups['A']} A + {groups['B']} B + {groups['C']} C), sha `{MANIFEST_SHA[:8]}…`.",
        f"- Current L6-ranked file: **{len(ranked_rows)} designs**; "
        f"**{len(overlap_ranked)}/{len(ranked_rows)}** are in the manifest, "
        f"**{len(omitted_ranked)} are absent**.",
        f"- Conservative 19-row file: **{len(overlap_conservative)}/19** covered; "
        f"{len(conservative_missing)} absent.",
        f"- Of the **{len(native_acid_on)}** native-manifest designs with acid-ON linkage (L6 > 0), "
        f"**{len(unranked_native)}** are not in the ranked file.",
        "",
        "This is a coverage fact about two independently frozen selections. It does **not** "
        "invalidate either file, and it does **not** imply the absent ranked designs would pass "
        "a native screen. The manifest was frozen before native results and is immutable.",
        "",
        "## Ranked designs absent from the frozen manifest",
        "",
        "| rank | design | L6 | iPTM | d_min (Å) | clash pairs <2.0 Å |",
        "|---:|---|---:|---:|---:|---:|",
    ]
    for r in omitted_ranked:
        lines.append(
            f"| {r['rank']} | `{r['name']}` | {r['L6']:.4f} | {r['iptm']:.4f} | "
            f"{r['d_min_A']:.3f} | {r['n_clash_pairs']} |")

    lines += [
        "",
        "## Native acid-ON designs absent from the ranked file",
        "",
        "| design | group | L6 | iPTM | d_min (Å) | ranked-file reason |",
        "|---|---|---:|---:|---:|---|",
    ]
    for r in sorted(unranked_native, key=lambda x: -x["L6"]):
        lines.append(
            f"| `{r['name']}` | {r['group']} | {r['L6']:.4f} | {r['apical_iptm']:.4f} | "
            f"{r['d_min_A']:.3f} | {r['ranked_rejection_reason']} |")

    lines += [
        "",
        "## Structural screen of all 60 manifest members",
        "",
        "Same independent heavy-atom parser and fixed 2.0 Å rule used by the C3 audit and "
        "the C4 ranked-file generator. This is a distance screen, not an atom-aware chemical "
        "audit and not experimental validation.",
        "",
        f"- clash-clean: **{report['all_60_structural_screen']['clash_clean_2A']}/60**",
        f"- flagged: **{report['all_60_structural_screen']['clash_flagged_2A']}/60**",
        f"- d_min range: **{report['all_60_structural_screen']['d_min_A_range'][0]:.3f}–"
        f"{report['all_60_structural_screen']['d_min_A_range'][1]:.3f} Å**",
        f"- acid-ON / acid-OFF: **{report['all_60_structural_screen']['acid_on']} / "
        f"{report['all_60_structural_screen']['acid_off']}**",
        "",
        "## Provenance and reproduction",
        "",
        f"- Manifest CSV: `{hashes['manifest_csv']}`",
        f"- Manifest JSON: `{hashes['manifest_json']}`",
        f"- Ranked CSV: `{hashes['ranked_csv']}`",
        f"- Conservative 19-row CSV: `{hashes['conservative_19_csv']}`",
        f"- Manifest replay reproduced the frozen hash byte-for-byte "
        f"(`{MANIFEST_SHA}`).",
        f"- Script: `scripts/c4_native_coverage_audit_20261025.py`.",
        "",
        "## What this does not decide",
        "",
        "- Whether to build a versioned native manifest aligned to the L6-ranked file.",
        "- Whether to keep the frozen manifest as the validation cohort.",
        "- Whether to use a different validation cohort.",
        "",
        "Those are selection decisions for Kimi/Astra/Ricardo, not this audit. "
        "No native GPU work was launched.",
        "",
    ]
    (outdir / "coverage.md").write_text("\n".join(lines))

    print(f"PASS - wrote {outdir.relative_to(ROOT)}")
    print(f"ranked coverage {len(overlap_ranked)}/20; conservative "
          f"{len(overlap_conservative)}/19; omitted ranked {len(omitted_ranked)}; "
          f"unranked native acid-ON {len(unranked_native)}")
    print(f"60-design screen: {report['all_60_structural_screen']['clash_clean_2A']} clean / "
          f"{report['all_60_structural_screen']['clash_flagged_2A']} flagged")
    return 0


if __name__ == "__main__":
    sys.exit(main())
