#!/usr/bin/env python3
"""E3 selection: Astra's E3 acceptance rules, unchanged scientific thresholds.

Eligibility (all must hold):
  * backbone NOVEL vs round 1 + round 2 (TM>=0.65 AND coverage>=0.80 rule), and novel
    within the E3 cohort itself (one representative per near-identical E3 family);
  * ESMFold refold QC pass (mean pLDDT>=80, frac70>=0.90, CA RMSD<=3.0) - round-2 code;
  * the four pre-registered soluble/non-TM filters - round-2 code.
Selection: rank by (RMSD asc, pLDDT desc, frac70 desc, name asc). Take best eligible per
family first, then second pass, capped at MAX_PER_CLUSTER, targeting 8 per arm and balanced
length bins. ENFORCES: <=24 total, <=8 per arm, never backfills to hit a quota.

Writes results/c3_e3_111_20261025/selected_20261025.json  (NEW file; never touches E2/v8).
Exit 3 = shortfall (reported, not padded).
"""
import collections
import json
import pathlib
import sys

import numpy as np

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from c3_backbone_clusters_20261025 import one_letter, read_binder  # noqa: E402
from c3_e3_recover_novelty_20261025 import load_cif_ca  # noqa: E402
from c3_soluble_filters_20261025 import failures as filter_failures  # noqa: E402

E3 = ROOT / "results/c3_e3_111_20261025"
TM_MIN, COV_MIN = 0.65, 0.80
MAX_TOTAL, MAX_PER_ARM, MAX_PER_CLUSTER = 24, 8, 2
MIN_PLDDT, MIN_FRAC70, MAX_RMSD = 80.0, 0.90, 3.0
BINS = ["52_64", "65_80", "81_100"]


def _target_seq():
    """Frozen 111-mer target sequence, read from the round-2 screening input (single source)."""
    import csv
    rows = list(csv.DictReader(open(ROOT / "results/c3_round2_111_20261025/screen_input_24.csv")))
    seqs = {r["target"] for r in rows}
    assert len(seqs) == 1, "round-2 target column is not unique"
    s = seqs.pop()
    import hashlib
    assert hashlib.sha256(s.encode()).hexdigest() == \
        "5c2bae2dac5e467bf4e802473450a7ca3729990921bbe5c45cf6025531ef36b3", "wrong target"
    return s


TARGET_SEQ = _target_seq()


def near(sa, ca, sb, cb, tm_align):
    r = tm_align(ca, cb, sa, sb)
    cov = min(sum(c != "-" for c in r.seqxA) / len(sa),
              sum(c != "-" for c in r.seqyA) / len(sb))
    return bool(float(r.tm_norm_chain2) >= TM_MIN and cov >= COV_MIN)


def families(e3, tm_align):
    """Connected components of the E3 cohort under the unchanged near-identical rule."""
    names = sorted(e3)
    parent = {n: n for n in names}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for i, a in enumerate(names):
        for b in names[i + 1:]:
            if near(e3[a][0], e3[a][1], e3[b][0], e3[b][1], tm_align):
                parent[find(a)] = find(b)
    return {n: find(n) for n in names}


