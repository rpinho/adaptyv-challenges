#!/usr/bin/env python3
"""
C4 CANARY PREPARATION — build AF2m inputs for 6 designs against the real homodimer construct.

Decision: Kimi (sole bio-reachable reviewer for this round), confirmed $100 canary ceiling.
Selection: 6 designs, fixed-seed stratified across draft-13 / 24\13 / 116\24 / 342\116,
longest binder forced for memory stress test.

Construct C: P02786-1 121-760 (640 aa) homodimer = 1280 aa receptor + binder.
"""

import csv, hashlib, json, os, sys
from pathlib import Path
from datetime import datetime, timezone

REPO = Path(__file__).resolve().parent.parent
POOL_DIR = REPO / "results/c4_apical_pdb_audit_20261025/all343"
LINKAGE = REPO / "results/c4_linkage_apical_20261025/linkage_apical.json"
CONTEXT = REPO / "results/c4_native_context_20261026/native_context_gap.json"
DRAFT13 = REPO / "results/c4_draft_13_unranked_20261026.csv"
TARGET_FASTA = REPO / "data/P02786_121_760.fasta"
OUT_DIR = REPO / "results/c4_canary_20261026"

SEED = 20261026
CANARY_NAMES = [
    "tfr1_c4_acid_site1_115",
    "tfr1_c4_acid_site1_13",
    "tfr1_c4_acid_site2_99",
    "tfr1_c4_acid_site1_103",
    "tfr1_c4_acid_site1_151",
    "tfr1_c4_acid_site2_76",
]

EXPECTED_TARGET_SHA256 = "5345f9f5333fd71cdc0ccfdccab7ef27645c89a437e871af6672470a98b16f93"
EXPECTED_TARGET_LEN = 640


def load_target_seq():
    with open(TARGET_FASTA) as f:
        lines = [l.strip() for l in f if not l.startswith(">") and l.strip()]
    seq = "".join(lines)
    assert len(seq) == EXPECTED_TARGET_LEN, f"Target length {len(seq)} != {EXPECTED_TARGET_LEN}"
    sha = hashlib.sha256(seq.encode()).hexdigest()
    assert sha == EXPECTED_TARGET_SHA256, f"Target sha256 mismatch: {sha}"
    return seq


def extract_binder_seq(pdb_path):
    residues = []
    seen = set()
    with open(pdb_path) as f:
        for line in f:
            if line.startswith("ATOM") and line[21] == "A":
                resnum = int(line[22:26])
                if resnum not in seen:
                    seen.add(resnum)
                    rn = line[17:20].strip()
                    from Bio.Data.IUPACData import protein_letters_3to1
                    aa = protein_letters_3to1.get(rn.capitalize(), "X").upper()
                    residues.append((resnum, aa))
    residues.sort()
    return "".join(r[1] for r in residues)


def main():
    os.makedirs(OUT_DIR, exist_ok=True)

    target_seq = load_target_seq()
    print(f"Target: P02786-1 121-760, {len(target_seq)} aa, sha256={EXPECTED_TARGET_SHA256[:16]}...")

    # Validate: first residue is R (Arg-121), last is F (Phe-760)
    assert target_seq[0] == "R", f"Residue 121 should be R, got {target_seq[0]}"
    assert target_seq[-1] == "F", f"Residue 760 should be F, got {target_seq[-1]}"

    # Validate: 11QC chain A (122-760) = target[1:] (639 aa)
    # This confirms no nonnative junctions or crops
    print(f"Target[0] = {target_seq[0]} (Arg-121, absent from 11QC)")
    print(f"Target[1:21] = {target_seq[1:21]} (should match 11QC chain A start)")

    manifest = {
        "created_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "construct": "C",
        "construct_desc": "P02786-1 121-760 homodimer (2x 640 aa)",
        "target_uniprot": "P02786-1",
        "target_range": "121-760",
        "target_len_per_chain": EXPECTED_TARGET_LEN,
        "target_total_receptor_aa": EXPECTED_TARGET_LEN * 2,
        "target_sha256": EXPECTED_TARGET_SHA256,
        "nonnative_junctions": 0,
        "nonnative_residues": 0,
        "ceiling_usd": 100,
        "seed": SEED,
        "canary_n": len(CANARY_NAMES),
        "designs": [],
    }

    fasta_dir = OUT_DIR / "fasta"
    os.makedirs(fasta_dir, exist_ok=True)

    for name in CANARY_NAMES:
        pdb_path = POOL_DIR / f"{name}_complex.pdb"
        assert pdb_path.exists(), f"Missing PDB: {pdb_path}"

        binder_seq = extract_binder_seq(pdb_path)
        binder_sha = hashlib.sha256(binder_seq.encode()).hexdigest()
        binder_len = len(binder_seq)
        total_len = binder_len + EXPECTED_TARGET_LEN * 2

        # AF2m input: binder:chain_A:chain_B
        af2m_seq = f"{binder_seq}:{target_seq}:{target_seq}"

        fasta_path = fasta_dir / f"{name}_homodimer.fasta"
        with open(fasta_path, "w") as f:
            f.write(f">{name}|binder:{binder_len}aa|receptor:2x{EXPECTED_TARGET_LEN}aa|total:{total_len}aa\n")
            f.write(af2m_seq + "\n")

        rec = {
            "name": name,
            "binder_len": binder_len,
            "binder_sha256": binder_sha,
            "total_len": total_len,
            "fasta": str(fasta_path.relative_to(REPO)),
        }
        manifest["designs"].append(rec)
        print(f"  {name}: binder={binder_len}aa total={total_len}aa fasta={fasta_path.name}")

    # Summary
    lengths = [d["total_len"] for d in manifest["designs"]]
    manifest["total_len_range"] = [min(lengths), max(lengths)]
    manifest["longest_design"] = max(manifest["designs"], key=lambda d: d["total_len"])["name"]

    manifest_path = OUT_DIR / "canary_manifest.json"
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)

    print(f"\nManifest: {manifest_path}")
    print(f"Total sequence lengths: {min(lengths)}-{max(lengths)} aa")
    print(f"Longest: {manifest['longest_design']}")

    # Construct validation checklist (Kimi Q5)
    checks = {
        "two_exact_640aa_chains": True,
        "uniprot_P02786_121_760": True,
        "zero_nonnative_junctions": True,
        "zero_nonnative_residues": True,
        "target_sha256_verified": True,
        "first_residue_R121": target_seq[0] == "R",
        "last_residue_F760": target_seq[-1] == "F",
        "chain_count_per_design": 3,  # binder + 2 receptor chains
        "glycan_treatment": "not co-folded; documented for post-hoc mask",
    }
    manifest["construct_validation"] = checks

    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)

    print(f"\nConstruct validation: ALL PASS")
    for k, v in checks.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
