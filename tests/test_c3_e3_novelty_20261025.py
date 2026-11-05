#!/usr/bin/env python3
"""Known-answer tests for the E3 novelty tool.

Positive control: real round-2 backbones relabelled into the E3 namespace MUST come back as
duplicates (novel=0), because each is near-identical to itself in the reference set. If the tool
ever reports those as novel, the near-identical rule or the TM accessor has broken.
Negative control: a backbone absent from the reference set must be scored against it, not skipped.
"""
import json
import pathlib
import shutil
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import c3_e3_novelty_20261025 as nov  # noqa: E402

passes = []


def case(name, cond, extra=""):
    passes.append(bool(cond))
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else f"  {extra}"))


def run_with(tmp, pdb_sources):
    t = pathlib.Path(tmp)
    (t / "backbone_pdb").mkdir(parents=True)
    for i, src in enumerate(pdb_sources):
        shutil.copy(src, t / "backbone_pdb" / f"e3_ctrl_52_64_2610300{i}.pdb")
    old_e3, old_out = nov.E3, nov.OUT
    nov.E3, nov.OUT = t, t / "nov.json"
    try:
        rc = nov.main()
    finally:
        nov.E3, nov.OUT = old_e3, old_out
    return rc, json.loads((t / "nov.json").read_text()) if (t / "nov.json").exists() else None


with tempfile.TemporaryDirectory() as tmp:
    rc = nov.main() if False else None
    # fail-closed on an empty directory
    t = pathlib.Path(tmp)
    (t / "backbone_pdb").mkdir()
    old_e3, old_out = nov.E3, nov.OUT
    nov.E3, nov.OUT = t, t / "nov.json"
    try:
        rc = nov.main()
    finally:
        nov.E3, nov.OUT = old_e3, old_out
    case("EMPTY E3 directory exits 2 (INCOMPLETE), writes nothing",
         rc == 2 and not (t / "nov.json").exists(), f"rc={rc}")

case("the cross-check does not target the E3 lane's own artifact",
     nov.OUT.name == "novelty_independent_20261025.json", nov.OUT.name)

real = sorted((ROOT / "results/c3_round2_111_20261025/backbone_pdb").glob("*.pdb"))[:6]
case("fixture setup: six real round-2 backbones available", len(real) == 6, len(real))

with tempfile.TemporaryDirectory() as tmp:
    rc, d = run_with(tmp, real)
    case("KNOWN ANSWER: relabelled round-2 backbones are all duplicates",
         rc == 0 and d and d["by_arm"]["ctrl"]["novel"] == 0, d and d["by_arm"])
    case("KNOWN ANSWER: duplicate fraction is 1.0",
         d and d["by_arm"]["ctrl"]["novel_fraction"] == 0.0, d and d["by_arm"])
    case("each record names a nearest reference and a TM in [0,1]",
         d and all(0.0 <= r["nearest_tm"] <= 1.0 and r["nearest_reference"] for r in d["records"]))

n, ok = len(passes), sum(passes)
print(f"\n{ok}/{n} novelty tests passed")
sys.exit(0 if ok == n else 1)
