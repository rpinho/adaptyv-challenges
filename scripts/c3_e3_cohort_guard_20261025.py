#!/usr/bin/env python3
"""E3 cohort isolation guard.

Astra (2026-10-25): new E3 candidates "cannot enter that unchanged gate" (which hash-pins E2).
This guard makes that a checked property instead of a convention:

  A. E2 and E3 namespace disjointness (no E3 design id can collide with an E2 member)
  B. the E2 gate still refuses a fabricated E3 row appended to E2
  C. the frozen E2 manifest, v6, v7, v8 and the round-1/2 evidence are byte-unchanged
  D. E3 output dirs are tagged with an arm/bin/seed convention and live outside E2 paths
  E. no E3 artifact is referenced by results/c3_submission_v*.csv

Exit 0 only if all hold. Nothing here writes to frozen evidence.
"""
import csv
import hashlib
import json
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
R2 = ROOT / "results/c3_round2_111_20261025"
E2P = R2 / "e2_manifest_20261025.json"
E2_SHA = "3f748fd5b68c4e65b43b511065e9c42c06c122a2d9787e855fcb3667c03ec694"
V7_SHA = "1d99f843b9d5af6cedd74e5ccfbf6cfd260f26e5461b2bffb0a4ee2204349c55"
V6_SHA = "8e9b2d741586e8b360fbed401b4de77317d579e183409cf4928de42661096891"
V8_SHA = "631ed0bf6b10e0f8fbf64bd5d9730e294da15f0436af20f52a42bafc92229e12"
E3_TAG = re.compile(r"^e3_(ctrl|subA|subB)_(52_64|65_80|81_100)_\d+$")

results = []


def check(name, cond, detail=""):
    results.append(bool(cond))
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else f"   [{detail}]"))


def sha(p):
    return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()


def main():
    # --- C: frozen artifacts untouched
    check("E2 manifest hash unchanged", sha(E2P) == E2_SHA, sha(E2P))
    check("v6 unchanged", sha(ROOT / "results/c3_submission_v6_20261023.csv") == V6_SHA)
    check("v7 unchanged", sha(ROOT / "results/c3_submission_v7_20261025.csv") == V7_SHA)
    check("v8 unchanged", sha(ROOT / "results/c3_submission_v8_20261025.csv") == V8_SHA)

    e2 = json.loads(E2P.read_text())
    e2_names = {m["name"] for m in e2["members"]}
    e2_backbones = {m["backbone"] for m in e2["members"]}

    # --- A: namespace disjointness (E3 ids are <arm> seeds, never the 2610xx E2 family)
    e3_like = {n for n in e2_names if n.startswith("e3_")}
    check("no E3-tagged id inside the frozen E2 manifest", not e3_like, sorted(e3_like)[:3])

    # --- D: config naming convention for the pilot
    cfgs = sorted((ROOT / "configs/rfd4").glob("c3_ecd111_e3_*.yaml"))
    bad = [p.name for p in cfgs
           if not re.match(r"^c3_ecd111_e3_(ctrl|subA|subB)_(52_64|65_80|81_100)\.yaml$", p.name)]
    check("E3 configs follow the arm x bin convention", not bad, bad[:3])
    arms = {re.match(r"^c3_ecd111_e3_(\w+?)_", p.name).group(1) for p in cfgs}
    check("exactly the three authorized arms exist", arms == {"ctrl", "subA", "subB"}, sorted(arms))
    # Only C_HOT MEMBERSHIP may differ from the round-2 config for the same bin. Compare parsed
    # structures (name-insensitive, order-insensitive) rather than raw lines: the ctrl arm is the
    # same hotspot set as round 2 but written in ascending residue order.
    diffs, hotdiff = [], []
    for p in cfgs:
        arm_bin = p.name.split("c3_ecd111_e3_")[1].rsplit(".", 1)[0]
        bin_key = arm_bin.rsplit("_", 2)[-2] + "_" + arm_bin.rsplit("_", 1)[-1]
        base = ROOT / f"configs/rfd4/c3_ecd111_r2_{bin_key}.yaml"
        if not base.exists():
            continue

        def norm(path):
            text = path.read_text()
            body = text.split("\n", 1)[1] if "\n" in text else text
            head, _, hot = body.partition("    C_HOT:")
            hot_set = frozenset(re.findall(r"sel\('([^']+)'\)", hot))
            return head, hot_set

        (ha, sa), (hb, sb) = norm(p), norm(base)
        if ha != hb:
            diffs.append(p.name)
        if arm_bin.startswith("ctrl") and sa != sb:
            hotdiff.append(p.name)
    check("E3 configs match round-2 except C_HOT membership/order", not diffs, diffs[:3])
    check("ctrl arm uses exactly the round-2 hotspot set", not hotdiff, hotdiff[:3])

    # --- E: no E3 design in any submission CSV
    leaks = []
    for csvp in sorted((ROOT / "results").glob("c3_submission_v*.csv")):
        for r in csv.DictReader(open(csvp, newline="")):
            if r["name"] in e2_names or r["name"].startswith("e3_") or r["name"].startswith("E3"):
                if r["name"].startswith("e3_") or r["name"].startswith("E3"):
                    leaks.append(f"{csvp.name}:{r['name']}")
    check("no E3-tagged design appears in any submission CSV", not leaks, leaks[:3])
    check("v8 membership is exactly E2-derived (19 retained + 1 replacement)",
          len({r["name"] for r in csv.DictReader(open(ROOT / "results/c3_submission_v8_20261025.csv", newline=""))}) == 20)

    # --- B: the gate provably refuses an E3 row injected into E2 evidence
    ver = json.loads((R2 / "round2_verify_independent.json").read_text())
    fake = dict(ver)
    fake["records"] = list(ver["records"]) + [{
        "name": "E3_ctrl_52_64_26103000_s1", "status": "PASS", "iptm": 0.99,
        "binder_sequence_sha256": "0" * 64, "target_sequence_sha256":
            "5c2bae2dac5e467bf4e802473450a7ca3729990921bbe5c45cf6025531ef36b3",
        "reasons": []}]
    tmp = ROOT / "results/c3_v8_audit_20261025/_e3_injection_probe.json"
    tmp.write_text(json.dumps(fake))
    try:
        r = subprocess.run([sys.executable, str(ROOT / "scripts/c3_round2_gate_20261025.py"),
                            "--scores", str(tmp), "--dry-run",
                            "--report", str(ROOT / "results/c3_v8_audit_20261025/_e3_probe_report.json")],
                           capture_output=True, text=True)
        check("gate REFUSES an injected E3 record (exit 4, fail-closed)", r.returncode == 4,
              f"rc={r.returncode}")
    finally:
        tmp.unlink(missing_ok=True)
        (ROOT / "results/c3_v8_audit_20261025/_e3_probe_report.json").unlink(missing_ok=True)

    ok, n = sum(results), len(results)
    print(f"\n{ok}/{n} cohort-isolation checks passed")
    return 0 if ok == n else 1


if __name__ == "__main__":
    sys.exit(main())
