#!/usr/bin/env python3
"""Independent round-2 screen verifier — recomputes everything from raw pod artifacts.

Deliberately does NOT import or trust the C3 lane's merge/structural/gate scripts.
It re-derives, for every design that has a pulled artifact:

  * sequence identity   — the binder sequence in the AF2M PDB must be exactly the
                          sequence in screen_input_24.csv; the target must be the
                          exact 111-mer
  * model settings      — num_recycle 3, num_models 5, alphafold2_multimer_v3
  * structural checks   — binder mean pLDDT, target/binder contacts <=5 A, groove
                          residues contacted, heavy-atom clashes <2 A, chain integrity
  * soluble filters     — the four pre-registered conditions on the designed sequence

and then reports which designs would pass every pre-registered promotion condition
at the recorded floor. It writes ONLY a report; it never writes a submission CSV.

Usage:  python3 scripts/c3_round2_verify_20261025.py [--dir DIR] [--json OUT]
"""
import argparse
import csv
import hashlib
import json
import math
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import c3_soluble_filters_20261025 as soluble  # noqa: E402

R2 = ROOT / "results/c3_round2_111_20261025"
DEFAULT_DIR = R2 / "screen24"
INPUT = R2 / "screen_input_24.csv"
REFOLD = R2 / "refold_checks_20261025.json"
GROOVE = ROOT / "results/c3_groove_reference_20261025.json"
FLOOR = 0.850            # recorded round-1 floor = max(0.76, min BindCraft iPTM)
GROOVE_CONTACT_A = 5.0
CLASH_A = 2.0
MIN_GROOVE = 5
MIN_CONTACTS = 20
BINDER_PLDDT_MIN = 80.0
CA_BOND_MIN, CA_BOND_MAX = 3.5, 4.1
TARGET_LEN = 111
TARGET_SHA = "5c2bae2d"  # prefix of the verified 111-mer hash
EXPECT_RECYCLE, EXPECT_MODELS = 3, 5
EXPECT_MODEL_TYPE = "alphafold2_multimer_v3"

AA3 = {"ALA": "A", "ARG": "R", "ASN": "N", "ASP": "D", "CYS": "C", "GLN": "Q", "GLU": "E",
       "GLY": "G", "HIS": "H", "ILE": "I", "LEU": "L", "LYS": "K", "MET": "M", "PHE": "F",
       "PRO": "P", "SER": "S", "THR": "T", "TRP": "W", "TYR": "Y", "VAL": "V"}


def parse_pdb(path):
    """chains: {chain: [ {resname, atoms:{name:(x,y,z)}, bfac:{name:b}} ]}, ATOM records only."""
    chains, order = {}, {}
    for line in open(path):
        if not line.startswith("ATOM"):
            continue
        if line[16].strip() not in ("", "A"):      # first altloc only
            continue
        ch = line[21]
        key = (int(line[22:26]), line[26].strip())
        chains.setdefault(ch, {})
        if key not in chains[ch]:
            chains[ch][key] = {"resname": line[17:20].strip(), "atoms": {}, "bfac": {}}
            order.setdefault(ch, []).append(key)
        name = line[12:16].strip()
        chains[ch][key]["atoms"][name] = (float(line[30:38]), float(line[38:46]), float(line[46:54]))
        chains[ch][key]["bfac"][name] = float(line[60:66]) if line[60:66].strip() else 0.0
    return {c: [chains[c][k] for k in order[c]] for c in chains}


def seq_of(residues):
    out = []
    for r in residues:
        aa = AA3.get(r["resname"])
        out.append(aa if aa else "X")
    return "".join(out)


def heavy(res):
    return {n: c for n, c in res["atoms"].items() if not n.startswith("H")}


def contacts(a, b, cutoff):
    n, pairs = 0, set()
    c2 = cutoff * cutoff
    b_atoms = [(i, x) for i, r in enumerate(a) for x in heavy(r).values()]
    t_atoms = [(i, x) for i, r in enumerate(b) for x in heavy(r).values()]
    for bi, bx in b_atoms:
        for ti, tx in t_atoms:
            dx, dy, dz = bx[0] - tx[0], bx[1] - tx[1], bx[2] - tx[2]
            if dx * dx + dy * dy + dz * dz <= c2:
                n += 1
                pairs.add((bi, ti))
    return n, pairs


