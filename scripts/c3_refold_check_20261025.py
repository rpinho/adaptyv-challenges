#!/usr/bin/env python3
"""C3 refold + structural evidence checks (Kimi 2026-10-25 plan §1.2).

Two entry points:

  --groove          Derive the target-groove residue set ONCE from the reference
                    BindCraft CIF (target residues within 5 A of its binder chain)
                    and write results/c3_groove_reference_20261025.json.
  --structural      For every shortlist candidate with an AF2M complex artifact,
                    compute chain integrity, binder-chain pLDDT, target-binder
                    contacts, groove contacts, and severe clashes; write
                    results/c3_structural_checks_20261025.json.
  --refold-merge    Merge per-candidate ESMFold monomer outputs (from the pods)
                    with their AF2M binder chains: RMSD + refold pLDDT; write
                    results/c3_refold_checks_20261025.json.

No thresholds are invented here — every constant is from the decision record.
"""
import argparse
import csv
import glob
import hashlib
import json
import math
import pathlib
import sys

ROOT = pathlib.Path("/Users/ricardo/dev/adaptyv-c4")
REF_CIF = ROOT / "results/pods/c3_glp1r/3_Ranked/c3_glp1r_ecd_groove_forced_l57_fbcf76afc72c5634_seq0.cif"
SHORTLIST = ROOT / "results/c3_screen_shortlist_20261024.csv"
SCORES = ROOT / "results/c3_screen_af2m_scores_combined_20261025.json"
ARTIFACT_DIR = ROOT / "results/c3_pod_artifacts_20261025"

GROOVE_CONTACT_A = 5.0
CLASH_A = 2.0
MIN_GROOVE_RESIDUES = 5
MIN_TOTAL_CONTACTS = 20
REFOLD_PLDDT_MEAN = 80.0
REFOLD_PLDDT_FRAC70 = 0.90
RMSD_MAX = 3.0
ALLOW_SHRINK = False
BINDER_PLDDT_MIN = 80.0
CA_BOND_MIN, CA_BOND_MAX = 3.5, 4.1
BACKBONE = ("N", "CA", "C", "O")

AA3 = {
    "ALA": "A", "ARG": "R", "ASN": "N", "ASP": "D", "CYS": "C", "GLN": "Q",
    "GLU": "E", "GLY": "G", "HIS": "H", "ILE": "I", "LEU": "L", "LYS": "K",
    "MET": "M", "PHE": "F", "PRO": "P", "SER": "S", "THR": "T", "TRP": "W",
    "TYR": "Y", "VAL": "V",
}


def parse_pdb(path):
    """Return chains: {chain_id: [(resseq, icode, resname, {atom: (x,y,z), bfac})]}."""
    chains = {}
    order = {}
    with open(path) as f:
        for line in f:
            if not line.startswith("ATOM"):
                continue
            alt = line[16].strip()
            if alt not in ("", "A"):
                continue
            name = line[12:16].strip()
            resn = line[17:20].strip()
            ch = line[21]
            resseq = int(line[22:26])
            icode = line[26].strip()
            x, y, z = float(line[30:38]), float(line[38:46]), float(line[46:54])
            b = float(line[60:66]) if line[60:66].strip() else 0.0
            key = (resseq, icode)
            chains.setdefault(ch, {})
            if key not in chains[ch]:
                chains[ch][key] = {"resname": resn, "atoms": {}, "bfac": {}}
                order.setdefault(ch, []).append(key)
            chains[ch][key]["atoms"][name] = (x, y, z)
            chains[ch][key]["bfac"][name] = b
    return {ch: [chains[ch][k] for k in order[ch]] for ch in chains}


