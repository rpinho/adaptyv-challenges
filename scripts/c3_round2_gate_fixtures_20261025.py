#!/usr/bin/env python3
"""Fixtures for the v8 gate. Builds a synthetic-but-complete evidence set in a temp dir,
mutates one thing at a time, and asserts the gate's exit code and that nothing is written.

The point is the FAIL-OPEN regressions Kimi called out:
  * a missing (candidate, retained) TM pair must be exit 4, never "independent";
  * near-identical candidates must be rejected;
  * a later addition must not undo the independent-count gain.

Exit 0 if every fixture behaves as specified.
"""
import csv
import hashlib
import json
import pathlib
import shutil
import subprocess
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
GATE = ROOT / "scripts/c3_round2_gate_20261025.py"
V7 = ROOT / "results/c3_submission_v7_20261025.csv"
V7_SHA = "1d99f843b9d5af6cedd74e5ccfbf6cfd260f26e5461b2bffb0a4ee2204349c55"
INPUT_SHA = "30bc5c12d8c16928a02ccb227b5a13f96137bdc257b2246c44051a8b5c679780"
R2 = ROOT / "results/c3_round2_111_20261025"
E2 = R2 / "e2_manifest_20261025.json"
TARGET = ("TVSLWETVQKWREYRRQCQRSLTEDPPPATDLFCNRTFDEYACWPDGEPGSFVNVSCPWYLPWASSVPQGHVYRF"
          "CTAEGLWLQKDNSSLPWRDLSECEESSPEEQLLFLY")
TARGET_SHA = hashlib.sha256(TARGET.encode()).hexdigest()
AA = "ACDEFGHIKLMNPQRSTVWY"


def sha(s):
    return hashlib.sha256(s.encode()).hexdigest()


def good_seq(n, seed):
    """Soluble-looking: charged/polar, low GRAVY, no hydrophobic run."""
    base = "EELKKRREELKQREELKKRREELKQREELKKRREELKQREELKKRR"
    return (base * 4)[:n] if n <= len(base) * 4 else (base * 4 + "EEKKRR" * 20)[:n]


results = []


def case(name, cond, extra=""):
    results.append(bool(cond))
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else f"  {extra}"))


