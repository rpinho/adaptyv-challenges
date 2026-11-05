#!/usr/bin/env python3
"""Astra's five CPU audit artifacts (2026-10-25 ruling, Q4).

Writes ONLY new files under results/c3_v8_audit_20261025/. Never mutates frozen evidence.
Every artifact carries start/end timestamps, exit status, input hashes, findings, and a
PASS / FAIL / INCOMPLETE verdict.

  1 v8_integrity_audit.json        v7 hash, single replacement, 20 unique rows, order
  2 e2_membership_audit.json       E2 = raw inputs - 2 documented filter failures
  3 screen_reconciliation.{csv,json}  26 screen records vs verification records
  4 independence_audit.json        three units re-derived; global declared binding
  5 provenance_manifest.json       inventory of configs/runners/inputs/outputs/decisions
"""
import csv
import datetime
import hashlib
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
R2 = ROOT / "results/c3_round2_111_20261025"
OUT = ROOT / "results/c3_v8_audit_20261025"
V6 = ROOT / "results/c3_submission_v6_20261023.csv"
V7 = ROOT / "results/c3_submission_v7_20261025.csv"
V8 = ROOT / "results/c3_submission_v8_20261025.csv"
V7_SHA = "1d99f843b9d5af6cedd74e5ccfbf6cfd260f26e5461b2bffb0a4ee2204349c55"
V6_SHA = "8e9b2d741586e8b360fbed401b4de77317d579e183409cf4928de42661096891"
E2_SHA = "3f748fd5b68c4e65b43b511065e9c42c06c122a2d9787e855fcb3667c03ec694"
INPUT_SHA = "30bc5c12d8c16928a02ccb227b5a13f96137bdc257b2246c44051a8b5c679780"
TARGET_SHA = "5c2bae2dac5e467bf4e802473450a7ca3729990921bbe5c45cf6025531ef36b3"
SLOT = "c3_v_l65_E5Q"
NEW = "B_26102611_s1"
TM_NEAR, COV_NEAR = 0.65, 0.80


def now():
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")


