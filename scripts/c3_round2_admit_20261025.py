#!/usr/bin/env python3
"""C3 round-2 backbone admission: verify every generated 111-mer complex, run the
existing structural gate on the binder, and stage MPNN-ready complex PDBs.

Reads RFD4 output trees under results/c3_round2_111_20261025/<TAG>_<seed>/,
writes results/c3_round2_111_20261025/admission.json and (with --stage)
results/c3_round2_111_20261025/rfd4_complex_pdbs/<name>.pdb.

Kimi plan §2: every generated full complex is verified before admission; binder
chain A, intended length, ordinary structural checks. No threshold is invented
here: construct/geometry from c3_round2_construct_20261025, structural checks
from c3_refold_check_20261025 (binder pLDDT >= 80, >=5 groove residues,
>=20 contacts <= 5 A, zero heavy-atom pairs < 2 A, chain integrity).
"""
import argparse, json, pathlib, re, subprocess, sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
R2 = ROOT / "results/c3_round2_111_20261025"
sys.path.insert(0, str(ROOT / "scripts"))
import c3_round2_construct_20261025 as construct  # noqa: E402
import c3_refold_check_20261025 as checks  # noqa: E402

BINS = {"A": (52, 64), "B": (65, 80), "C": (81, 100)}
SEEDS = {"A": ("26102500", "26102511"), "B": ("26102600", "26102611"),
         "C": ("26102700", "26102711")}
GROOVE = json.loads((ROOT / "results/c3_groove_reference_20261025.json").read_text())
GROOVE_SET = set(GROOVE["groove_residues_1based"])


def seq_of(residues):
    return "".join(checks.AA3.get(r["resname"], "X") for r in residues)


def to_pdb(cif, out):
    subprocess.run([sys.executable, str(ROOT / "scripts/cif2pdb.py"), str(cif), str(out)],
                   check=True, capture_output=True)
    return out


def admit(cif, bin_id, seed):
    name = f"c3r2_{bin_id}_{seed}"
    rec = {"name": name, "bin": bin_id, "seed": seed, "cif": str(cif.relative_to(ROOT)),
           "intended_len": BINS[bin_id]}
    try:
        rec["construct"] = construct.verify(cif)
    except AssertionError as e:
        rec.update(pass_=False, reason=f"construct: {e}")
        return rec
    pdb = R2 / "rfd4_complex_pdbs" / f"{name}.pdb"
    pdb.parent.mkdir(parents=True, exist_ok=True)
    to_pdb(cif, pdb)
    ch = checks.parse_pdb(str(pdb))
    if len(ch) != 2:
        rec.update(pass_=False, reason=f"expected 2 chains, found {sorted(ch)}")
        return rec
    binder = min(ch.values(), key=len)
    target = [c for c in ch.values() if c is not binder][0]
    bseq = seq_of(binder)
    ncontacts, pairs = checks.contacts(binder, target, checks.GROOVE_CONTACT_A)
    groove_hits = sorted({ti + 1 for _, ti in pairs} & GROOVE_SET)
    clash_n, _ = checks.contacts(binder, target, checks.CLASH_A)
    integrity = checks.chain_integrity(binder)
    plddt = [b for res in binder for b in res["bfac"].values()]
    lo, hi = rec["intended_len"]
    rec.update(
        binder_sequence=bseq, binder_len=len(binder), target_len=len(target),
        binder_sequence_sha256=checks._seqsha(bseq),
        binder_mean_plddt=round(sum(plddt) / len(plddt), 2) if plddt else 0.0,
        target_binder_contacts_le5A=ncontacts, groove_residues_contacted=len(groove_hits),
        heavy_atom_pairs_lt2A=clash_n, chain_integrity_problems=integrity[:10])
    reasons = []
    if not (lo <= len(binder) <= hi):
        reasons.append(f"binder length {len(binder)} outside {lo}-{hi}")
    if integrity:
        reasons.append("binder chain integrity")
    if rec["binder_mean_plddt"] < checks.BINDER_PLDDT_MIN:
        reasons.append(f"binder pLDDT {rec['binder_mean_plddt']} < {checks.BINDER_PLDDT_MIN}")
    if clash_n:
        reasons.append(f"{clash_n} heavy-atom pairs < {checks.CLASH_A} A")
    if len(groove_hits) < checks.MIN_GROOVE_RESIDUES:
        reasons.append(f"groove residues {len(groove_hits)} < {checks.MIN_GROOVE_RESIDUES}")
    if ncontacts < checks.MIN_TOTAL_CONTACTS:
        reasons.append(f"contacts {ncontacts} < {checks.MIN_TOTAL_CONTACTS}")
    rec["pass_"] = not reasons
    if reasons:
        rec["reason"] = "; ".join(reasons)
    return rec


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", action="store_true", help="keep MPNN-ready complex PDBs")
    ap.add_argument("--bins", default="ABC")
    a = ap.parse_args()
    rows, seen = [], {}
    for bin_id in a.bins:
        lo, hi = SEEDS[bin_id]
        for n in range(int(lo), int(hi) + 1):
            seed = str(n)
            hits = []
            for tag in (bin_id, bin_id.lower()):
                d = R2 / f"{tag}_{seed}"
                if d.is_dir() and d.name == f"{tag}_{seed}":
                    hits += sorted(d.glob("inference_samples/*/*_generated.cif"))
            if not hits:
                rows.append({"name": f"c3r2_{bin_id}_{seed}", "bin": bin_id, "seed": seed,
                             "pass_": False, "reason": "missing output"})
                continue
            if len(hits) > 1:
                rows.append({"name": f"c3r2_{bin_id}_{seed}", "bin": bin_id, "seed": seed,
                             "pass_": False, "reason": f"{len(hits)} CIFs in one seed dir"})
                continue
            rec = admit(hits[0], bin_id, seed)
            rows.append(rec)
            if rec.get("pass_"):
                seq = rec["binder_sequence"]
                if seq in seen:
                    rec["pass_"] = False
                    rec["reason"] = f"duplicate binder sequence of {seen[seq]}"
                else:
                    seen[seq] = rec["name"]
    out = R2 / "admission.json"
    out.write_text(json.dumps(rows, indent=2) + "\n")
    for b in a.bins:
        sel = [r for r in rows if r["bin"] == b]
        ok = sum(1 for r in sel if r.get("pass_"))
        print(f"bin {b}: {ok}/{len(sel)} admitted")
        for r in sel:
            if not r.get("pass_"):
                print(f"  REJECT {r['name']}: {r.get('reason')}")
    ok = sum(1 for r in rows if r.get("pass_"))
    print(f"TOTAL {ok}/{len(rows)} admitted -> {out}")
    if a.stage:
        stage = R2 / "rfd4_complex_pdbs"
        keep = {r["name"] for r in rows if r.get("pass_")}
        for p in stage.glob("*.pdb"):
            if p.stem not in keep:
                p.unlink()
        print(f"staged {len(keep)} PDBs in {stage}")
    return 0 if ok == len(rows) else 1


if __name__ == "__main__":
    sys.exit(main())