def parse_ref_cif(path):
    """Parse the BindCraft reference CIF (nonstandard column set) into the same shape."""
    header, atoms = [], []
    with open(path) as f:
        for line in f:
            if line.startswith("_atom_site."):
                header.append(line.strip().split(".", 1)[1])
            elif line.startswith("ATOM"):
                atoms.append(line.split())
    idx = {h: i for i, h in enumerate(header)}
    chains, order = {}, {}
    for a in atoms:
        ch = a[idx["label_asym_id"]]
        resseq = int(a[idx["label_seq_id"]])
        name = a[idx["label_atom_id"]]
        resn = a[idx["label_comp_id"]]
        coord = (float(a[idx["Cartn_x"]]), float(a[idx["Cartn_y"]]), float(a[idx["Cartn_z"]]))
        b = float(a[idx["B_iso_or_equiv"]])
        key = (resseq, "")
        chains.setdefault(ch, {})
        if key not in chains[ch]:
            chains[ch][key] = {"resname": resn, "atoms": {}, "bfac": {}}
            order.setdefault(ch, []).append(key)
        chains[ch][key]["atoms"][name] = coord
        chains[ch][key]["bfac"][name] = b
    return {ch: [chains[ch][k] for k in order[ch]] for ch in chains}


def heavy_atoms(res):
    return {n: c for n, c in res["atoms"].items() if not n.startswith("H")}


def contacts(chains_a, chains_b, cutoff):
    """Count target-binder heavy-atom pairs within cutoff; return (n, residue pairs)."""
    n = 0
    pairs = set()
    b_atoms = [(ri, nme, xyz) for ri, res in enumerate(chains_a) for nme, xyz in heavy_atoms(res).items()]
    t_atoms = [(ri, nme, xyz) for ri, res in enumerate(chains_b) for nme, xyz in heavy_atoms(res).items()]
    c2 = cutoff * cutoff
    for bi, _, bxyz in b_atoms:
        for ti, _, txyz in t_atoms:
            dx = bxyz[0] - txyz[0]
            dy = bxyz[1] - txyz[1]
            dz = bxyz[2] - txyz[2]
            if dx * dx + dy * dy + dz * dz <= c2:
                n += 1
                pairs.add((bi, ti))
    return n, pairs


def chain_integrity(residues):
    problems = []
    for res in residues:
        missing = [a for a in BACKBONE if a not in res["atoms"]]
        if missing:
            problems.append(f"{res['resname']}{residues.index(res)+1} missing {missing}")
    cas = [res["atoms"].get("CA") for res in residues]
    for i in range(len(cas) - 1):
        if cas[i] is None or cas[i + 1] is None:
            continue
        d = math.dist(cas[i], cas[i + 1])
        if d < CA_BOND_MIN or d > CA_BOND_MAX:
            problems.append(f"CA-CA {i+1}-{i+2} = {d:.2f} A")
    return problems


def kabsch_rmsd(P, Q):
    """RMSD of P onto Q after optimal superposition (all atoms, no pruning)."""
    import numpy as np
    P = np.asarray(P, dtype=float)
    Q = np.asarray(Q, dtype=float)
    pc = P - P.mean(axis=0)
    qc = Q - Q.mean(axis=0)
    H = pc.T @ qc
    U, S, Vt = np.linalg.svd(H)
    d = np.sign(np.linalg.det(Vt.T @ U.T))
    D = np.diag([1.0, 1.0, d])
    R = Vt.T @ D @ U.T
    Prot = (R @ pc.T).T
    return float(np.sqrt(((Prot - qc) ** 2).sum(axis=1).mean()))


def cmd_groove():
    ch = parse_ref_cif(REF_CIF)
    ids = sorted(ch)
    if len(ids) < 2:
        raise SystemExit(f"reference CIF has {len(ids)} chains; expected binder+target")
    binder, target = ch[ids[1]], ch[ids[0]]   # chain A = target(111), B = binder(57)
    _, pairs = contacts(binder, target, GROOVE_CONTACT_A)
    groove = sorted({ti + 1 for _, ti in pairs})
    out = {
        "reference_cif": str(REF_CIF.relative_to(ROOT)),
        "target_chain_residues": len(target),
        "binder_chain_residues": len(binder),
        "cutoff_a": GROOVE_CONTACT_A,
        "groove_residues_1based": groove,
        "n_groove_residues": len(groove),
        "note": ("Target residues (1-based, chain A of the reference CIF) within "
                 f"{GROOVE_CONTACT_A} A of the reference binder. Defined ONCE and reused "
                 "for every candidate."),
    }
    p = ROOT / "results/c3_groove_reference_20261025.json"
    p.write_text(json.dumps(out, indent=2))
    print(f"groove residues ({len(groove)}): {groove}")
    print(f"wrote {p}")


