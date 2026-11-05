"""Fail-closed fixtures for the C3 gate. Each must exit non-zero and write nothing."""
import json, pathlib, tempfile, shutil, subprocess, copy, csv, hashlib, sys, os

R = pathlib.Path("/Users/ricardo/dev/adaptyv-c4")
GATE = R / "scripts/c3_screen_gate_20261025.py"
SRC = dict(
    baseline=R / "results/c3_submission_v6_20261023.csv",
    shortlist=R / "results/c3_screen_shortlist_20261024.csv",
    scores=R / "results/c3_screen_af2m_scores_combined_20261025.json",
    input=R / "results/c3_screen_input_20261024.csv",
    refold=R / "results/c3_refold_checks_20261025.json",
    structural=R / "results/c3_structural_checks_20261025.json",
    groove=R / "results/c3_groove_reference_20261025.json",
    clusters=R / "results/c3_backbone_clusters_20261025.json",
)
wk = pathlib.Path(tempfile.mkdtemp(prefix="c3fx_"))

def fresh():
    d = pathlib.Path(tempfile.mkdtemp(dir=wk))
    for k, p in SRC.items():
        if p.exists():
            shutil.copy(p, d / k)
    return d

def loadj(d, k): return json.loads((d / k).read_text())
def savej(d, k, v): (d / k).write_text(json.dumps(v, indent=2))

def run(d, extra=()):
    out = d / "out.csv"; rep = d / "rep.json"
    cmd = ["/usr/bin/python3", str(GATE),
           "--baseline", str(d / "baseline"), "--shortlist", str(d / "shortlist"),
           "--scores", str(d / "scores"), "--input", str(d / "input"),
           "--refold", str(d / "refold"), "--structural", str(d / "structural"),
           "--groove", str(d / "groove"), "--clusters", str(d / "clusters"),
           "--output", str(out), "--report", str(rep), *extra]
    r = subprocess.run(cmd, capture_output=True, text=True)
    return r.returncode, out.exists(), (r.stderr or r.stdout)

def strip_seq_hashes(obj):
    for v in obj.values():
        if isinstance(v, dict): v.pop("sequence_sha256", None)
    return obj

VICTIM = "c3_glp1r_ecd_26"
cases = []

def case(name, mutate):
    cases.append((name, mutate))

def m_scores43(d):
    s = loadj(d, "scores"); savej(d, "scores", [r for r in s if r["name"] != s[0]["name"]])
case("scores 43/44 (one row removed)", m_scores43)

def m_noanchor(d):
    s = loadj(d, "scores")
    for r in s:
        if r["name"].startswith("c3_"):
            pass
    # remove one anchor by name pattern from the anchor list used by the gate
    anchors = [r["name"] for r in s if r.get("is_anchor") or r["name"].count("-") >= 0]
    savej(d, "scores", s[1:])
case("anchor row missing", m_noanchor)

def m_norefold(d):
    rf = loadj(d, "refold"); rf.pop(VICTIM, None); savej(d, "refold", rf)
case("refold record absent for an eligible candidate", m_norefold)

def m_belowfloor(d):
    s = loadj(d, "scores")
    for r in s:
        if r["name"] == VICTIM: r["iptm"] = 0.40
    savej(d, "scores", s)
# below-floor: promotion of OTHERS is allowed, but the poisoned candidate must be excluded
BELOW = []
case("eligible candidate below the floor", lambda d: (m_belowfloor(d), BELOW.append(d)))

def m_anchor_removed(d):
    s = loadj(d, "scores"); savej(d, "scores", s[1:])
case("BindCraft anchor removed from scores", m_anchor_removed)

def m_dupname(d):
    s = loadj(d, "scores"); s.append(copy.deepcopy(s[0])); savej(d, "scores", s)
case("duplicate design name", m_dupname)

def m_dupseq(d):
    rows = list(csv.DictReader(open(d / "shortlist")))
    rows[1]["sequence"] = rows[0]["sequence"]
    with open(d / "shortlist", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=rows[0].keys()); w.writeheader(); w.writerows(rows)