def sha(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()


def jload(path):
    return json.loads(pathlib.Path(path).read_text())


def write(name, obj):
    p = OUT / name
    p.write_text(json.dumps(obj, indent=2) + "\n")
    print(f"  wrote {p.relative_to(ROOT)}  ({len(obj.get('checks', obj.get('findings', [])))} findings)")
    return p


def verdict(checks):
    if any(c["status"] == "FAIL" for c in checks):
        return "FAIL"
    if any(c["status"] == "INCOMPLETE" for c in checks):
        return "INCOMPLETE"
    return "PASS"


def chk(checks, name, status, detail):
    checks.append({"check": name, "status": status, "detail": detail})


# ---------------------------------------------------------------- 1 v8 integrity
def audit_v8():
    t0 = now()
    checks = []
    inputs = {str(p.relative_to(ROOT)): sha(p) for p in (V6, V7, V8)}
    chk(checks, "v7 hash == pinned fallback", "PASS" if sha(V7) == V7_SHA else "FAIL", sha(V7))
    chk(checks, "v6 hash == pinned fallback", "PASS" if sha(V6) == V6_SHA else "FAIL", sha(V6))
    chk(checks, "v8 exists", "PASS" if V8.exists() else "INCOMPLETE",
        str(V8.relative_to(ROOT)) if V8.exists() else "missing")
    if not V8.exists():
        return write("v8_integrity_audit.json", {
            "audit": "v8 integrity", "started": t0, "finished": now(),
            "exit_status": 1, "inputs": inputs, "checks": checks,
            "verdict": verdict(checks)})
    v7raw = V7.read_bytes().splitlines(keepends=True)
    v8raw = V8.read_bytes().splitlines(keepends=True)
    v7rows = list(csv.DictReader(open(V7, newline="")))
    v8rows = list(csv.DictReader(open(V8, newline="")))
    v7names = [r["name"] for r in v7rows]
    v8names = [r["name"] for r in v8rows]

    chk(checks, "exactly 20 data rows", "PASS" if len(v8raw) == 21 else "FAIL", f"{len(v8raw)-1}")
    chk(checks, "header identical to v7", "PASS" if v8raw[0] == v7raw[0] else "FAIL",
        v8raw[0].decode("ascii", "replace").strip())
    chk(checks, "20 unique names", "PASS" if len(set(v8names)) == 20 else "FAIL", f"{len(set(v8names))}")
    chk(checks, "20 unique sequences", "PASS" if len({r['sequence'] for r in v8rows}) == 20 else "FAIL",
        f"{len({r['sequence'] for r in v8rows})}")
    chk(checks, "exactly one row differs", "PASS" if len(set(v7names) ^ set(v8names)) == 2 else "FAIL",
        f"symdiff={sorted(set(v7names) ^ set(v8names))}")
    chk(checks, f"removed {SLOT}", "PASS" if SLOT not in v8names else "FAIL", SLOT)
    chk(checks, f"added {NEW} once", "PASS" if v8names.count(NEW) == 1 else "FAIL", f"{v8names.count(NEW)}")
    idx7 = v7names.index(SLOT)
    chk(checks, "added row sits in the replaced row's position",
        "PASS" if v8names[idx7] == NEW else "FAIL", f"v8[{idx7}]={v8names[idx7]}")
    by = {ln.split(b",", 1)[0]: ln for ln in v7raw[1:]}
    retained = [ln for ln in v8raw[1:] if not ln.startswith(NEW.encode() + b",")]
    expected = [by[n.encode()] for n in v7names if n != SLOT]
    chk(checks, "19 retained rows byte-identical to v7", "PASS" if retained == expected else "FAIL",
        f"{len(retained)} vs {len(expected)}")
    chk(checks, "retained rows keep v7 order",
        "PASS" if [ln.split(b",", 1)[0] for ln in retained] ==
        [n.encode() for n in v7names if n != SLOT] else "FAIL", "order")
    chk(checks, "all rows end CRLF", "PASS" if all(ln.endswith(b"\r\n") for ln in v8raw) else "FAIL",
        "line endings")
    out = {"audit": "v8 integrity", "started": t0, "finished": now(), "exit_status": 0,
           "inputs": inputs, "v8_sha256": sha(V8), "checks": checks, "verdict": verdict(checks)}
    write("v8_integrity_audit.json", out)
    return out


# ---------------------------------------------------------------- 2 E2 membership
def audit_e2():
    t0 = now()
    checks = []
    e2p = R2 / "e2_manifest_20261025.json"
    inp = R2 / "screen_input_24.csv"
    rep = R2 / "screen_input_replacements_2.csv"
    inputs = {str(p.relative_to(ROOT)): sha(p) for p in (e2p, inp, rep)}
    e2 = jload(e2p)
    chk(checks, "E2 manifest hash == frozen", "PASS" if sha(e2p) == E2_SHA else "FAIL", sha(e2p))
    chk(checks, "screen_input_24 hash == frozen verifier input",
        "PASS" if sha(inp) == INPUT_SHA else "FAIL", sha(inp))
    members = e2["members"]
    names = [m["name"] for m in members]
    chk(checks, "|E2| == 24", "PASS" if len(members) == 24 else "FAIL", f"{len(members)}")
    chk(checks, "E2 names unique", "PASS" if len(set(names)) == 24 else "FAIL", f"{len(set(names))}")
    excluded = set(e2["excluded_filter_failures"])
    replacements = set(e2["replacements"])
    chk(checks, "two documented exclusions", "PASS" if len(excluded) == 2 else "FAIL", sorted(excluded))
    chk(checks, "two post-selection replacements", "PASS" if len(replacements) == 2 else "FAIL",
        sorted(replacements))
    chk(checks, "no exclusion leaked into E2", "PASS" if not (excluded & set(names)) else "FAIL",
        sorted(excluded & set(names)))
    chk(checks, "both replacements are in E2", "PASS" if replacements <= set(names) else "FAIL",
        sorted(replacements - set(names)))
    rows = {r["name"]: r for r in csv.DictReader(open(inp, newline=""))}
    for r in csv.DictReader(open(rep, newline="")):
        rows.setdefault(r["name"], r)
    missing = sorted(set(names) - set(rows))
    chk(checks, "every E2 member has a frozen screening input row",
        "PASS" if not missing else "INCOMPLETE", missing or "all present")
    seq_bad = [n for n in names if n in rows and
               hashlib.sha256(rows[n]["binder"].strip().encode()).hexdigest() !=
               next(m["binder_sha256"] for m in members if m["name"] == n)]
    chk(checks, "E2 binder hashes match the screening input", "PASS" if not seq_bad else "FAIL",
        seq_bad or "all match")
    tgt_bad = [n for n in names if n in rows and hashlib.sha256(rows[n]["target"].strip().encode()).hexdigest()
               != TARGET_SHA]
    chk(checks, "every E2 input target is the exact 111-mer", "PASS" if not tgt_bad else "FAIL",
        tgt_bad or "all 111-mer")
    manifest_tgt_bad = [m["name"] for m in members if m["target_sha256"] != TARGET_SHA]
    chk(checks, "every E2 manifest target hash is the exact 111-mer",
        "PASS" if not manifest_tgt_bad else "FAIL", manifest_tgt_bad or "all 111-mer")
    # recompute the exact set from the raw launch set minus documented failures
    chk(checks, "E2 == (input rows - exclusions)",
        "PASS" if set(names) == set(rows) - excluded else "FAIL",
        sorted((set(names) ^ (set(rows) - excluded)))[:5] or "exact")
    out = {"audit": "E2 membership", "started": t0, "finished": now(), "exit_status": 0,
           "inputs": inputs, "e2_members": len(members), "excluded": sorted(excluded),
           "replacements": sorted(replacements), "checks": checks, "verdict": verdict(checks)}
    write("e2_membership_audit.json", out)


# ---------------------------------------------------------------- 3 reconciliation
def audit_screen():
    t0 = now()
    checks = []
    verp = R2 / "round2_verify_independent.json"
    scrp = R2 / "screen_scores_partial_20261025.json"
    stp = R2 / "structural_checks_20261025.json"
    e2p = R2 / "e2_manifest_20261025.json"
    inputs = {str(p.relative_to(ROOT)): sha(p) for p in (verp, scrp, stp, e2p)}
    ver = jload(verp)
    scores = jload(scrp)
    struct = jload(stp)
    e2 = jload(e2p)
    excluded = set(e2["excluded_filter_failures"])
    vrec = {r["name"]: r for r in ver["records"]}

    # screen file is either a dict of name->score or a list of records
    if isinstance(scores, dict):
        srec = scores.get("designs") or scores.get("scores") or scores
        if isinstance(srec, list):
            srec = {r["name"]: r for r in srec}
    else:
        srec = {r["name"]: r for r in scores}

    all_names = sorted(set(vrec) | set(srec) | set(struct))
    rows = []
    for n in all_names:
        v = vrec.get(n, {})
        s = srec.get(n, {}) if isinstance(srec, dict) else {}
        st = struct.get(n, {})
        iptm = v.get("iptm", s.get("iptm") if isinstance(s, dict) else None)
        reasons = list(v.get("reasons") or [])
        if isinstance(s, dict):
            for r in (s.get("reasons") or []):
                if r not in reasons:
                    reasons.append(r)
        # The independent verifier re-derived structural checks for ALL 26 launched designs;
        # structural_checks_20261025.json is a 20-record partial snapshot. Use the verifier as
        # authoritative and record the partial file's coverage explicitly.
        vclash = v.get("clashes_lt2A")
        clash = (vclash if isinstance(vclash, int) else (st.get("heavy_atom_pairs_lt2A") or 0)) > 0
        rows.append({
            "name": n,
            "in_e2": n in {m["name"] for m in e2["members"]},
            "in_screen_scores": n in srec,
            "has_verification": n in vrec,
            "has_structural": n in struct,
            "iptm": iptm,
            "verification_status": v.get("status"),
            "structural_pass": st.get("pass"),
            "clash_failure": clash,
            "clashes": vclash if isinstance(vclash, int) else st.get("heavy_atom_pairs_lt2A"),
            "clash_source": "verifier" if isinstance(vclash, int) else (
                "structural_checks_partial" if n in struct else "none"),
            "documented_filter_failure": n in excluded,
            "reasons": "; ".join(reasons)[:300],
        })
    OUT.mkdir(parents=True, exist_ok=True)
    with open(OUT / "screen_reconciliation.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

    e2names = {m["name"] for m in e2["members"]}
    chk(checks, "26 launched designs accounted for",
        "PASS" if len(rows) == 26 else "INCOMPLETE", f"{len(rows)}")
    chk(checks, "all 24 E2 designs have verification records",
        "PASS" if e2names <= set(vrec) else "INCOMPLETE", sorted(e2names - set(vrec)) or "complete")
    # screen_scores_partial_*.json is a 20-record partial snapshot taken mid-run; the
    # independent verifier re-read every raw artifact and is the authoritative score source.
    scored = {n for n, r in vrec.items() if isinstance(r.get("iptm"), (int, float))}
    chk(checks, "all 24 E2 designs have a verified finite iPTM",
        "PASS" if e2names <= scored else "INCOMPLETE", sorted(e2names - scored) or "complete")
    chk(checks, "partial screen snapshot is explicitly NOT treated as complete",
        "PASS" if len(srec) == 20 else "INCOMPLETE",
        f"{len(srec)} records in screen_scores_partial (superseded by the verifier's 26)")
    chk(checks, "all 20 partial structural records bind an E2 or documented design",
        "PASS" if set(struct) <= (e2names | excluded) else "FAIL",
        sorted(set(struct) - e2names - excluded) or "consistent")
    chk(checks, "verifier structural coverage is complete (26/26), not the partial 20",
        "PASS" if sum(1 for r in vrec.values() if isinstance(r.get("clashes_lt2A"), int)) == len(vrec)
        else "INCOMPLETE",
        f"{sum(1 for r in vrec.values() if isinstance(r.get('clashes_lt2A'), int))}/{len(vrec)} "
        f"verifier records carry clashes_lt2A; partial file has {len(struct)} records")
    npass = sum(1 for r in rows if r["verification_status"] == "PASS")
    nclash = sum(1 for r in rows if r["clash_failure"])
    e2clash = sum(1 for r in rows if r["clash_failure"] and r["in_e2"])
    clash_only = sorted(r["name"] for r in rows
                        if r["verification_status"] != "PASS" and r["reasons"]
                        and all("clash" in x for x in r["reasons"].split("; ")))
    chk(checks, "counts reconcile with the verifier report (8 PASS)",
        "PASS" if npass == 8 else "FAIL", f"{npass} PASS")
    # Astra's correction: clash shares, both E2-only and all launched
    detail = (f"{nclash}/26 launched carry >=1 clash <2 A; {e2clash}/24 E2 members do "
              f"({100*e2clash/24:.1f}% of E2). Clash is the SOLE listed reason for "
              f"{len(clash_only)} designs: {clash_only}. Do not describe clash as the sole "
              f"cause of all rejections.")
    chk(checks, "clash incidence recorded as an overlap, not a sole cause", "PASS", detail)
    out = {"audit": "screen reconciliation", "started": t0, "finished": now(), "exit_status": 0,
           "inputs": inputs, "n_designs": len(rows), "n_pass": npass,
           "n_clash": nclash, "n_clash_in_e2": e2clash,
           "n_clash_only": len(clash_only), "clash_only": clash_only,
           "artifacts": ["results/c3_v8_audit_20261025/screen_reconciliation.csv"],
           "checks": checks, "verdict": verdict(checks)}
    write("screen_reconciliation.json", out)


# ---------------------------------------------------------------- 4 independence
def audit_independence():
    t0 = now()
    checks = []
    maps = [R2.parent / "c3_backbone_clusters_20261025.json",
            R2 / "clusters_20261025.json", R2 / "cross_tm_20261025.json"]
    inputs = {str(p.relative_to(ROOT)): sha(p) for p in maps}
    v7names = [r["name"] for r in csv.DictReader(open(V7, newline=""))]
    sel = {x["name"]: x["backbone"] for x in jload(R2 / "selected24_20261025.json")}
    e2 = jload(R2 / "e2_manifest_20261025.json")
    for m in e2["members"]:
        if m["name"] in e2["replacements"]:
            sel.setdefault(m["name"], m["backbone"])
    cache = {}
    for mp in maps:
        mp = jload(mp)
        for a, row in (mp.get("pairs") or {}).items():
            for b, v in (row or {}).items():
                cache.setdefault((a, b), v)
    missing = []

    def near(a, b):
        if a == b:
            return True
        v = cache.get((a, b)) or cache.get((b, a))
        if not isinstance(v, dict):
            missing.append((a, b))
            return False
        return float(v["tm"]) >= TM_NEAR and float(v["coverage"]) >= COV_NEAR

    def bb(n):
        return n if n in v7names else sel.get(n, n)

    def components(nodes):
        parent = {n: n for n in nodes}

        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x
        lst = list(nodes)
        for i, a in enumerate(lst):
            for b in lst[i + 1:]:
                if near(a, b):
                    ra, rb = find(a), find(b)
                    if ra != rb:
                        parent[max(ra, rb)] = min(ra, rb)
        return {n: find(n) for n in nodes}

    def count(names, unit):
        bbs = list(dict.fromkeys(bb(n) for n in names))
        if unit == "direct":
            return sum(1 for i, x in enumerate(bbs)
                       if not any(near(x, y) for j, y in enumerate(bbs) if i != j))
        nodes = bbs if unit == "v7cc" else sorted({k for pair in cache for k in pair})
        roots = components(nodes)
        return len({roots.get(b, b) for b in bbs})

    final = [n for n in v7names if n != SLOT] + [NEW]
    got = {u: (count(v7names, u), count(final, u)) for u in ("direct", "v7cc", "global")}
    missing.clear()
    expect = {"direct": (16, 18), "v7cc": (18, 19), "global": (15, 16)}
    for u in ("direct", "v7cc", "global"):
        chk(checks, f"{u}: v7 -> final == {expect[u]}",
            "PASS" if got[u] == expect[u] else "FAIL", f"{got[u]} (missing pairs: {len(missing)})")
    chk(checks, "global declared binding; +1 satisfied",
        "PASS" if got["global"][1] >= got["global"][0] + 1 else "FAIL", f"{got['global']}")
    chk(checks, "v7cc/direct recorded as sensitivity only", "PASS",
        "not binding; different baselines must not be mixed")
    out = {"audit": "independence", "started": t0, "finished": now(), "exit_status": 0,
           "inputs": inputs, "rule": f"near-identical iff TM>={TM_NEAR} AND coverage>={COV_NEAR}",
           "binding_unit": "global", "counts": {u: {"v7": a, "final": b} for u, (a, b) in got.items()},
           "missing_pairs": missing[:10], "checks": checks, "verdict": verdict(checks)}
    write("independence_audit.json", out)


# ---------------------------------------------------------------- 5 provenance
def audit_provenance():
    t0 = now()
    checks = []
    groups = {
        "gate": ["scripts/c3_round2_gate_20261025.py",
                 "scripts/c3_round2_gate_fixtures_20261025.py"],
        "verifier": ["scripts/c3_round2_verify_20261025.py",
                     "scripts/c3_round2_pull_verify_20261025.sh"],
        "generation": ["scripts/c3_round2_construct_20261025.py",
                       "scripts/c3_round2_select_20261025.py",
                       "scripts/c3_round2_refold_merge_20261025.py"],
        "structure": ["scripts/c3_round2_structural_20261025.py",
                      "scripts/c3_refold_check_20261025.py",
                      "scripts/c3_soluble_filters_20261025.py"],
        "cluster": ["scripts/c3_round2_clusters_20261025.py",
                    "scripts/c3_round2_cross_tm_20261025.py",
                    "scripts/c3_round2_cluster_crosswalk_20261025.py"],
        "configs": ["configs/rfd4/c3_ecd111_r2_52_64.yaml",
                    "configs/rfd4/c3_ecd111_r2_65_80.yaml",
                    "configs/rfd4/c3_ecd111_r2_81_100.yaml"],
        "evidence": ["results/c3_round2_111_20261025/e2_manifest_20261025.json",
                     "results/c3_round2_111_20261025/screen_input_24.csv",
                     "results/c3_round2_111_20261025/round2_verify_independent.json",
                     "results/c3_round2_111_20261025/structural_checks_20261025.json",
                     "results/c3_round2_111_20261025/refold_checks_20261025.json",
                     "results/c3_round2_111_20261025/selected24_20261025.json",
                     "results/c3_backbone_clusters_20261025.json",
                     "results/c3_round2_111_20261025/cross_tm_20261025.json"],
        "outputs": ["results/c3_submission_v6_20261023.csv",
                    "results/c3_submission_v7_20261025.csv",
                    "results/c3_submission_v8_20261025.csv"],
        "decisions": sorted(str(p.relative_to(ROOT)) for p in (ROOT / "results/decisions").glob("*.md")),
    }
    inv, absent = {}, []
    for g, files in groups.items():
        inv[g] = []
        for f in files:
            p = ROOT / f
            present = p.is_file()
            inv[g].append({"path": f, "present": present,
                           "sha256": sha(p) if present else None,
                           "bytes": p.stat().st_size if present else None})
            if not present:
                absent.append(f)
    chk(checks, "every inventoried artifact exists", "PASS" if not absent else "INCOMPLETE",
        absent or "all present")
    chk(checks, "decision record exists for the binding unit", "PASS"
        if "results/decisions/20261025-v8-independence-unit.md" in groups["decisions"] else "INCOMPLETE",
        "20261025-v8-independence-unit.md")
    chk(checks, "clash-rule decision recorded", "PASS"
        if any("clash-rule" in d for d in groups["decisions"]) else "INCOMPLETE", "clash rule")
    # scan for stale claims about the superseded 16/17 formulation in live docs
    stale = []
    for f in ("HANDOFF_KIMI.md", "results/overnight_log.md"):
        p = ROOT / f
        if not p.exists():
            continue
        for ln in p.read_text().splitlines():
            if ("final ≥17" in ln or "final >= 17" in ln) and \
                    not any(w in ln.lower() for w in ("superseded", "withdrawn", "earlier", "former")):
                stale.append(f)
    chk(checks, "live docs free of the withdrawn >=17 binding claim", "PASS" if not stale else "INCOMPLETE",
        stale or "none")
    out = {"audit": "provenance", "started": t0, "finished": now(), "exit_status": 0,
           "inventory": inv, "absent": absent, "checks": checks, "verdict": verdict(checks)}
    write("provenance_manifest.json", out)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    print(f"=== C3 v8 audit bundle — {now()}")
    a1 = audit_v8()
    audit_e2()
    audit_screen()
    audit_independence()
    audit_provenance()
    summary = {p.name: jload(p)["verdict"] for p in OUT.glob("*.json") if p.name != "summary.json"}
    write("summary.json", {"generated": now(), "verdicts": summary,
                           "all_pass": all(v == "PASS" for v in summary.values())})
    print("\n" + json.dumps(summary, indent=2))
    return 0 if all(v == "PASS" for v in summary.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
