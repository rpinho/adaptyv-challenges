#!/usr/bin/env python3
"""Negative controls for the independent round-2 verifier. CPU only, synthetic PDBs.

The verifier's only value is that it FAILS when it should, so every case here mutates one
property of a known-good artifact and asserts the verifier rejects it.
"""
import json
import pathlib
import shutil
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import c3_round2_verify_20261025 as V  # noqa: E402

results = []


def case(name, cond):
    results.append(bool(cond))
    print(("PASS " if cond else "FAIL ") + name)


AA3 = {v: k for k, v in V.AA3.items()}
BINDER = "EELKKRREELKKRREELKKRREELKKRREELKKRREELKKRREELKKRREELKKRRE"  # 58 res, 3.8 A apart
TARGET = ("TVSLWETVQKWREYRRQCQRSLTEDPPPATDLFCNRTFDEYACWPDGEPGSFVNVSCPWYLPWASSVPQGHVYRF"
          "CTAEGLWLQKDNSSLPWRDLSECEESSPEEQLLFLY")
GROOVE = set(range(1, 112))
REFOLD_OK = {"pass": True, "ca_rmsd_vs_designed_backbone": 0.5,
             "refold_mean_plddt": 90.0, "refold_frac_residues_plddt_ge70": 0.95}


def write_pdb(path, binder_seq, target_seq, bfac=90.0, dx=0.0, clash=False):
    """Two chains: A=binder at y=0, B=target at y=Y0 (5.0 A => contacts without a <2 A clash).

    clash=True collapses the target's y offset to 0 so heavy atoms genuinely overlap.
    dx shifts the target along x (large dx removes the interface entirely).
    """
    Y0 = 0.0 if clash else 5.0
    lines, serial = [], 0
    for chain, seq, x0, y0 in (("A", binder_seq, 0.0, 0.0), ("B", target_seq, 0.0, Y0)):
        for i, aa in enumerate(seq):
            bx = x0 + i * 3.8 + (dx if chain == "B" else 0.0)
            for atom, off in (("N", 0.0), ("CA", 1.46), ("C", 2.5), ("O", 2.9)):
                serial += 1
                # strict PDB columns: 13-16 atom, 18-20 resName, 22 chain, 23-26 resSeq,
                # 31-38 x, 39-46 y, 47-54 z, 55-60 occ, 61-66 B
                lines.append(
                    f"ATOM  {serial:5d} {atom:^4s} {AA3[aa]:>3s} {chain}{i + 1:4d}    "
                    f"{bx:8.3f}{y0 + off:8.3f}{0.0:8.3f}{1.0:6.2f}{bfac:6.2f}          "
                    f"{atom[0]:>2s}")
    path.write_text("\n".join(lines) + "\nEND\n")


def scores(path, **over):
    d = {"name": "T_s1", "source": "r2_111", "binder_len": len(BINDER), "target_len": len(TARGET),
         "iptm": 0.91, "ptm": 0.87, "mean_plddt": 92.0,
         "predictor": "colabfold_alphafold2_multimer_v3",
         "num_recycle": 3, "num_models": 5}
    d.update(over)
    path.write_text(json.dumps(d))


def build(tmp, **kw):
    d = pathlib.Path(tmp)
    write_pdb(d / "complex_rank_001.pdb", kw.get("binder", BINDER),
              kw.get("target", TARGET), bfac=kw.get("bfac", 90.0),
              dx=kw.get("dx", 0.0), clash=kw.get("clash", False))
    scores(d / "scores.json", **kw.get("scores", {}))
    return V.verify_one("T_s1", kw.get("expect_binder", BINDER),
                        kw.get("expect_target", TARGET), d, kw.get("refold", REFOLD_OK), GROOVE)


with tempfile.TemporaryDirectory() as tmp:
    r = build(tmp)
    case("control: well-formed artifact PASSES", r["status"] == "PASS")
    case("control: chains identified by sequence", (r["binder_chain"], r["target_chain"]) == ("A", "B"))

with tempfile.TemporaryDirectory() as tmp:
    bad = TARGET[:50] + "A" + TARGET[51:]
    r = build(tmp, target=bad)
    case("mutated target sequence is REJECTED", r["status"] == "fail"
         and any("target sequence" in x or "cannot assign" in x for x in r["reasons"]))

with tempfile.TemporaryDirectory() as tmp:
    bad = BINDER[:10] + "A" + BINDER[11:]
    r = build(tmp, binder=bad)
    case("mutated binder sequence is REJECTED", r["status"] == "fail")