def _seqsha(seq):
    return hashlib.sha256(seq.encode()).hexdigest()


def cmd_structural():
    scores = {r["name"]: r for r in json.loads(SCORES.read_text())}
    shortlist = {r["name"]: r["sequence"] for r in csv.DictReader(open(SHORTLIST))}
    groove = json.loads((ROOT / "results/c3_groove_reference_20261025.json").read_text())
    groove_set = set(groove["groove_residues_1based"])
    out = {}
    for pdb in sorted(glob.glob(str(ARTIFACT_DIR / "*_complex.pdb"))):
        name = pathlib.Path(pdb).name[: -len("_complex.pdb")]
        ch = parse_pdb(pdb)
        if len(ch) != 2:
            out[name] = {"pass": False, "reason": f"expected 2 chains, found {len(ch)}"}
            continue
        small = min(ch, key=lambda c: len(ch[c]))
        large = [c for c in ch if c != small][0]
        binder, target = ch[small], ch[large]
        binder_plddt = [b for res in binder for b in res["bfac"].values()]
        mean_binder = sum(binder_plddt) / len(binder_plddt) if binder_plddt else 0.0
        ncontacts, pairs = contacts(binder, target, GROOVE_CONTACT_A)
        groove_hits = sorted({ti + 1 for _, ti in pairs} & groove_set)
        clash_n, _ = contacts(binder, target, CLASH_A)
        integrity = chain_integrity(binder)
        checks = {
            "binder_len": len(binder),
            "target_len": len(target),
            "binder_mean_plddt": round(mean_binder, 2),
            "target_binder_contacts_le5A": ncontacts,
            "groove_residues_contacted": len(groove_hits),
            "groove_residues": groove_hits,
            "heavy_atom_pairs_lt2A": clash_n,
            "chain_integrity_problems": integrity[:10],
        }
        passed = (
            checks["binder_mean_plddt"] >= BINDER_PLDDT_MIN
            and checks["groove_residues_contacted"] >= MIN_GROOVE_RESIDUES
            and checks["target_binder_contacts_le5A"] >= MIN_TOTAL_CONTACTS
            and checks["heavy_atom_pairs_lt2A"] == 0
            and not integrity
        )
        checks["pass"] = passed
        if name in shortlist:
            checks["sequence_sha256"] = _seqsha(shortlist[name])
            if not integrity and checks["binder_len"] != len(shortlist[name]):
                checks["pass"] = False
                checks["reason"] = "binder length differs from shortlist sequence"
        else:
            checks["sequence_sha256"] = None
        if not integrity and checks["binder_len"] != scores.get(name, {}).get("binder_len"):
            checks["pass"] = False
            checks["reason"] = "binder length differs from scored row"
        out[name] = checks
    p = ROOT / "results/c3_structural_checks_20261025.json"
    p.write_text(json.dumps(out, indent=2))
    ok = sum(1 for v in out.values() if v.get("pass"))
    print(f"structural checks: {ok}/{len(out)} pass -> {p}")
    for n, v in sorted(out.items()):
        if not v.get("pass"):
            print(f"  FAIL {n}: {v.get('reason') or v.get('chain_integrity_problems') or ''}")