def build(tmp, *, drop_pair=None, near_pair=None, incomplete=None, floor_break=None,
          near_bridge=None):
    """Write a self-consistent evidence set against the REAL frozen E2 manifest.

    The gate hash-pins E2, so the fixture must use the real member names/sequences/backbones.
    Only the scores, TM measurements and pass/fail verdicts are synthetic."""
    t = pathlib.Path(tmp)
    base = list(csv.DictReader(open(V7)))
    base_names = [r["name"] for r in base]
    real_e2 = json.loads(E2.read_text())
    members = real_e2["members"]
    real_inputs = {}
    for path in (R2 / "screen_input_24.csv", R2 / "screen_input_replacements_2.csv"):
        for r in csv.DictReader(open(path)):
            real_inputs[r["name"]] = r
    missing = [m["name"] for m in members if m["name"] not in real_inputs]
    if missing:
        raise SystemExit(f"fixture setup: E2 members missing from real inputs: {missing[:3]}")

    cand = "A_26102502_s2"
    if cand not in {m["name"] for m in members}:
        raise SystemExit("fixture setup: intended candidate not in E2")
    input_rows, records, sel = [], [], []
    # The real raw launch set includes the two documented filter failures; E2 projects them out.
    for name in real_e2.get("excluded_filter_failures") or []:
        row = real_inputs[name]
        input_rows.append({"name": name, "binder": row["binder"].strip(),
                           "target": row["target"].strip(), "source": "r2_111"})
        records.append({"name": name, "status": "fail", "iptm": 0.50,
                        "binder_sequence_sha256": sha(row["binder"].strip()),
                        "target_sequence_sha256": TARGET_SHA,
                        "reasons": ["documented filter failure"]})
    replacements = set(real_e2.get("replacements") or [])
    for m in members:
        name = m["name"]
        row = real_inputs[name]
        seq = row["binder"].strip()
        input_rows.append({"name": name, "binder": seq, "target": row["target"].strip(),
                           "source": "r2_111"})
        rec = {"name": name, "status": "PASS",
               "iptm": (0.84 if name == floor_break else 0.95) if name == cand else 0.50,
               "binder_sequence_sha256": sha(seq), "target_sequence_sha256": TARGET_SHA,
               "reasons": []}
        records.append(rec)
        if name not in replacements:
            sel.append({"name": name, "backbone": m["backbone"],
                        "cluster": m.get("cluster_round2")})
    if incomplete:
        for r in records:
            if r["name"] == incomplete:
                r["status"] = "incomplete"
                r["reasons"] = ["artifact absent"]
                r.pop("iptm", None)

    # TM maps: round-1 (baseline rows pairwise), round-2, cross
    # Reproduce v7's REAL baseline count (16 direct singletons). Two disjoint pairs must
    # be near-identical, otherwise base_indep would be 20 and the gate must correctly refuse.
    # Mirrors real v7: the replaceable slot is itself redundant with a retained row,
    # so removing it (and adding an independent design) raises the count.
    NEAR_BASE = [("c3_v_l65_E5Q", base_names[0]), (base_names[2], base_names[3])]
    near_lookup = {frozenset(x) for x in NEAR_BASE}
    r1 = {"pairs": {}}
    for i, a in enumerate(base_names):
        for b in base_names[i + 1:]:
            v = ({"tm": 0.9, "coverage": 0.95} if frozenset((a, b)) in near_lookup
                 else {"tm": 0.1, "coverage": 0.5})
            r1["pairs"].setdefault(a, {})[b] = dict(v)
            r1["pairs"].setdefault(b, {})[a] = dict(v)
    r2 = {"pairs": {}}
    bb_names = sorted({m["backbone"] for m in members})
    for i, a in enumerate(bb_names):
        for b in bb_names[i + 1:]:
            r2["pairs"].setdefault(a, {})[b] = {"tm": 0.1, "coverage": 0.5}
            r2["pairs"].setdefault(b, {})[a] = r2["pairs"][a][b]
    cross = {"pairs": {}}
    for a in bb_names:
        for b in base_names:
            cross["pairs"].setdefault(a, {})[b] = {"tm": 0.1, "coverage": 0.5}
    # v7's REAL global baseline is 15, not the 18 components visible inside v7 alone:
    # discarded designs bridge v7 seats. Encode three such bridges so the fixture exercises
    # the binding global unit end to end. Each bridge row is connected to everything else at
    # 0.1 and to exactly two v7 rows at 0.9 (so it merges exactly those two components).
    BRIDGES = [("r1_bridge_a", 4, 5), ("r1_bridge_b", 6, 7), ("r1_bridge_c", 8, 9)]
    bridge_names = [b for b, _, _ in BRIDGES]
    for br, i, j in BRIDGES:
        for b in base_names:
            cross["pairs"].setdefault(br, {})[b] = {"tm": 0.1, "coverage": 0.5}
        cross["pairs"][br][base_names[i]] = {"tm": 0.9, "coverage": 0.95}
        cross["pairs"][br][base_names[j]] = {"tm": 0.9, "coverage": 0.95}
        for other in bridge_names:
            if other != br:
                cross["pairs"].setdefault(br, {})[other] = {"tm": 0.1, "coverage": 0.5}
        for a in bb_names:
            cross["pairs"].setdefault(br, {})[a] = {"tm": 0.1, "coverage": 0.5}
    if drop_pair:
        a, b = drop_pair
        cross["pairs"].get(a, {}).pop(b, None)
    if near_pair:
        a, b = near_pair
        cross["pairs"].setdefault(a, {})[b] = {"tm": 0.9, "coverage": 0.95}
    if near_bridge:
        a, br = near_bridge
        a = a.rsplit("_s", 1)[0]          # the measured node is the parent backbone
        cross["pairs"].setdefault(a, {})[br] = {"tm": 0.9, "coverage": 0.95}

    refold = {r["name"]: {"pass": True, "ca_rmsd_vs_designed_backbone": 0.5,
                          "refold_mean_plddt": 90.0,
                          "refold_frac_residues_plddt_ge70": 0.95,
                          "sequence": r["binder"]} for r in input_rows}

    p = t / "screen_input_24.csv"
    with open(p, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["name", "binder", "target", "source"])
        w.writeheader()
        w.writerows(input_rows)
    files = {
        "input": p,
        "scores_json": t / "verify.json",
        "refold": t / "refold.json",
        "refold_input": t / "refold_input.csv",
        "tm_round1": t / "tm1.json",
        "tm_round2": t / "tm2.json",
        "tm_cross": t / "tmcross.json",
        "report": t / "report.json",
        "output": t / "v8.csv",
        "selection": t / "selection.json",
        "e2": t / "e2.json",
    }
    files["selection"].write_text(json.dumps(sel))
    files["e2"].write_bytes(E2.read_bytes())
    files["scores_json"].write_text(json.dumps({"records": records,
                                                "input_sha256": INPUT_SHA}))
    files["refold"].write_text(json.dumps(refold))
    with open(files["refold_input"], "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["name", "sequence"])
        w.writeheader()
        w.writerows({"name": r["name"], "sequence": r["binder"]} for r in input_rows)
    files["tm_round1"].write_text(json.dumps(r1))
    files["tm_round2"].write_text(json.dumps(r2))
    files["tm_cross"].write_text(json.dumps(cross))
    # copy v7 so the baseline path is stable inside the temp dir
    files["baseline"] = t / "v7.csv"
    shutil.copy(V7, files["baseline"])
    return files, cand


def run(files, *extra):
    cmd = [sys.executable, str(GATE),
           "--baseline", str(files["baseline"]),
           "--input", str(files["input"]),
           "--scores", str(files["scores_json"]),
           "--refold", str(files["refold"]),
           "--refold-input", str(files["refold_input"]),
           "--tm-round1", str(files["tm_round1"]),
           "--tm-round2", str(files["tm_round2"]),
           "--tm-cross", str(files["tm_cross"]),
           "--selection", str(files["selection"]),
           "--e2", str(files["e2"]),
           "--output", str(files["output"]),
           "--report", str(files["report"]), *extra]
    r = subprocess.run(cmd, capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr


with tempfile.TemporaryDirectory() as tmp:
    files, cand = build(tmp)
    rc, out = run(files)
    case("CONTROL: complete independent candidate promotes (rc=0)", rc == 0, out[-600:])
    case("CONTROL: v8 file written with 20 rows",
         files["output"].exists() and len(list(csv.DictReader(open(files["output"])))) == 20)
    rep = json.loads(files["report"].read_text())
    case("CONTROL: write-mode report names the written path",
         rep.get("wrote") == str(files["output"]) and rep.get("dry_run") is False, rep)
    if files["output"].exists():
        rows = list(csv.DictReader(open(files["output"])))
        case("CONTROL: candidate replaced c3_v_l65_E5Q",
             cand in {r["name"] for r in rows} and "c3_v_l65_E5Q" not in {r["name"] for r in rows})
        case("CONTROL: v7 untouched", hashlib.sha256(open(files["baseline"], "rb").read()).hexdigest() == V7_SHA)

with tempfile.TemporaryDirectory() as tmp:
    files, cand = build(tmp)
    rc, out = run(files, "--dry-run")
    rep = json.loads(files["report"].read_text())
    case("CONTROL: dry-run exits 0 with a promotable set", rc == 0, out[-600:])
    case("CONTROL: dry-run writes no output file", not files["output"].exists())
    case("CONTROL: dry-run report says wrote=null + dry_run=true",
         rep.get("wrote") is None and rep.get("dry_run") is True, rep)

with tempfile.TemporaryDirectory() as tmp:
    files, cand = build(tmp, drop_pair=("A_26102502", "c3_glp1r_ecd_14"))
    rc, out = run(files)
    case("MISSING TM PAIR is exit 4 (never 'independent')", rc == 4, out[-400:])
    case("MISSING TM PAIR writes nothing", not files["output"].exists())

with tempfile.TemporaryDirectory() as tmp:
    files, cand = build(tmp, near_pair=("A_26102502", "c3_glp1r_ecd_14"))
    rc, out = run(files)
    case("NEAR-IDENTICAL candidate is not promoted (rc=3)", rc == 3, out[-400:])
    case("NEAR-IDENTICAL writes nothing", not files["output"].exists())

with tempfile.TemporaryDirectory() as tmp:
    files, cand = build(tmp, incomplete="B_26102604_s2")
    rc, out = run(files)
    case("INCOMPLETE screen is exit 4", rc == 4, out[-400:])

with tempfile.TemporaryDirectory() as tmp:
    files, cand = build(tmp, floor_break="A_26102502_s2")
    rc, out = run(files)
    case("BELOW-FLOOR candidate is not promoted (rc=3)", rc == 3, out[-400:])

# The binding unit is global components. A candidate that is NOT directly near any retained
# row but is joined to one through a discarded bridge design adds no independent cluster and
# must be refused (Astra: reject indirect connections too).
with tempfile.TemporaryDirectory() as tmp:
    files, cand = build(tmp, near_bridge=(cand, "r1_bridge_a"))
    rc, out = run(files)
    case("INDIRECT bridge to a represented cluster is rc=3", rc == 3, out[-500:])
    case("INDIRECT bridge writes nothing", not files["output"].exists())

# The other selectable units keep their own measured pins; the default must be `global`.
for unit, base in (("direct", "16"), ("v7cc", "18"), ("global", "15")):
    with tempfile.TemporaryDirectory() as tmp:
        files, cand = build(tmp)
        rc, out = run(files, "--independence", unit, "--dry-run")
        case(f"UNIT {unit}: pinned v7 baseline {base} reproduces (rc=0)", rc == 0, out[-500:])
        case(f"UNIT {unit}: run reports baseline {base}",
             f"baseline v7 independent count reproduced = {base}" in out, out[-500:])

with tempfile.TemporaryDirectory() as tmp:
    files, cand = build(tmp)
    d = json.loads(files["scores_json"].read_text())
    for r in d["records"]:
        if r["name"] == "A_26102502_s2":
            r["binder_sequence_sha256"] = "0" * 64
    files["scores_json"].write_text(json.dumps(d))
    rc, out = run(files)
    case("UNBOUND sequence is exit 4", rc == 4, out[-400:])

with tempfile.TemporaryDirectory() as tmp:
    files, cand = build(tmp)
    files["baseline"].write_text(files["baseline"].read_text() + "\n")
    rc, out = run(files)
    case("MUTATED baseline hash is exit 4", rc == 4, out[-400:])

with tempfile.TemporaryDirectory() as tmp:
    files, cand = build(tmp)
    d = json.loads(files["scores_json"].read_text())
    for r in d["records"]:
        if r["name"] == cand:
            r["status"] = "fail"
            r["reasons"] = ["1 heavy-atom clash < 2.0 A"]
    files["scores_json"].write_text(json.dumps(d))
    rc, out = run(files)
    case("VERIFIER-FAILED candidate is not promoted (rc=3)", rc == 3, out[-400:])

with tempfile.TemporaryDirectory() as tmp:
    files, cand = build(tmp)
    d = json.loads(files["scores_json"].read_text())
    d["records"].pop()
    files["scores_json"].write_text(json.dumps(d))
    rc, out = run(files)
    case("MISSING E2 MEMBER is exit 4", rc == 4, out[-400:])
    case("MISSING E2 MEMBER writes nothing", not files["output"].exists())

with tempfile.TemporaryDirectory() as tmp:
    files, cand = build(tmp)
    d = json.loads(files["scores_json"].read_text())
    d["records"].append(dict(d["records"][0]))
    files["scores_json"].write_text(json.dumps(d))
    rc, out = run(files)
    case("DUPLICATE E2 record is exit 4", rc == 4, out[-400:])

with tempfile.TemporaryDirectory() as tmp:
    files, cand = build(tmp)
    d = json.loads(files["scores_json"].read_text())
    d["records"].append({"name": "Z_UNDOCUMENTED_s1", "status": "PASS", "iptm": 0.99})
    files["scores_json"].write_text(json.dumps(d))
    rc, out = run(files)
    case("UNDOCUMENTED extra record is exit 4", rc == 4, out[-400:])

with tempfile.TemporaryDirectory() as tmp:
    files, cand = build(tmp)
    d = json.loads(files["scores_json"].read_text())
    d["input_sha256"] = "0" * 64
    files["scores_json"].write_text(json.dumps(d))
    rc, out = run(files)
    case("STALE verifier input hash is exit 4", rc == 4, out[-400:])

with tempfile.TemporaryDirectory() as tmp:
    files, cand = build(tmp)
    d = json.loads(files["scores_json"].read_text())
    for r in d["records"]:
        if r["name"] == cand:
            r["target_sequence_sha256"] = "0" * 64
    files["scores_json"].write_text(json.dumps(d))
    rc, out = run(files)
    case("UNBOUND evidence target is exit 4", rc == 4, out[-400:])

with tempfile.TemporaryDirectory() as tmp:
    files, cand = build(tmp)
    rows = list(csv.DictReader(open(files["input"])))
    for r in rows:
        if r["name"] == cand:
            r["target"] = "A" * 111
    with open(files["input"], "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["name", "binder", "target", "source"])
        w.writeheader(); w.writerows(rows)
    rc, out = run(files)
    case("WRONG input target is exit 4", rc == 4, out[-400:])

with tempfile.TemporaryDirectory() as tmp:
    files, cand = build(tmp)
    d = json.loads(files["e2"].read_text())
    d["members"].append({"name": "Z_EXTRA_s1", "backbone": "Z_EXTRA",
                         "binder_sha256": "0" * 64, "target_sha256": TARGET_SHA})
    files["e2"].write_text(json.dumps(d))
    rc, out = run(files)
    case("MUTATED E2 manifest hash is exit 4", rc == 4, out[-400:])

with tempfile.TemporaryDirectory() as tmp:
    files, cand = build(tmp)
    rc, out = run(files)
    if files["output"].exists():
        raw = files["output"].read_bytes().splitlines(keepends=True)
        v7raw = V7.read_bytes().splitlines(keepends=True)
        v7_by = {ln.split(b",", 1)[0]: ln for ln in v7raw[1:]}
        retained = [ln for ln in raw[1:] if not ln.startswith(cand.encode())]
        expected = [v7_by[n.encode()] for n in
                    [r["name"] for r in csv.DictReader(open(V7))]
                    if n != "c3_v_l65_E5Q"]
        case("RETAINED rows are byte-identical to v7", retained == expected)
        case("v8 preserves CRLF line endings", raw[0].endswith(b"\r\n"))

with tempfile.TemporaryDirectory() as tmp:
    files, cand = build(tmp)
    d = json.loads(files["tm_cross"].read_text())
    d["pairs"]["A_26102502"]["c3_glp1r_ecd_14"] = {"tm": "nan", "coverage": 0.9}
    files["tm_cross"].write_text(json.dumps(d))
    rc, out = run(files)
    case("NON-FINITE TM is exit 4", rc == 4, out[-400:])

with tempfile.TemporaryDirectory() as tmp:
    files, cand = build(tmp)
    d = json.loads(files["tm_cross"].read_text())
    d["pairs"]["A_26102502"]["c3_glp1r_ecd_14"] = {"tm": 1.7, "coverage": 0.9}
    files["tm_cross"].write_text(json.dumps(d))
    rc, out = run(files)
    case("OUT-OF-RANGE TM is exit 4", rc == 4, out[-400:])

n, ok = len(results), sum(results)
print(f"\n{ok}/{n} fixtures behaved as specified")
sys.exit(0 if ok == n else 1)
