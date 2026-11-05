#!/usr/bin/env python3
"""
C4 FULL RE-SCORE PREPARATION — build AF2m homodimer FASTAs for all 342 designs.

Construct C: P02786-1 121-760 (640 aa) homodimer = 1280 aa receptor + binder.
Kimi decision: re-score ALL 342 against the correct construct on 4x A40 pods.
"""

import hashlib, json, os, sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
POOL_DIR = REPO / "results/c4_apical_pdb_audit_20261025/all343"
LINKAGE = REPO / "results/c4_linkage_apical_20261025/linkage_apical.json"
TARGET_FASTA = REPO / "data/P02786_121_760.fasta"
OUT_DIR = REPO / "results/c4_full_rescore_20261027"

EXPECTED_TARGET_SHA256 = "5345f9f5333fd71cdc0ccfdccab7ef27645c89a437e871af6672470a98b16f93"
EXPECTED_TARGET_LEN = 640
N_SHARDS = 4


def sha256_str(s):
    return hashlib.sha256(s.encode()).hexdigest()


def load_target_seq():
    with open(TARGET_FASTA) as f:
        lines = [l.strip() for l in f if not l.startswith(">") and l.strip()]
    seq = "".join(lines)
    assert len(seq) == EXPECTED_TARGET_LEN, f"Target length {len(seq)} != {EXPECTED_TARGET_LEN}"
    sha = sha256_str(seq)
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
    target_seq = load_target_seq()
    print(f"Target: P02786-1 121-760, {len(target_seq)} aa, sha256={EXPECTED_TARGET_SHA256[:16]}...")
    assert target_seq[0] == "R" and target_seq[-1] == "F"

    linkage = json.load(open(LINKAGE))
    records = linkage["records"]
    print(f"Designs in linkage: {len(records)}")

    os.makedirs(OUT_DIR, exist_ok=True)

    # Build all FASTAs
    all_designs = []
    missing = []
    for rec in records:
        name = rec["name"]
        pdb_path = POOL_DIR / f"{name}_complex.pdb"
        if not pdb_path.exists():
            missing.append(name)
            continue

        binder_seq = extract_binder_seq(pdb_path)
        binder_len = len(binder_seq)
        total_len = binder_len + EXPECTED_TARGET_LEN * 2
        binder_sha = sha256_str(binder_seq)

        all_designs.append({
            "name": name,
            "binder_len": binder_len,
            "binder_sha256": binder_sha,
            "total_len": total_len,
            "binder_seq": binder_seq,
        })

    if missing:
        print(f"WARNING: {len(missing)} designs missing PDB: {missing[:5]}...")

    print(f"Valid designs: {len(all_designs)}")

    # Sort by total length descending (longest first for load balancing)
    all_designs.sort(key=lambda d: -d["total_len"])

    # Round-robin shard across N_SHARDS pods (interleaved by length for balance)
    shards = [[] for _ in range(N_SHARDS)]
    for i, d in enumerate(all_designs):
        shards[i % N_SHARDS].append(d)

    manifest = {
        "created_utc": None,  # filled below
        "construct": "C",
        "construct_desc": "P02786-1 121-760 homodimer (2x 640 aa)",
        "target_sha256": EXPECTED_TARGET_SHA256,
        "total_designs": len(all_designs),
        "n_shards": N_SHARDS,
        "shards": [],
    }

    for shard_idx, shard in enumerate(shards):
        shard_dir = OUT_DIR / f"shard_{shard_idx}" / "fasta"
        os.makedirs(shard_dir, exist_ok=True)

        shard_info = {
            "shard": shard_idx,
            "n_designs": len(shard),
            "designs": [],
        }

        for d in shard:
            name = d["name"]
            binder_seq = d["binder_seq"]
            af2m_seq = f"{binder_seq}:{target_seq}:{target_seq}"

            fasta_path = shard_dir / f"{name}_homodimer.fasta"
            with open(fasta_path, "w") as f:
                f.write(f">{name}|binder:{d['binder_len']}aa|receptor:2x{EXPECTED_TARGET_LEN}aa|total:{d['total_len']}aa\n")
                f.write(af2m_seq + "\n")

            shard_info["designs"].append({
                "name": name,
                "binder_len": d["binder_len"],
                "total_len": d["total_len"],
                "binder_sha256": d["binder_sha256"],
            })

        manifest["shards"].append(shard_info)

        lengths = [d["total_len"] for d in shard]
        print(f"  Shard {shard_idx}: {len(shard)} designs, lengths {min(lengths)}-{max(lengths)} aa")

    import time
    manifest["created_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    manifest_path = OUT_DIR / "rescore_manifest.json"
    with open(manifest_path, "w") as f:
        # Remove binder_seq from manifest (it's in the FASTAs)
        json.dump(manifest, f, indent=2)

    print(f"\nManifest: {manifest_path}")
    print(f"Total FASTAs: {len(all_designs)}")
    for i, s in enumerate(manifest["shards"]):
        print(f"  Shard {i}: {s['n_designs']} designs")


if __name__ == "__main__":
    main()