with tempfile.TemporaryDirectory() as tmp:
    r = build(tmp, scores={"num_recycle": 1})
    case("wrong num_recycle is REJECTED", r["status"] == "fail"
         and any("num_recycle" in x for x in r["reasons"]))

with tempfile.TemporaryDirectory() as tmp:
    r = build(tmp, scores={"num_models": 1})
    case("wrong num_models is REJECTED", r["status"] == "fail")

with tempfile.TemporaryDirectory() as tmp:
    r = build(tmp, scores={"predictor": "colabfold_alphafold2_single_chain"})
    case("wrong model type is REJECTED", r["status"] == "fail")

with tempfile.TemporaryDirectory() as tmp:
    r = build(tmp, scores={"source": "v6"})
    case("wrong source tag is REJECTED", r["status"] == "fail")

with tempfile.TemporaryDirectory() as tmp:
    r = build(tmp, scores={"iptm": 0.84})
    case("below-floor iPTM is REJECTED", r["status"] == "fail"
         and any("floor" in x for x in r["reasons"]))

with tempfile.TemporaryDirectory() as tmp:
    r = build(tmp, refold={"pass": False})
    case("refold-ineligible candidate is REJECTED", r["status"] == "fail"
         and any("refold" in x for x in r["reasons"]))

with tempfile.TemporaryDirectory() as tmp:
    r = build(tmp, refold={"pass": True, "ca_rmsd_vs_designed_backbone": 3.5,
                           "refold_mean_plddt": 90, "refold_frac_residues_plddt_ge70": 0.95})
    case("refold RMSD > 3.0 is REJECTED", r["status"] == "fail")

with tempfile.TemporaryDirectory() as tmp:
    r = build(tmp, bfac=70.0)
    case("binder pLDDT < 80 is REJECTED", r["status"] == "fail"
         and any("pLDDT" in x for x in r["reasons"]))

with tempfile.TemporaryDirectory() as tmp:
    r = build(tmp, dx=400.0)
    case("no interface contacts is REJECTED", r["status"] == "fail")

with tempfile.TemporaryDirectory() as tmp:
    r = build(tmp, expect_binder="A" * 58)
    case("wrong expected binder (input mismatch) is REJECTED", r["status"] == "fail")

with tempfile.TemporaryDirectory() as tmp:
    d = pathlib.Path(tmp)
    d.mkdir(exist_ok=True)
    r = V.verify_one("T_s1", BINDER, TARGET, d, REFOLD_OK, GROOVE)
    case("missing artifact is INCOMPLETE (not a pass)", r["status"] == "incomplete")

with tempfile.TemporaryDirectory() as tmp:
    d = pathlib.Path(tmp)
    write_pdb(d / "complex_rank_001.pdb", BINDER, TARGET)
    (d / "scores.json").write_text("{ not json")
    r = V.verify_one("T_s1", BINDER, TARGET, d, REFOLD_OK, GROOVE)
    case("corrupt scores.json is REJECTED", r["status"] == "bad_evidence")

with tempfile.TemporaryDirectory() as tmp:
    d = pathlib.Path(tmp)
    write_pdb(d / "complex_rank_001.pdb", BINDER, TARGET)
    scores(d / "scores.json")
    (d / "complex_rank_001.pdb").write_text("")  # no ATOM records
    r = V.verify_one("T_s1", BINDER, TARGET, d, REFOLD_OK, GROOVE)
    case("empty PDB is REJECTED", r["status"] == "fail")

# the real artifact, if present, must still pass after the chain-assignment change
real = ROOT / "results/c3_round2_111_20261025/screen24/d/B_26102607_s2"
if real.exists():
    import csv
    inputs = {r["name"]: r for r in csv.DictReader(
        open(ROOT / "results/c3_round2_111_20261025/screen_input_24.csv"))}
    row = inputs["B_26102607_s2"]
    refold = json.loads((ROOT / "results/c3_round2_111_20261025/refold_checks_20261025.json").read_text())
    groove = set(json.loads((ROOT / "results/c3_groove_reference_20261025.json").read_text())["groove_residues_1based"])
    r = V.verify_one("B_26102607_s2", row["binder"], row["target"], real, refold["B_26102607_s2"], groove)
    case("real artifact B_26102607_s2 still PASSES", r["status"] == "PASS")

n, ok = len(results), sum(results)
print(f"\n{ok}/{n} passed")
sys.exit(0 if ok == n else 1)
