#!/usr/bin/env python3
"""R3 preflight: exact Kimi allocation, config diff, real seed collision, target hash.

Read-only. Exit 0 only if every check passes; any failure is printed and exits 4.
Seed collisions are checked against actual RFD4 manifests/logs, never decision prose.
"""
import hashlib, json, pathlib, re, subprocess, sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
CFG = ROOT / "configs/rfd4"
R3CFG = CFG / "r3"
TARGET_SHA = "5c2bae2dac5e467bf4e802473450a7ca3729990921bbe5c45cf6025531ef36b3"
ALLOC = {
 "p1": [("H8","52_64",range(910000,910024))],
 "p2": [("H8","65_80",range(910100,910124))],
 "p3": [("H8","81_100",range(910200,910224))],
 "p4": [("H8","52_64",range(910024,910032)),("H8","65_80",range(910124,910132)),
        ("H8","81_100",range(910224,910232))],
 "p5": [("H4","52_64",range(910300,910308)),("H4","65_80",range(910400,910408)),
        ("H4","81_100",range(910500,910508))],
}

def sha(p): return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()

def cfg_name(tag, b):
    return R3CFG / f"c3_ecd111_r3_{tag.lower()}_{b}.yaml"

def main():
    errs = []
    total = 0
    seen = {}
    for pod, jobs in ALLOC.items():
        for tag, b, seeds in jobs:
            p = cfg_name(tag, b)
            if not p.exists(): errs.append(f"missing config {p}"); continue
            r2 = (CFG / f"c3_ecd111_r2_{b}.yaml").read_text().splitlines()
            got = p.read_text().splitlines()
            i2 = r2.index("    C_HOT:"); ig = got.index("    C_HOT:")
            if r2[1:i2] != got[1:ig]: errs.append(f"{p.name}: non-hotspot lines differ from R2")
            if tag == "H8":
                if len(r2) != len(got) or r2[1:] != got[1:]:
                    errs.append(f"{p.name}: H8 differs from R2 beyond name")
            else:
                want = ["    C_HOT:","      true:",
                 "        - select: \"sel('F/*/5/[CE2,NE1]')\"",
                 "        - select: \"sel('F/*/40/[OE1,OE2]')\"",
                 "        - select: \"sel('F/*/63/[CE2,NE1]')\"",
                 "        - select: \"sel('F/*/93/[NH1,NH2]')\""]
                if got[ig:] != want: errs.append(f"{p.name}: H4 hotspot block wrong")
            for s in seeds:
                total += 1
                if s in seen: errs.append(f"duplicate allocation seed {s}: {seen[s]} + {pod}")
                seen[s] = pod
    # Real seed collision check: only execution manifests/logs, no decision prose.
    # The R3 evidence namespace is the subject of this preflight, not an independent
    # prior run: counting it would make every planned seed collide with itself.
    r3_ns = ROOT / "results/c3_r3_20261025"
    real, prior_r3 = set(), set()
    for p in list((ROOT/"results").rglob("*.jsonl")) + list((ROOT/"results").rglob("*.log")):
        if "decisions" in p.parts: continue
        # records.jsonl is the merged 120-row admission manifest: every allocated seed
        # appears there even when no pod record exists. It is not an execution log.
        if p.parent == r3_ns and p.name == "records.jsonl": continue
        try: txt = p.read_text(errors="ignore")
        except Exception: continue
        if "rfd4" not in txt.lower() and "e3" not in txt.lower() and "seed=" not in txt.lower():
            continue
        for m in re.finditer(r"(?:seed=|\"seed\":\s*)(26\d{6}|910\d{3})\b", txt):
            (prior_r3 if r3_ns in p.parents else real).add(int(m.group(1)))
    hits = sorted(set(seen) & real)
    if hits: errs.append(f"seed collisions with real runs: {hits}")
    # target hash from all configs
    for p in R3CFG.glob("c3_ecd111_r3_*.yaml"):
        txt = p.read_text()
        if "c3_ecd111_af2m_target_20261025.cif" not in txt:
            errs.append(f"{p.name}: target path unexpected")
    tgt = ROOT/"data/c3_ecd111_af2m_target_20261025.cif"
    file_sha = None
    if not tgt.exists():
        errs.append("target CIF missing")
    else:
        file_sha = sha(tgt)
    # Kimi's 5c2bae2d... is the 111-aa SEQUENCE hash (the gate's identity check),
    # not the CIF file hash. Verify the sequence from the CIF chain F.
    seq_sha = None
    try:
        sys.path.insert(0, str(ROOT/"scripts"))
        from c3_round2_construct_20261025 import verify
        v = verify(tgt)
        seq_sha = v["target_sequence_sha256"]
    except Exception as ex:
        errs.append(f"target sequence cannot be verified: {ex}")
    if seq_sha and seq_sha != TARGET_SHA:
        errs.append(f"target sequence sha {seq_sha} != {TARGET_SHA}")
    print(json.dumps({"allocated":total,"unique":len(seen),"collisions":hits,
       "prior_r3_attempt_seeds":sorted(prior_r3),
       "prior_r3_reused_seeds":sorted(set(seen) & prior_r3),
       "configs":[{"path":str(p.relative_to(ROOT)),"sha256":sha(p)}
                  for p in sorted(R3CFG.glob("c3_ecd111_r3_*.yaml"))],
       "target_file_sha256":file_sha,"target_sequence_sha256":seq_sha,"errors":errs},indent=1))
    return 4 if errs else 0

if __name__ == "__main__": sys.exit(main())