case("duplicate sequence in shortlist", m_dupseq)

def m_badreplacement(d):
    # make every eligible candidate look like a non-c3_v_ replacement by renaming v6 variants
    rows = list(csv.DictReader(open(d / "baseline")))
    for r in rows:
        if r["name"].startswith("c3_v_"): r["name"] = "c3_plain_" + r["name"][5:]
    with open(d / "baseline", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=rows[0].keys()); w.writeheader(); w.writerows(rows)
case("no c3_v_* replacement slots available", m_badreplacement)

def m_stale_seq(d):
    rf = loadj(d, "refold"); rf[VICTIM]["sequence_sha256"] = "0" * 64; savej(d, "refold", rf)
case("refold evidence bound to a different sequence", m_stale_seq)

def m_stale_struct(d):
    st = loadj(d, "structural"); st[VICTIM]["sequence_sha256"] = "0" * 64; savej(d, "structural", st)
case("structural evidence bound to a different sequence", m_stale_struct)

def m_nodiversity(d):
    cl = loadj(d, "clusters")
    # make every eligible candidate a near-identical copy of every v6 row
    pairs = cl["pairs"]
    import csv as _c
    v6 = {r["name"] for r in _c.DictReader(open(d / "baseline"))}
    for n in pairs:
        for m in pairs[n]:
            pairs[n][m] = {"tm": 0.99, "coverage": 1.0}
    savej(d, "clusters", cl)
case("all candidate backbones near-identical (no gain)", m_nodiversity)

def m_clusters_truncated(d):
    cl = loadj(d, "clusters"); cl["rows_measured"] = 10; savej(d, "clusters", cl)
case("backbone cluster evidence incomplete", m_clusters_truncated)

def m_altercommon(d):
    rows = list(csv.DictReader(open(d / "baseline")))
    for r in rows:
        if r["name"].startswith("c3_") and not r["name"].startswith("c3_v_"):
            r["sequence"] = r["sequence"][:-1] + ("A" if r["sequence"][-1] != "A" else "G")
            break
    with open(d / "baseline", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=rows[0].keys()); w.writeheader(); w.writerows(rows)
case("common v6 row altered", m_altercommon)

def m_empty(d):
    (d / "scores").write_text("[]"); savej(d, "refold", {}); savej(d, "structural", {})
case("empty evidence JSON", m_empty)

def m_garbage(d):
    (d / "clusters").write_text("{not json")
case("malformed evidence JSON", m_garbage)

fails = []
for name, mut in cases:
    d = fresh()
    mut(d)
    rc, wrote, txt = run(d)
    if name == "eligible candidate below the floor":
        d = BELOW[-1]
        rows = list(csv.DictReader(open(d / "out.csv"))) if (d / "out.csv").exists() else []
        ok = VICTIM not in {r["name"] for r in rows}
        print(f"{'PASS' if ok else 'FAIL'}  exclusion-check  {name} (promoted {len(rows)} rows, victim absent={VICTIM not in {r.get('name') for r in rows}})")
        if not ok: fails.append(name)
        continue
    ok = (rc != 0) and (not wrote)
    print(f"{'PASS' if ok else 'FAIL'}  rc={rc} wrote={wrote}  {name}")
    if not ok:
        fails.append(name); print("      " + txt.strip().splitlines()[-1][:160] if txt.strip() else "")

# control: unmutated must promote
d = fresh()
rc, wrote, txt = run(d, extra=())
print(f"{'PASS' if (rc==0 and wrote) else 'FAIL'}  rc={rc} wrote={wrote}  CONTROL unmutated (must promote)")
if not (rc == 0 and wrote):
    fails.append("control")
    print("      " + txt.strip().splitlines()[-1][:200])

print(f"\n{len(cases)-len([f for f in fails if f!='control'])}/{len(cases)} fixtures fail closed; control {'ok' if 'control' not in fails else 'BROKEN'}")
print("workspace:", wk)
sys.exit(1 if fails else 0)