def main():
    try:
        from tmtools import tm_align
    except Exception as ex:
        print(f"INCOMPLETE: tmtools unavailable ({ex})", file=sys.stderr)
        return 2
    manifest = json.loads((E3 / "manifest.json").read_text())
    nov = json.loads((E3 / "novelty_20261025.json").read_text())["verdict"]
    refold = json.loads((E3 / "refold_checks_20261025.json").read_text())
    seqs = {}
    import csv
    for r in csv.DictReader(open(E3 / "e3_mpnn_sequences.csv")):
        seqs[r["name"]] = r["sequence"]

    e3 = {}
    for p in sorted((E3 / "backbone_pdb").iterdir()):
        if p.suffix == ".cif":
            e3[p.stem] = load_cif_ca(p)
    fam = families(e3, tm_align)

    pool, rejected = [], collections.Counter()
    for name, seq in seqs.items():
        bb = name.rsplit("_s", 1)[0]
        rec = refold.get(name)
        if not nov.get(bb, {}).get("novel"):
            rejected["duplicate_of_prior_round"] += 1
            continue
        if not rec or not rec.get("pass"):
            rejected["refold_fail"] += 1
            continue
        if filter_failures(seq):
            rejected["soluble_filter"] += 1
            continue
        pool.append({"name": name, "backbone": bb, "sequence": seq,
                     "arm": manifest.get(bb, {}).get("arm", "?"),
                     "bin": manifest.get(bb, {}).get("length_bin", "?"),
                     "family": fam.get(bb, bb),
                     "rmsd": rec["ca_rmsd_vs_designed_backbone"],
                     "mean_plddt": rec["refold_mean_plddt"],
                     "frac70": rec["refold_frac_residues_plddt_ge70"]})
    print(f"pool {len(pool)} eligible sequences; rejected {dict(rejected)}")
    if not pool:
        print("INCOMPLETE: empty pool", file=sys.stderr)
        return 3
    pool.sort(key=lambda r: (r["rmsd"], -r["mean_plddt"], -r["frac70"], r["name"]))

    byfam = {}
    for e in pool:
        byfam.setdefault(e["family"], []).append(e)
    order = sorted(byfam, key=lambda f: (byfam[f][0]["rmsd"], -byfam[f][0]["mean_plddt"],
                                         byfam[f][0]["name"]))
    chosen, per_arm, per_fam, per_bin = [], collections.Counter(), collections.Counter(), collections.Counter()
    for pass_i in (1, 2):
        for f in order:
            if len(chosen) >= MAX_TOTAL:
                break
            members = byfam[f]
            if len(members) < pass_i:
                continue
            e = members[pass_i - 1]
            if per_arm[e["arm"]] >= MAX_PER_ARM or per_fam[f] >= MAX_PER_CLUSTER:
                continue
            chosen.append(e)
            per_arm[e["arm"]] += 1
            per_fam[f] += 1
            per_bin[e["bin"]] += 1
        if len(chosen) >= MAX_TOTAL:
            break

    out = {"rule": f"TM>={TM_MIN} & cov>={COV_MIN} near-identical; refold pLDDT>={MIN_PLDDT}, "
                   f"frac70>={MIN_FRAC70}, RMSD<={MAX_RMSD}; <= {MAX_TOTAL} total, "
                   f"<= {MAX_PER_ARM}/arm, <= {MAX_PER_CLUSTER}/family",
           "n_pool": len(pool), "n_selected": len(chosen),
           "rejected": dict(rejected),
           "per_arm": dict(per_arm), "per_bin": dict(per_bin),
           "n_families": len(per_fam),
           "shortfall": bool(len(chosen) < MAX_TOTAL),
           "selected": chosen}
    (E3 / "selected_20261025.json").write_text(json.dumps(out, indent=1) + "\n")
    print(f"selected {len(chosen)} ({'SHORTFALL' if len(chosen) < MAX_TOTAL else 'full'}) "
          f"arms={dict(per_arm)} bins={dict(per_bin)} families={len(per_fam)}")
    # Screening input uses round-2's exact schema; target is the frozen 111-mer.
    import csv as _csv
    with (E3 / "screen_input_20261025.csv").open("w", newline="") as fh:
        w = _csv.DictWriter(fh, fieldnames=["name", "binder", "target", "source"])
        w.writeheader()
        for e in chosen:
            w.writerow({"name": e["name"], "binder": e["sequence"],
                        "target": TARGET_SEQ, "source": "r3_e3"})
    print(f"wrote {E3/'selected_20261025.json'} and screen_input_20261025.csv")
    return 0 if len(chosen) == MAX_TOTAL else 3


if __name__ == "__main__":
    sys.exit(main())