def cmd_refold_merge(esm_dir):
    """esm_dir holds <name>.pdb monomer models produced by ESMFold on the pods."""
    scores = {r["name"]: r for r in json.loads(SCORES.read_text())}
    out = {}
    for pdb in sorted(glob.glob(str(pathlib.Path(esm_dir) / "*.pdb"))):
        name = pathlib.Path(pdb).stem
        mono = parse_pdb(pdb)
        if len(mono) != 1:
            out[name] = {"pass": False, "reason": f"monomer file has {len(mono)} chains"}
            continue
        residues = list(mono.values())[0]
        plddt = [b for res in residues for b in res["bfac"].values()]
        mean = sum(plddt) / len(plddt) if plddt else 0.0
        frac70 = sum(1 for b in plddt if b >= 70) / len(plddt) if plddt else 0.0
        complex_pdb = ARTIFACT_DIR / f"{name}_complex.pdb"
        rmsd = None
        if complex_pdb.exists():
            ch = parse_pdb(complex_pdb)
            small = min(ch, key=lambda c: len(ch[c]))
            binder = ch[small]
            mono_ca = [(r["resseq"], r["atoms"].get("CA")) for r in _as_residues(residues)]
            bnd_ca = []
            for i, res in enumerate(binder):
                bnd_ca.append((i + 1, res["atoms"].get("CA")))
            if len(mono_ca) == len(bnd_ca) and all(p[1] and q[1] for p, q in zip(mono_ca, bnd_ca)):
                rmsd = kabsch_rmsd([p[1] for p in mono_ca], [q[1] for q in bnd_ca])
        passed = mean >= REFOLD_PLDDT_MEAN and frac70 >= REFOLD_PLDDT_FRAC70 and (
            rmsd is not None and rmsd <= RMSD_MAX)
        shortlist = {r["name"]: r["sequence"] for r in csv.DictReader(open(SHORTLIST))}
        seq = shortlist.get(name)
        out[name] = {
            "sequence_sha256": _seqsha(seq) if seq else None,
            "refold_mean_plddt": round(mean, 2),
            "refold_frac_residues_plddt_ge70": round(frac70, 4),
            "ca_rmsd_vs_af2m_binder": None if rmsd is None else round(rmsd, 3),
            "pass": passed,
        }
    p = ROOT / "results/c3_refold_checks_20261025.json"
    # SAFETY: this file is promotion evidence. A merge over a partial set of ESMFold
    # outputs must never shrink or silently overwrite the full record (this happened
    # once on 2026-10-24 with a 2-design reproducibility check). Refuse to write a set
    # that loses rows already on disk, unless --refold-allow-shrink is given.
    if p.exists():
        try:
            prev = json.loads(p.read_text())
        except Exception:
            prev = {}
        if isinstance(prev, dict) and prev:
            lost = sorted(set(prev) - set(out))
            if lost and not ALLOW_SHRINK:
                print(f"REFUSING to shrink {p.name}: merge would drop {len(lost)} existing "
                      f"record(s) ({', '.join(lost[:4])}...). Existing file left untouched.",
                      file=sys.stderr)
                return 5
    p.write_text(json.dumps(out, indent=2))
    print(f"refold checks: {sum(1 for v in out.values() if v.get('pass'))}/{len(out)} pass -> {p}")


def _as_residues(seq):
    return [{"resseq": i + 1, "atoms": r["atoms"], "resname": r["resname"], "bfac": r["bfac"]}
            for i, r in enumerate(seq)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--groove", action="store_true")
    ap.add_argument("--structural", action="store_true")
    ap.add_argument("--refold-merge", metavar="ESM_DIR")
    ap.add_argument("--refold-allow-shrink", action="store_true",
                    help="permit a merge that drops existing records (audited override)")
    a = ap.parse_args()
    if a.groove:
        cmd_groove()
    if a.structural:
        cmd_structural()
    if a.refold_merge:
        globals()["ALLOW_SHRINK"] = a.refold_allow_shrink
        cmd_refold_merge(a.refold_merge)
    if not (a.groove or a.structural or a.refold_merge):
        ap.print_help()
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
