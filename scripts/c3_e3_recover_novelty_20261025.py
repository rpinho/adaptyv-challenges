#!/usr/bin/env python3
"""E3 cohort: recover designed backbones from the pods and measure novelty vs ALL prior work.

CPU only. Reads only; never launches GPU work, never touches v6/v7/v8, E2 or round-1 evidence.

Rule (identical to c3_backbone_clusters / c3_round2_cross_tm): near-identical iff
TM >= 0.65 AND coverage >= 0.80, tm_align on binder C-alpha traces.

Reference universe = round-1 retained complexes + round-2 designed backbones + E3 backbones.
A backbone is "novel" iff it is near-identical to nothing in round 1 and round 2.

Outputs (new, versioned):
  results/c3_e3_111_20261025/backbone_pdb/*.pdb        recovered backbones
  results/c3_e3_111_20261025/manifest.json             per-backbone arm/bin/seed/source
  results/c3_e3_111_20261025/novelty_20261025.json     pair map + novelty verdicts
"""
import json
import pathlib
import re
import subprocess
import sys

import numpy as np

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
from c3_backbone_clusters_20261025 import one_letter, read_binder  # noqa: E402

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUTDIR = ROOT / "results/c3_e3_111_20261025"
BB = OUTDIR / "backbone_pdb"
R2 = ROOT / "results/c3_round2_111_20261025/backbone_pdb"
R1_DIR = ROOT / "results/c3_pod_artifacts_20261025"
TM_MIN, COV_MIN = 0.65, 0.80
MIN_COORDS = 20

PODS = [("p1", "63.141.33.138", 22113), ("p2", "194.68.245.32", 22065),
        ("p3", "69.30.85.102", 22129)]
AA3_TO_1 = {
    "ALA": "A", "ARG": "R", "ASN": "N", "ASP": "D", "CYS": "C", "GLN": "Q", "GLU": "E",
    "GLY": "G", "HIS": "H", "ILE": "I", "LEU": "L", "LYS": "K", "MET": "M", "PHE": "F",
    "PRO": "P", "SER": "S", "THR": "T", "TRP": "W", "TYR": "Y", "VAL": "V",
}
KEY = pathlib.Path.home() / ".ssh/runpod_ed25519"


