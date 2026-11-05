#!/usr/bin/env python3
"""Freeze the 60-design C4 native-dimer manifest BEFORE any native result exists (Kimi §3.4).

Deterministic, CPU-only, no GPU, no network. Groups:
  A — all 20 rows of results/c4_apical_preview_20261024.csv
  B — scan descending apical iPTM, add first 20 not already included
  C — scan descending apical complex His pKa among iPTM >= 0.60, add first 20 not included
Ties broken by name ascending. Writes a manifest plus its SHA256 so later screens
cannot be re-selected after seeing native numbers.
"""
import argparse
import csv
import hashlib
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
CONS = ROOT / "results/c4_apical_consolidated_results.json"
PREVIEW = ROOT / "results/c4_apical_preview_20261024.csv"
OUT = ROOT / "results/c4_native_screen_input_20261025.csv"
META = ROOT / "results/c4_native_screen_input_20261025.json"
APT_IPTM_MIN = 0.60
N_PER_GROUP = 20
MISSING_EXPECTED = "tfr1_c4_acid_site1_41"
AA = set("ACDEFGHIKLMNPQRSTVWY")


def valid(r):
    """A row carries a usable apical score. NOTE: `skipped` means the remote driver found the
    artifact already present and did not recompute it — it is NOT an error and must count."""
    return (isinstance(r.get("iptm"), (int, float)) and isinstance(r.get("confidence"), (int, float))
            and not r.get("error") and bool(r.get("sequence")))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(OUT))
    ap.add_argument("--meta", default=str(META))
    a = ap.parse_args()

    cons = json.loads(CONS.read_text())
    rows = cons["results"]
    preview = list(csv.DictReader(open(PREVIEW)))

    by_name = {r["name"]: r for r in rows}
    valid_rows = [r for r in rows if valid(r)]
    print(f"consolidated rows: {len(rows)}   valid with scores: {len(valid_rows)}")
    missing = sorted(n for n in by_name if not valid(by_name[n]))
    print(f"without valid score ({len(missing)}): {missing}")

    # sanity: every preview row must have a valid apical score
    bad_preview = [p["name"] for p in preview if p["name"] not in by_name or not valid(by_name[p["name"]])]
    if bad_preview:
        print(f"FAIL: preview rows without valid apical score: {bad_preview}", file=sys.stderr)
        return 2

    picked, seen = [], set()

    def add(name, group):
        if name in seen:
            return False
        r = by_name[name]
        seq = r["sequence"]
        if not set(seq) <= AA:
            raise SystemExit(f"non-canonical residues in {name}")
        picked.append({"name": name, "sequence": seq, "molecule_class": "single_chain",
                       "group": group, "apical_iptm": round(r["iptm"], 4),
                       "apical_confidence": round(r["confidence"], 4),
                       "apical_complex_his_pka": r.get("avg_complex_his_pka"),
                       "binder_len": len(seq)})
        seen.add(name)
        return True

    # A
    for p in preview:
        add(p["name"], "A")
    print(f"A: {len(picked)}")

    # B — descending iPTM, ties by name
    b_added = 0
    for r in sorted(valid_rows, key=lambda r: (-r["iptm"], r["name"])):
        if b_added >= N_PER_GROUP:
            break
        if add(r["name"], "B"):
            b_added += 1
    print(f"B: +{b_added} (total {len(picked)})")

    # C — descending complex His pKa among iPTM>=0.60, ties by name
    c_added = 0
    pool_c = [r for r in valid_rows if r["iptm"] >= APT_IPTM_MIN
              and isinstance(r.get("avg_complex_his_pka"), (int, float))]
    print(f"C pool (iPTM>={APT_IPTM_MIN} with pKa): {len(pool_c)}")
    for r in sorted(pool_c, key=lambda r: (-r["avg_complex_his_pka"], r["name"])):
        if c_added >= N_PER_GROUP:
            break
        if add(r["name"], "C"):
            c_added += 1
    print(f"C: +{c_added} (total {len(picked)})")

    is_never = len(picked) != 60
    seqs = [p["sequence"] for p in picked]
    if len(set(seqs)) != 60:
        print(f"FAIL: duplicate sequences ({len(set(seqs))} unique)", file=sys.stderr)
        return 2
    assert not is_never, f"expected 60 designs, got {len(picked)}"

    # pilot: 4 from each group, deterministic (first per group in frozen order)
    pilot = []
    for g in ("A", "B", "C"):
        pilot += [p["name"] for p in picked if p["group"] == g][:4]

    out = pathlib.Path(a.out)
    with open(out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["name", "sequence", "molecule_class", "group",
                                          "apical_iptm", "apical_confidence",
                                          "apical_complex_his_pka", "binder_len"])
        w.writeheader()
        w.writerows(picked)
    meta = {"rule": "Kimi 2026-10-25 §3.4 frozen pre-native manifest",
            "n": len(picked), "unique_sequences": len(set(seqs)),
            "group_counts": {g: sum(1 for p in picked if p["group"] == g) for g in "ABC"},
            "apical_iptm_min_for_C": APT_IPTM_MIN,
            "excluded_without_valid_score": missing,
            "expected_missing_binder": MISSING_EXPECTED,
            "pilot_12": pilot,
            "source_consolidated": str(CONS.relative_to(ROOT)),
            "source_preview": str(PREVIEW.relative_to(ROOT)),
            "manifest_sha256": hashlib.sha256(out.read_bytes()).hexdigest()}
    pathlib.Path(a.meta).write_text(json.dumps(meta, indent=1) + "\n")
    print(f"\nfroze {len(picked)} designs -> {out}")
    print(f"sha256 {meta['manifest_sha256']}")
    print("groups", meta["group_counts"], " pilot_12:", pilot)
    lengths = sorted({p["binder_len"] for p in picked})
    print("binder lengths:", lengths[0], "-", lengths[-1])
    return 0


if __name__ == "__main__":
    sys.exit(main())
