#!/usr/bin/env python3
"""Re-run the C4 structural screen on the CORRECT apical receptor construct.

The shipped ranked file (3370909a...) ranks 20 designs by apical-context (195-residue,
P02786 189-383) iPTM and L6, but its d_min / 2.0 A clash screen reads
results/c4_rebuild_20261024/remote_pdbs/, whose receptor chain B is the 154-residue
stitched surrogate. This script measures the same screen on the apical PDBs so the two
constructs can be compared for the identical designs.

Read-only. Writes nothing to any candidate file. Downloads nothing: the apical PDBs must
already be present in results/c4_apical_pdb_audit_20261025/ (fetched once, read-only, from
the Modal volume rfd4-runs/boltz2_c4_apical/).

Controls, both required before any number is trusted:
  * reproduction: the shipped ranked d_min must reproduce from the 154-residue PDBs
  * identity:      binder chain A sequence must be identical between the two constructs
"""
from __future__ import annotations

import importlib.util
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
APICAL = ROOT / "results/c4_apical_pdb_audit_20261025"
REBUILT = ROOT / "results/c4_rebuild_20261024/remote_pdbs"
RANKED = ROOT / "results/c4_ranked_20261025/c4_acid_ranked_20261025.json"
CLASH_GATE_A = 2.0
D_REPRO_TOL = 0.02  # shipped d_min is recorded to 3 decimals


def load_parser():
    spec = importlib.util.spec_from_file_location(
        "clash", ROOT / "scripts/c3_clash_audit_independent_20261025.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def chain_sequences(path):
    """chain id -> residue-name string, in file order (CA records only)."""
    out = {}
    for line in open(path):
        if line.startswith("ATOM  ") and line[12:16].strip() == "CA":
            out.setdefault(line[21], []).append(line[17:20].strip())
    return {chain: "".join(res) for chain, res in out.items()}


def measure(parser, path):
    chains = parser.parse_pdb(path)
    order = sorted(chains, key=lambda c: len(chains[c]))
    d_min = parser.min_interchain_distance(chains[order[0]], chains[order[1]])[0]
    pairs = len(parser.clashing_pairs(chains[order[0]], chains[order[1]], CLASH_GATE_A))
    return d_min, pairs, {c: len(chains[c]) for c in chains}


def main():
    parser = load_parser()
    ranked = json.loads(RANKED.read_text())["chosen_by_L6"]
    rows, repro_ok, identity_ok = [], 0, 0

    for entry in ranked:
        name = entry["name"]
        p_sur = REBUILT / f"{name}_complex.pdb"
        p_api = APICAL / f"{name}_complex.pdb"
        if not p_api.is_file():
            print(f"MISSING apical PDB: {p_api}", file=sys.stderr)
            return 2

        d_sur, k_sur, ch_sur = measure(parser, p_sur)
        d_api, k_api, ch_api = measure(parser, p_api)

        reproduced = abs(d_sur - entry["d_min_A"]) < D_REPRO_TOL
        repro_ok += reproduced
        seq_sur = chain_sequences(p_sur)
        seq_api = chain_sequences(p_api)
        binder_same = (
            seq_sur.get("A") is not None and seq_sur.get("A") == seq_api.get("A"))
        identity_ok += binder_same

        rows.append({
            "rank": entry["rank"], "name": name,
            "ranked_d_min_A": entry["d_min_A"],
            "d_min_surrogate154_A": round(d_sur, 3),
            "d_min_apical195_A": round(d_api, 3),
            "shift_A": round(d_api - d_sur, 3),
            "clash_pairs_surrogate154": k_sur,
            "clash_pairs_apical195": k_api,
            "pass_surrogate": d_sur >= CLASH_GATE_A and k_sur == 0,
            "pass_apical": d_api >= CLASH_GATE_A and k_api == 0,
            "chains_surrogate": ch_sur, "chains_apical": ch_api,
            "binder_sequence_identical": binder_same,
            "shipped_dmin_reproduced_from_surrogate": reproduced,
        })

    if repro_ok != len(rows):
        print(f"CONTROL FAILED: reproduction {repro_ok}/{len(rows)}", file=sys.stderr)
        return 3
    if identity_ok != len(rows):
        print(f"CONTROL FAILED: binder identity {identity_ok}/{len(rows)}", file=sys.stderr)
        return 3

    payload = {
        "question": "Does the ranked d_min / clash screen reproduce on the correct "
                    "195-residue apical structures?",
        "finding": "the shipped structural screen read 154-residue-surrogate PDBs "
                   "while iPTM/L6 came from the 195-residue apical run",
        "clash_gate_A": CLASH_GATE_A,
        "controls": {"reproduction": f"{repro_ok}/{len(rows)}",
                     "binder_identity": f"{identity_ok}/{len(rows)}"},
        "n_pass_surrogate": sum(r["pass_surrogate"] for r in rows),
        "n_pass_apical": sum(r["pass_apical"] for r in rows),
        "flagged_apical": [r["name"] for r in rows if not r["pass_apical"]],
        "rows": rows,
    }
    out = APICAL / "structural_recheck.json"
    out.write_text(json.dumps(payload, indent=1) + "\n")

    print(f"controls: reproduction {repro_ok}/{len(rows)}, binder identity {identity_ok}/{len(rows)}")
    print(f"pass on 154-residue surrogate: {payload['n_pass_surrogate']}/{len(rows)}")
    print(f"pass on 195-residue apical   : {payload['n_pass_apical']}/{len(rows)}")
    print("flagged on apical:", ", ".join(payload["flagged_apical"]) or "(none)")
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