def sh(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def _atom_site_layout(path):
    """Map _atom_site.* column names to 0-based indices, resolved from the loop header."""
    cols, in_loop = [], False
    for line in open(path):
        if line.startswith("_atom_site."):
            cols.append(line.split()[0][len("_atom_site."):])
        elif cols and line.startswith(("ATOM", "HETATM")):
            break
    if not cols:
        raise ValueError(f"{path}: no _atom_site columns")
    return {name: i for i, name in enumerate(cols)}


def load_cif_ca(path):
    """Binder chain (shortest) one-letter sequence + CA coords, from an RFD4 mmCIF.

    Column order differs between RFD4 outputs and the prepared target, so indices are
    resolved from the loop header. NaN coordinates are dropped (fail closed on too few).
    """
    idx = _atom_site_layout(path)
    need = ["label_asym_id", "label_seq_id", "label_comp_id", "label_atom_id",
            "Cartn_x", "Cartn_y", "Cartn_z"]
    missing = [n for n in need if n not in idx]
    if missing:
        raise ValueError(f"{path}: missing atom_site columns {missing}")
    seen, order, ca = {}, {}, {}
    for line in open(path):
        if not line.startswith("ATOM"):
            continue
        f = line.split()
        if len(f) <= max(idx[n] for n in need):
            continue
        asym = f[idx["label_asym_id"]]
        try:
            seq = int(f[idx["label_seq_id"]])
        except ValueError:
            continue
        key = (asym, seq)
        if key not in seen:
            seen[key] = f[idx["label_comp_id"]]
            order.setdefault(asym, []).append(key)
        if f[idx["label_atom_id"]] == "CA":
            try:
                xyz = (float(f[idx["Cartn_x"]]), float(f[idx["Cartn_y"]]), float(f[idx["Cartn_z"]]))
            except ValueError:
                continue
            if all(v == v for v in xyz):
                ca[key] = xyz
    if not order:
        raise ValueError(f"{path}: no ATOM records")
    small = min(order, key=lambda c: len(order[c]))
    keys = [k for k in order[small] if k in ca]
    if len(keys) < MIN_COORDS:
        raise ValueError(f"{path}: binder chain has {len(keys)} usable CA atoms")
    seqstr = "".join(AA3_TO_1.get(seen[k], "X") for k in keys)
    return seqstr, np.array([ca[k] for k in keys], dtype=float)


def recover():
    OUTDIR.mkdir(parents=True, exist_ok=True)
    BB.mkdir(parents=True, exist_ok=True)
    manifest = {}
    for name, host, port in PODS:
        ssh = ["ssh", "-n", "-i", str(KEY), "-o", "StrictHostKeyChecking=no",
               "-o", "ConnectTimeout=10", "-o", "BatchMode=yes", "-p", str(port),
               f"root@{host}"]
        listing = sh(ssh + ["ls /workspace/e3/out 2>/dev/null"])
        dirs = [d for d in listing.stdout.split() if d]
        print(f"{name}: {len(dirs)} output dirs")
        for d in dirs:
            # e3_<arm>_<bin>_<seed>
            m = re.match(r"e3_(ctrl|subA|subB)_(\d+_\d+)_(\d+)$", d)
            if not m:
                print(f"  SKIP unrecognised dir {d}")
                continue
            arm, bin_, seed = m.groups()
            remote = f"/workspace/e3/out/{d}"
            find = sh(ssh + [f"find {remote} -name '*generated.cif' -o -name '*.pdb' 2>/dev/null | head -20"])
            cands = [p for p in find.stdout.split() if p.endswith((".cif", ".pdb"))]
            if not cands:
                print(f"  {d}: no structure yet")
                continue
            pick = None
            for p in cands:
                if "generated.cif" in p.lower():
                    pick = p
                    break
            pick = pick or cands[0]
            local = BB / f"{d}{pathlib.Path(pick).suffix}"
            get = sh(["scp", "-q", "-i", str(KEY), "-o", "StrictHostKeyChecking=no",
                      "-o", "ConnectTimeout=10", "-P", str(port), f"root@{host}:{pick}",
                      str(local)])
            if get.returncode != 0 or not local.exists():
                print(f"  {d}: scp FAILED {get.stderr[:120]}")
                continue
            manifest[d] = {"arm": arm, "length_bin": bin_, "seed": int(seed),
                           "pod": name, "remote_path": pick,
                           "local": str(local.relative_to(ROOT))}
    (OUTDIR / "manifest.json").write_text(json.dumps(manifest, indent=1) + "\n")
    print(f"recovered {len(manifest)} backbones -> {BB}")
    return manifest


def load(path):
    keys, residues = read_binder(str(path))
    ca = [(k, next((x for x in residues[k] if x[0] == "CA"), None)) for k in keys]
    ca = [c for c in ca if c[1]]
    names = [c[1][1] for c in ca]
    coords = np.array([c[1][2] for c in ca], dtype=float)
    if len(coords) < MIN_COORDS:
        raise ValueError(f"{path}: only {len(coords)} CA atoms")
    return one_letter(names), coords


def main():
    try:
        from tmtools import tm_align
    except Exception as ex:
        print(f"tmtools unavailable ({ex}); cannot measure novelty", file=sys.stderr)
        return 2
    if "--no-recover" not in sys.argv:
        recover()
    e3 = {}
    for p in sorted(BB.iterdir()):
        if p.suffix == ".cif":
            e3[p.stem] = load_cif_ca(p)
        elif p.suffix == ".pdb":
            e3[p.stem] = load(p)
    r2 = {p.stem: load(p) for p in sorted(R2.glob("*.pdb"))}
    r1 = {p.name[:-len("_complex.pdb")]: load(p) for p in sorted(R1_DIR.glob("*_complex.pdb"))}
    print(f"E3 {len(e3)} | round2 {len(r2)} | round1 {len(r1)}")
    if not e3:
        print("no E3 backbones recovered", file=sys.stderr)
        return 3
    pairs, verdict = {}, {}
    for a, (sa, ca) in sorted(e3.items()):
        pairs[a] = {}
        for label, ref in (("r2", r2), ("r1", r1)):
            for b, (sb, cb) in sorted(ref.items()):
                r = tm_align(ca, cb, sa, sb)
                cov = min(sum(c != "-" for c in r.seqxA) / len(sa),
                          sum(c != "-" for c in r.seqyA) / len(sb))
                tm = float(r.tm_norm_chain2)
                pairs[a][f"{label}:{b}"] = {"tm": round(tm, 4), "coverage": round(cov, 4),
                                            "near_identical": bool(tm >= TM_MIN and cov >= COV_MIN)}
        near = sorted(k for k, v in pairs[a].items() if v["near_identical"])
        verdict[a] = {"novel": not near, "near_identical_to": near}
    n_novel = sum(1 for v in verdict.values() if v["novel"])
    arms = {}
    man = json.loads((OUTDIR / "manifest.json").read_text()) if (OUTDIR / "manifest.json").exists() else {}
    for a, v in verdict.items():
        arm = man.get(a, {}).get("arm", "?")
        d = arms.setdefault(arm, {"n": 0, "novel": 0})
        d["n"] += 1
        d["novel"] += int(v["novel"])
    out = {"rule": f"near-identical iff TM>={TM_MIN} AND coverage>={COV_MIN}; "
                   "tmtools tm_align on binder C-alpha traces (same convention as round 1/2)",
           "n_e3": len(e3), "n_round2": len(r2), "n_round1": len(r1),
           "n_novel": n_novel, "by_arm": arms, "pairs": pairs, "verdict": verdict}
    (OUTDIR / "novelty_20261025.json").write_text(json.dumps(out, indent=1) + "\n")
    print(f"novel {n_novel}/{len(e3)}; by arm {arms}")
    print(f"wrote {OUTDIR/'novelty_20261025.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