def chain_integrity(residues):
    problems = []
    for i, r in enumerate(residues):
        missing = [a for a in ("N", "CA", "C", "O") if a not in r["atoms"]]
        if missing:
            problems.append(f"res{i + 1}: missing backbone {missing}")
    for i in range(len(residues) - 1):
        a, b = residues[i]["atoms"].get("CA"), residues[i + 1]["atoms"].get("CA")
        if not a or not b:
            continue
        d = math.dist(a, b)
        if not (CA_BOND_MIN <= d <= CA_BOND_MAX):
            problems.append(f"CA bond {i + 1}-{i + 2} = {d:.2f} A")
    return problems


def sha(s):
    return hashlib.sha256(s.encode()).hexdigest()


def verify_one(name, binder_expect, target_expect, d, refold_rec, groove_set,
               allowed_sources=("r2_111", "r3_e3")):
    r = {"name": name, "artifact_dir": str(d)}
    why = []
    sp = d / "scores.json"
    pdb = d / "complex_rank_001.pdb"
    if not sp.exists() or not pdb.exists():
        r["status"] = "incomplete"
        r["reasons"] = ["scores.json or complex_rank_001.pdb absent"]
        return r
    try:
        scores = json.loads(sp.read_text())
    except Exception as ex:
        r["status"] = "bad_evidence"
        r["reasons"] = [f"scores.json unreadable: {ex}"]
        return r
    r["iptm"] = scores.get("iptm")
    r["ptm"] = scores.get("ptm")
    r["mean_plddt_scores_file"] = scores.get("mean_plddt")
    if scores.get("name") != name:
        why.append(f"scores.json name {scores.get('name')!r} != {name!r}")
    if scores.get("source") not in allowed_sources:
        why.append(f"source {scores.get('source')!r} is not an admitted C3 source")
    if scores.get("num_recycle") != EXPECT_RECYCLE:
        why.append(f"num_recycle {scores.get('num_recycle')} != {EXPECT_RECYCLE}")
    if scores.get("num_models") != EXPECT_MODELS:
        why.append(f"num_models {scores.get('num_models')} != {EXPECT_MODELS}")
    if EXPECT_MODEL_TYPE not in str(scores.get("predictor", "")):
        why.append(f"predictor {scores.get('predictor')!r} is not {EXPECT_MODEL_TYPE}")
    if not isinstance(r["iptm"], (int, float)):
        why.append("iptm absent")

    chains = parse_pdb(pdb)
    if len(chains) != 2:
        why.append(f"expected 2 chains, found {sorted(chains)}")
        r["status"] = "fail"
        r["reasons"] = why
        return r
    # identify chains by SEQUENCE, not by size (a long binder could outgrow the target)
    by_seq = {c: seq_of(chains[c]) for c in chains}
    binder_ids = [c for c, q in by_seq.items() if q == binder_expect]
    target_ids = [c for c, q in by_seq.items() if q == target_expect]
    if len(binder_ids) != 1 or len(target_ids) != 1 or binder_ids[0] == target_ids[0]:
        why.append(f"cannot assign chains unambiguously: binder={binder_ids} target={target_ids} "
                   f"lens={ {c: len(chains[c]) for c in chains} }")
        r["status"] = "fail"
        r["reasons"] = why
        return r
    small, large = binder_ids[0], target_ids[0]
    binder, target = chains[small], chains[large]
    r["binder_chain"], r["target_chain"] = small, large
    bseq, tseq = seq_of(binder), seq_of(target)
    r["binder_len"], r["target_len"] = len(binder), len(target)
    r["binder_sequence_sha256"] = sha(bseq)
    r["target_sequence_sha256"] = sha(tseq)
    r["sequence_bound"] = bool(bseq == binder_expect and tseq == target_expect)
    if bseq != binder_expect:
        why.append(f"binder sequence differs from input (len {len(bseq)} vs {len(binder_expect)})")
    if tseq != target_expect:
        why.append("target sequence differs from the exact 111-mer")
    if len(target) != TARGET_LEN:
        why.append(f"target length {len(target)} != {TARGET_LEN}")
    if not sha(tseq).startswith(TARGET_SHA):
        why.append(f"target sha {sha(tseq)[:8]} != expected prefix {TARGET_SHA}")

    bfacs = [b for res in binder for b in res["bfac"].values()]
    mean_binder = sum(bfacs) / len(bfacs) if bfacs else 0.0
    r["binder_mean_plddt"] = round(mean_binder, 2)
    ncon, pairs = contacts(binder, target, GROOVE_CONTACT_A)
    hits = sorted({ti + 1 for _, ti in pairs} & groove_set)
    nclash, _ = contacts(binder, target, CLASH_A)
    integ = chain_integrity(binder)
    r.update({"contacts_le5A": ncon, "groove_residues_contacted": len(hits),
              "groove_residues": hits, "clashes_lt2A": nclash,
              "chain_integrity_problems": integ[:5]})
    if mean_binder < BINDER_PLDDT_MIN:
        why.append(f"binder pLDDT {mean_binder:.2f} < {BINDER_PLDDT_MIN}")
    if len(hits) < MIN_GROOVE:
        why.append(f"groove residues {len(hits)} < {MIN_GROOVE}")
    if ncon < MIN_CONTACTS:
        why.append(f"contacts {ncon} < {MIN_CONTACTS}")
    if nclash:
        why.append(f"{nclash} heavy-atom clashes < {CLASH_A} A")
    if integ:
        why.append(f"chain integrity: {integ[:2]}")

    if not isinstance(r["iptm"], (int, float)) or r["iptm"] < FLOOR:
        why.append(f"iPTM {r['iptm']} < floor {FLOOR}")
    if not refold_rec or not refold_rec.get("pass"):
        why.append("refold not eligible")
    else:
        if refold_rec.get("ca_rmsd_vs_designed_backbone", 9e9) > 3.0:
            why.append("refold RMSD > 3.0")
        if (refold_rec.get("refold_mean_plddt") or 0) < 80:
            why.append("refold pLDDT < 80")
        if (refold_rec.get("refold_frac_residues_plddt_ge70") or 0) < 0.90:
            why.append("refold frac70 < 0.90")
    for reason in soluble.failures(binder_expect):
        why.append(f"soluble_filter:{reason}")

    r["reasons"] = why
    r["status"] = "PASS" if not why else "fail"
    return r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=str(DEFAULT_DIR))
    ap.add_argument("--extra-input", default=str(R2 / "screen_input_replacements_2.csv"),
                    help="extra screened designs (e.g. the two filter-clean replacements)")
    ap.add_argument("--json", default=str(R2 / "round2_verify_independent.json"))
    ap.add_argument("--prune-missing", action="store_true",
                    help="only report designs with a pulled artifact (default: report all 24)")
    a = ap.parse_args()

    inputs = {r["name"]: r for r in csv.DictReader(open(INPUT))}
    extra = pathlib.Path(a.extra_input)
    if extra.exists():   # additive: the frozen as-screened record stays untouched
        for r in csv.DictReader(open(extra)):
            inputs.setdefault(r["name"], r)
    refold = json.loads(REFOLD.read_text())
    groove_set = set(json.loads(GROOVE.read_text())["groove_residues_1based"])
    base = pathlib.Path(a.dir)

    records = []
    for name, row in inputs.items():
        # artifacts live either directly under --dir or in a per-pod shard subdir
        d = base / name
        if not (d / "scores.json").exists():
            for sub in sorted(p for p in base.iterdir() if p.is_dir()):
                cand = sub / name
                if (cand / "scores.json").exists() or (cand / "complex_rank_001.pdb").exists():
                    d = cand
                    break
        rec = verify_one(name, row["binder"].strip(), row["target"].strip(), d,
                         refold.get(name), groove_set)
        records.append(rec)

    complete = [r for r in records if r["status"] != "incomplete"]
    passed = [r for r in records if r["status"] == "PASS"]
    print(f"=== round-2 independent verification ({len(records)} designs) ===")
    print(f"artifacts present: {len(complete)}/{len(records)}   PASS: {len(passed)}")
    for r in sorted(records, key=lambda x: (x["status"] != "PASS", x["name"])):
        tag = r["status"].upper()
        extra = f"iptm={r['iptm']}" if "iptm" in r else ""
        print(f"  {tag:<10s} {r['name']:<18s} {extra:<14s} {'; '.join(r['reasons'])[:110]}")

    out = {"rule": "independent re-derivation from raw pod artifacts; no submission written",
           "thresholds": {"floor": FLOOR, "groove_contacts_min": MIN_GROOVE,
                          "total_contacts_min": MIN_CONTACTS, "clash_a": CLASH_A,
                          "binder_plddt_min": BINDER_PLDDT_MIN,
                          "soluble": {"max19": soluble.MAX19_LIMIT,
                                      "gravy": soluble.GRAVY_LIMIT,
                                      "charged_frac": soluble.CHARGED_FRAC_MIN}},
           "input_sha256": hashlib.sha256(INPUT.read_bytes()).hexdigest(),
           "records": records}
    if not a.prune_missing:
        out["records"] = records
    pathlib.Path(a.json).write_text(json.dumps(out, indent=1) + "\n")
    print(f"wrote {a.json}")
    return 0 if all(r["status"] != "fail" for r in records) or complete else 1


if __name__ == "__main__":
    sys.exit(main())
