#!/usr/bin/env python3
"""C3 ROUND-2 / v8 promotion gate — FAIL-CLOSED, measured-evidence only.

Separate from c3_screen_gate_20261025.py on purpose: that script is the writer of the frozen
v7 artifact and must stay byte-reproducible. This one writes ONLY a new v8 file.

Baseline: results/c3_submission_v7_20261025.csv (sha pinned below), NOT v6.
Replacement: EXACTLY ONE row, `c3_v_l65_E5Q` (Kimi v8 ruling 2026-10-25, §5).

Every promotion condition, all required simultaneously:

  1. v7 baseline hash matches the recorded value; v7 has 20 unique rows/sequences.
  2. The round-2 screen is complete over the FROZEN E2 manifest (e2_manifest_20261025.json):
     exactly one usable verification record for every E2 member, no duplicates, and the
     canonical candidate set equals E2 exactly (not merely length 24). The two documented
     filter failures are excluded from E2 but retained in the raw launch ledger.
  3. Every candidate record is SEQUENCE-BOUND on BOTH sides: the evidence row's binder_sequence_sha256
     equals sha256 of the frozen input sequence, the input target sha256 equals the exact
     111-mer hash (5c2bae2d...), and the evidence target sha256 equals the same value.
  4. An added candidate passes: iptm >= 0.850, refold eligible (pLDDT>=80, frac70>=0.90,
     CA RMSD<=3.0 vs designed backbone), structural checks (binder pLDDT>=80, >=5 groove
     residues, >=20 contacts <=5A, 0 clashes <2A, no chain-integrity problem), and the four
     pre-registered soluble filters.
  5. INDEPENDENCE IS MEASURED, NEVER ASSUMED (Kimi 2026-10-25, Option B): every
     (candidate, other-final-row) TM/coverage pair must exist in measured evidence.
     A missing pair is an EVIDENCE FAILURE (exit 4), not independence. A candidate is
     acceptable only if it is near-identical to NO other row in the FINAL output
     (TM>=0.65 AND coverage>=0.80 is near-identical).
  6. The final independent-backbone count must rise by >=1 over the reproduced v7 baseline,
     and every addition is re-checked against the whole final set (no `and not chosen`
     exemption). BINDING UNIT (Kimi + Astra, 2026-10-25, `results/decisions/
     20261025-v8-independence-unit.md`): global connected components over all measured
     designs, v7 baseline 15, minimum final 16. `--independence` remains selectable for
     audit only; it defaults to `global` and each unit keeps its own measured baseline pin.
  7. EXACTLY ONE replacement, 20 rows, unique names/sequences, the other 19 rows copied
     BYTE-FOR-BYTE from v7 in v7 order, atomic write, v7 never modified.

Exit codes: 0 written / 3 no promotion (evidence complete, criteria unmet) /
            4 missing/invalid evidence (fail-closed, nothing written).
"""
import argparse
import csv
import hashlib
import json
import math
import os
import pathlib
import sys
import tempfile

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import c3_soluble_filters_20261025 as soluble  # noqa: E402

R2 = ROOT / "results/c3_round2_111_20261025"
DEFAULT_BASE = ROOT / "results/c3_submission_v7_20261025.csv"
V7_SHA = "1d99f843b9d5af6cedd74e5ccfbf6cfd260f26e5461b2bffb0a4ee2204349c55"
TARGET_SHA = "5c2bae2dac5e467bf4e802473450a7ca3729990921bbe5c45cf6025531ef36b3"  # 111-mer
E2_SHA = "3f748fd5b68c4e65b43b511065e9c42c06c122a2d9787e855fcb3667c03ec694"
INPUT_SHA = "30bc5c12d8c16928a02ccb227b5a13f96137bdc257b2246c44051a8b5c679780"
FLOOR = 0.850
AUDIT_FLOOR = 0.76
TM_NEAR, COV_NEAR = 0.65, 0.80
# (baseline, minimum final) for each independence universe. Measured on the frozen evidence:
#   direct = rows not near-identical to any other FINAL row (the earlier "16 independent" pin)
#   v7cc   = connected components restricted to the final 20 rows
#   global = connected components over every measured design (excluded designs may bridge seats)
INDEPENDENCE = {"direct": (16, 17), "v7cc": (18, 19), "global": (15, 16)}
REPLACE_SLOT = "c3_v_l65_E5Q"
MIN_REPLACE = MAX_REPLACE = 1
HEADER = ["name", "sequence", "molecule_class"]
CANON = set("ACDEFGHIKLMNPQRSTVWY")


class EvidenceError(Exception):
    pass


def sha(s):
    return hashlib.sha256(s.encode()).hexdigest()


def jaccard(a, b, k=3):
    ka = {a[i:i + k] for i in range(len(a) - k + 1)}
    kb = {b[i:i + k] for i in range(len(b) - k + 1)}
    return len(ka & kb) / len(ka | kb) if (ka | kb) else 0.0


def load_json(path, label):
    p = pathlib.Path(path)
    if not p.exists():
        raise EvidenceError(f"{label}: file missing ({p})")
    try:
        d = json.loads(p.read_text())
    except Exception as ex:
        raise EvidenceError(f"{label}: unreadable JSON ({ex})")
    if not isinstance(d, dict) or not d:
        raise EvidenceError(f"{label}: empty or malformed evidence")
    return d


class TMMap:
    """Measured TM/coverage pairs. Missing or malformed data is an EvidenceError, never 0."""

    def __init__(self, maps):
        self.maps = maps
        self.cache = {}
        for m in maps:
            for a, row in (m.get("pairs") or {}).items():
                for b, v in (row or {}).items():
                    self.cache.setdefault((a, b), v)

    def get(self, a, b):
        if a == b:
            return {"tm": 1.0, "coverage": 1.0}
        v = self.cache.get((a, b)) or self.cache.get((b, a))
        if v is None:
            raise EvidenceError(f"no measured TM/coverage for pair ({a}, {b}) — "
                                "independence cannot be inferred from missing data")
        if not isinstance(v, dict) or "tm" not in v or "coverage" not in v:
            raise EvidenceError(f"malformed TM record for ({a}, {b}): {v!r}")
        try:
            tm, cov = float(v["tm"]), float(v["coverage"])
        except Exception:
            raise EvidenceError(f"non-numeric TM record for ({a}, {b}): {v!r}")
        if not (math.isfinite(tm) and math.isfinite(cov)):
            raise EvidenceError(f"non-finite TM record for ({a}, {b})")
        if not (0.0 <= tm <= 1.0 and 0.0 <= cov <= 1.0):
            raise EvidenceError(f"out-of-range TM record for ({a}, {b}): tm={tm} cov={cov}")
        return {"tm": tm, "coverage": cov}

    def near(self, a, b):
        v = self.get(a, b)
        return v["tm"] >= TM_NEAR and v["coverage"] >= COV_NEAR

    def nodes(self):
        """All design/backbone names for which at least one measured pair exists."""
        out = set()
        for m in self.maps:
            for a, row in (m.get("pairs") or {}).items():
                out.add(a)
                out.update((row or {}).keys())
        return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--baseline", default=str(DEFAULT_BASE))
    ap.add_argument("--input", default=str(R2 / "screen_input_24.csv"))
    ap.add_argument("--scores", default=str(R2 / "round2_verify_independent.json"))
    ap.add_argument("--refold", default=str(R2 / "refold_checks_20261025.json"))
    ap.add_argument("--refold-input", default=str(R2 / "refold_input_72.csv"),
                    help="exact sequences submitted to ESMFold for the round-2 refolds")
    ap.add_argument("--tm-round1", default=str(ROOT / "results/c3_backbone_clusters_20261025.json"))
    ap.add_argument("--tm-round2", default=str(R2 / "clusters_20261025.json"))
    ap.add_argument("--tm-cross", default=str(R2 / "cross_tm_20261025.json"))
    ap.add_argument("--selection", default=str(R2 / "selected24_20261025.json"),
                    help="frozen as-run selection; the ONLY source of design->backbone mapping")
    ap.add_argument("--e2", default=str(R2 / "e2_manifest_20261025.json"),
                    help="frozen E2 candidate manifest (exact-set completeness)")
    ap.add_argument("--independence", choices=sorted(INDEPENDENCE), default="global",
                    help="audit-only unit for the independence count; the binding rule is "
                         "global components, v7 baseline 15, minimum final 16")
    ap.add_argument("--expect-baseline", type=int, default=None,
                    help="test-only pin override for the baseline count")
    ap.add_argument("--output", default=str(ROOT / "results/c3_submission_v8_20261025.csv"))
    ap.add_argument("--report", default=str(ROOT / "results/c3_round2_gate_20261025_report.json"))
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    checks = []

    def rec(status, detail):
        checks.append({"status": status, "detail": detail})
        print(f"  {status:<4s} {detail}")

    def finish(code):
        pathlib.Path(a.report).write_text(json.dumps(
            {"gate": "C3 round-2 / v8", "checks": checks, "exit_code": code,
             "dry_run": bool(a.dry_run),
             "wrote": None if (code or a.dry_run) else str(a.output)}, indent=2))
        print(f"(report: {a.report})")
        return code

    print("=== C3 ROUND-2 / v8 gate — fail-closed, measured evidence only ===")
    try:
        ver = load_json(a.scores, "round-2 verification")
        refold = load_json(a.refold, "refold")
        refold_inputs = {r["name"]: r["sequence"].strip()
                         for r in csv.DictReader(open(a.refold_input))}
        tm = TMMap([load_json(a.tm_round1, "tm round1"),
                    load_json(a.tm_round2, "tm round2"),
                    load_json(a.tm_cross, "tm cross")])
        input_rows = list(csv.DictReader(open(a.input)))
        inputs = {r["name"]: r for r in input_rows}
        extra_path = pathlib.Path(a.input).with_name("screen_input_replacements_2.csv")
        if extra_path.exists():
            for r in csv.DictReader(open(extra_path)):
                inputs.setdefault(r["name"], r)
        base = list(csv.DictReader(open(a.baseline)))
        e2 = load_json(a.e2, "E2 manifest")
    except EvidenceError as ex:
        rec("FAIL", str(ex))
        print("\nDECISION: NO PROMOTION — evidence missing/invalid (fail-closed); nothing written.")
        return finish(4)
    except Exception as ex:
        rec("FAIL", f"input unreadable ({ex})")
        return finish(4)

    # --- 1 baseline
    baseline_bytes = open(a.baseline, "rb").read()
    cur = hashlib.sha256(baseline_bytes).hexdigest()
    if cur != V7_SHA:
        rec("FAIL", f"baseline sha256 {cur[:16]}… != recorded v7 {V7_SHA[:16]}…")
        return finish(4)
    if len(base) != 20 or len({r["name"] for r in base}) != 20 or \
            len({r["sequence"] for r in base}) != 20:
        rec("FAIL", "baseline is not 20 unique rows/sequences")
        return finish(4)
    rec("ok", "baseline v7 sha256 matches; 20 unique rows/sequences")

    base_names = [r["name"] for r in base]
    base_seq = {r["name"]: r["sequence"] for r in base}
    fixed = [n for n in base_names if n != REPLACE_SLOT]
    if REPLACE_SLOT not in base_names:
        rec("FAIL", f"permitted replacement slot {REPLACE_SLOT} is absent from v7")
        return finish(4)
    rec("ok", f"permitted replacement slot present and unique: {REPLACE_SLOT}")

    # --- 1b frozen E2 exact-set completeness (Kimi v8 ruling §2)
    e2_actual = hashlib.sha256(pathlib.Path(a.e2).read_bytes()).hexdigest()
    if e2_actual != E2_SHA:
        rec("FAIL", f"E2 manifest sha256 {e2_actual[:16]}… != frozen {E2_SHA[:16]}…")
        return finish(4)
    members = e2.get("members")
    if not isinstance(members, list) or len(members) != 24:
        rec("FAIL", "E2 manifest is not a 24-member list")
        return finish(4)
    e2_names = [m.get("name") for m in members if isinstance(m, dict)]
    e2_set = set(e2_names)
    excluded = set(e2.get("excluded_filter_failures") or [])
    if not excluded or not excluded <= set(inputs):
        rec("FAIL", f"documented filter failures are missing from the raw screen input: "
                    f"{sorted(excluded - set(inputs))}")
        return finish(4)
    projected = set(inputs) - excluded
    if len(e2_names) != 24 or len(e2_set) != 24 or e2_set != projected:
        rec("FAIL", f"E2 set != canonical candidate input set after projecting the 2 documented "
                    f"noncandidates (E2={len(e2_set)}, projected={len(projected)}, "
                    f"symmetric diff={sorted(e2_set ^ projected)[:4]})")
        return finish(4)
    if excluded & e2_set:
        rec("FAIL", "a documented filter failure is still inside E2")
        return finish(4)
    e2_by = {m["name"]: m for m in members}
    rec("ok", f"E2 exact set reproduced: {len(e2_set)} unique candidates, 2 documented "
              f"filter failures excluded, 2 replacements included")

    # the verifier's report must have been produced from exactly this frozen input
    if ver.get("input_sha256") != INPUT_SHA:
        rec("FAIL", f"verification report input sha256 {str(ver.get('input_sha256'))[:16]}… "
                    f"!= frozen {INPUT_SHA[:16]}… (stale or foreign evidence)")
        return finish(4)
    rec("ok", "verification report was produced from the frozen screen_input_24.csv")

    # --- 2/3 screen completeness + sequence binding
    all_records = [r for r in ver.get("records", []) if isinstance(r, dict)]
    records = {}
    for r in all_records:
        n = r.get("name")
        if n in records:
            rec("FAIL", f"duplicate verification record for {n}")
            return finish(4)
        records[n] = r
    if not records:
        rec("FAIL", "verification evidence contains no records")
        return finish(4)
    # The raw artifact may contain up to 26 launched designs (the 24 + 2 documented failures).
    # The canonical candidate set is E2; anything else must be explicitly documented.
    allowed_extra = set(excluded)
    undocumented = set(records) - e2_set - allowed_extra
    if undocumented:
        rec("FAIL", f"undocumented verification record(s), not in E2: {sorted(undocumented)[:4]}")
        return finish(4)
    canonical = set(records) & e2_set
    if canonical != e2_set:
        rec("FAIL", f"canonical verification set != E2 (missing {sorted(e2_set - canonical)[:4]})")
        return finish(4)
    gaps = []
    for name in sorted(e2_set):
        row = inputs[name]
        r = records.get(name)
        if not isinstance(r, dict):
            gaps.append(f"{name}: no verification record")
            continue
        if r.get("status") == "incomplete":
            gaps.append(f"{name}: artifact not yet verified")
            continue
        if not isinstance(r.get("iptm"), (int, float)):
            gaps.append(f"{name}: no finite iptm")
        if r.get("binder_sequence_sha256") != sha(row["binder"]):
            gaps.append(f"{name}: binder sequence not bound to evidence")
        if sha(row["target"]) != TARGET_SHA:
            gaps.append(f"{name}: frozen input target is not the exact 111-mer")
        if r.get("target_sequence_sha256") != TARGET_SHA:
            gaps.append(f"{name}: evidence target is not the exact 111-mer")
        m = e2_by[name]
        if m.get("binder_sha256") != sha(row["binder"]):
            gaps.append(f"{name}: E2 manifest binder hash does not match frozen input")
        if m.get("target_sha256") != TARGET_SHA:
            gaps.append(f"{name}: E2 manifest target hash is not the exact 111-mer")
    if gaps:
        rec("FAIL", f"screen evidence incomplete or unbound for {len(gaps)} design(s): {gaps[:3]}")
        print("\nDECISION: NO PROMOTION — evidence incomplete (fail-closed); nothing written.")
        return finish(4)
    rec("ok", f"all {len(e2_set)} E2 designs verified and sequence-bound on both sides to the "
              f"exact 111-mer")

    # --- 4 candidate eligibility
    eligible, rejected = [], []
    missing_refold_input = sorted(e2_set - set(refold_inputs))
    if missing_refold_input:
        rec("FAIL", f"no ESMFold input sequence for {len(missing_refold_input)} E2 member(s): "
                    f"{missing_refold_input[:4]}")
        return finish(4)
    for name in sorted(e2_set):
        row = inputs[name]
        r = records[name]
        seq = row["binder"]
        why = []
        if refold_inputs[name] != seq:
            why.append("refold input sequence differs from the frozen candidate sequence")
        if r["iptm"] < FLOOR:
            why.append(f"iptm {r['iptm']:.3f} < {FLOOR}")
        if r.get("status") != "PASS":
            why.append(f"independent verification status={r.get('status')}: "
                       f"{'; '.join(r.get('reasons', []))[:120]}")
        rf = refold.get(name)
        if not isinstance(rf, dict):
            gaps.append(f"{name}: refold record absent")
            continue
        if not isinstance(rf, dict) or not rf.get("pass"):
            why.append("refold not eligible")
        else:
            if rf.get("sequence") not in (None, seq):
                why.append("refold sequence not bound")
            if (rf.get("ca_rmsd_vs_designed_backbone") or 9e9) > 3.0:
                why.append("refold RMSD > 3.0")
            if (rf.get("refold_mean_plddt") or 0) < 80:
                why.append("refold pLDDT < 80")
            if (rf.get("refold_frac_residues_plddt_ge70") or 0) < 0.90:
                why.append("refold frac70 < 0.90")
        for reason in soluble.failures(seq):
            why.append(f"soluble_filter:{reason}")
        (eligible if not why else rejected).append(
            {"name": name, "reasons": why, "iptm": r["iptm"]})
    if gaps:
        rec("FAIL", f"supporting refold evidence incomplete for {len(gaps)} design(s): {gaps[:3]}")
        return finish(4)
    rec("info", f"{len(eligible)} of {len(e2_set)} screened designs are fully eligible "
                f"({len(rejected)} rejected)")

    # --- 5/6 measured independence over the FINAL retained set
    # explicit design -> parent backbone map from the frozen as-run selection
    bb_index = {}
    sel_path = pathlib.Path(a.selection)
    if not sel_path.exists():
        rec("FAIL", "selected24_20261025.json missing: cannot map designs to backbones")
        return finish(4)
    for x in json.loads(sel_path.read_text()):
        bb_index[x["name"]] = x["backbone"]
    replacements = set(e2.get("replacements") or [])
    for m in members:
        n = m["name"]
        if n in replacements:
            # replacements were launched after the 24-selection and must not be in it
            if n in bb_index:
                rec("FAIL", f"replacement {n} unexpectedly appears in the frozen selection")
                return finish(4)
            if m.get("backbone") != n.rsplit("_s", 1)[0]:
                rec("FAIL", f"replacement {n}: backbone {m.get('backbone')!r} does not match "
                            f"its design id")
                return finish(4)
            continue
        if bb_index.get(n) != m.get("backbone"):
            rec("FAIL", f"{n}: E2 backbone {m.get('backbone')!r} != frozen selection "
                        f"{bb_index.get(n)!r}")
            return finish(4)
    rec("ok", f"design -> backbone map agrees for all {len(members)} E2 members "
              f"({len(replacements)} post-selection replacements)")

    def bb_of(name):
        # round-2 designs map to their parent backbone; baseline rows map to themselves
        if name in base_seq:
            return name
        if name in bb_index:
            return bb_index[name]
        raise EvidenceError(f"no backbone mapping for {name} — cannot measure independence")

    def union_find(nodes):
        parent = {n: n for n in nodes}

        def find(x):
            while parent[x] != x:
                parent[x] = parent[parent[x]]
                x = parent[x]
            return x

        for i, a in enumerate(nodes):
            for b in nodes[i + 1:]:
                if tm.near(a, b):
                    ra, rb = find(a), find(b)
                    if ra != rb:
                        parent[max(ra, rb)] = min(ra, rb)
        return {n: find(n) for n in nodes}

    def independent_count(names):
        """Count independence in the selected universe (Kimi v8 ruling §4)."""
        bbs = [bb_of(n) for n in names]
        uniq = list(dict.fromkeys(bbs))
        if a.independence == "direct":
            return sum(1 for i, x in enumerate(uniq)
                       if not any(tm.near(x, y) for j, y in enumerate(uniq) if i != j))
        if a.independence == "v7cc":
            roots = union_find(uniq)
        elif a.independence == "global":
            global_nodes = sorted(tm.nodes())
            if not global_nodes:
                raise EvidenceError("TM evidence contains no nodes for the global universe")
            roots = union_find(global_nodes)
        else:  # argparse prevents this
            raise EvidenceError(f"unknown independence unit {a.independence}")
        return len({roots[b] for b in uniq})

    # v7 baseline independent count must reproduce the recorded value
    try:
        base_indep = independent_count(base_names)
    except EvidenceError as ex:
        rec("FAIL", f"baseline independence unmeasurable: {ex}")
        return finish(4)
    pinned_base = INDEPENDENCE[a.independence][0] if a.expect_baseline is None else a.expect_baseline
    if base_indep != pinned_base:
        rec("FAIL", f"baseline independent count {base_indep} ({a.independence}) != pinned {pinned_base}")
        return finish(4)
    rec("ok", f"baseline v7 independent count reproduced = {base_indep} (unit={a.independence})")

    eligible_by_name = {e["name"]: e for e in eligible}
    for e in eligible:
        if e["name"] not in bb_index:
            rec("FAIL", f"{e['name']}: no parent-backbone mapping")
            return finish(4)

    # greedy: try replacements in descending iptm, each checked against the WHOLE final set
    chosen = []
    slot = REPLACE_SLOT
    working = dict(base_seq)
    working_names = list(base_names)
    for name in sorted(eligible_by_name, key=lambda n: (-eligible_by_name[n]["iptm"], n)):
        # Kimi: compare against rows actually RETAINED after replacement, so the slot this
        # candidate occupies is excluded from the near-identity check.
        retained = [m for m in working_names if m != slot]
        try:
            conflict = [m for m in retained
                        if m != name and tm.near(bb_index[name], bb_of(m))]
        except EvidenceError as ex:
            rec("FAIL", f"{name}: {ex}")
            return finish(4)
        if conflict:
            rejected.append({"name": name, "iptm": eligible_by_name[name]["iptm"],
                             "reasons": [f"near-identical to retained row(s): {conflict}"]})
            continue
        trial_names = [n for n in working_names if n != slot] + [name]
        trial_seqs = {n: s for n, s in working.items() if n != slot}
        trial_seqs[name] = inputs[name]["binder"]
        try:
            trial_indep = independent_count(trial_names)
        except EvidenceError as ex:
            rec("FAIL", f"{name}: {ex}")
            return finish(4)
        # diversity: no closer than the row it replaces
        others = {k: v for k, v in trial_seqs.items() if k != name}
        closer_ok = (sum(jaccard(inputs[name]["binder"], others[o]) for o in others) / len(others)
                     <= sum(jaccard(base_seq[slot], others[o]) for o in others) / len(others) + 1e-9)
        if not closer_ok:
            rejected.append({"name": name, "iptm": eligible_by_name[name]["iptm"],
                             "reasons": ["no_diversity_gain_slot"]})
            continue
        working_names = trial_names
        working = trial_seqs
        chosen.append((name, slot, trial_indep))
        break   # exactly one permitted slot

    if not chosen:
        rec("FAIL", "no eligible candidate is independent of every retained row with a valid slot")
        for r in rejected[:8]:
            print(f"       {r['name']}: {', '.join(r['reasons'])[:140]}")
        print("\nDECISION: NO PROMOTION — v7 remains best; nothing written.")
        return finish(3)

    added, slot, final_indep = chosen[0]
    if final_indep < base_indep + 1:
        rec("FAIL", f"final independent count {final_indep} < required {base_indep + 1} "
                    f"(v7 = {base_indep}, unit={a.independence})")
        return finish(3)
    rec("ok", f"{added} (iptm={eligible_by_name[added]['iptm']:.3f}) replaces {slot}; "
              f"final independent count {final_indep} >= {base_indep + 1}")

    # --- 7 assemble + integrity (byte-preserving for the 19 retained rows)
    new_rows = [({"name": added, "sequence": inputs[added]["binder"], "molecule_class": "single_chain"}
                 if r["name"] == slot else dict(r)) for r in base]
    integrity = []
    if len(new_rows) != 20:
        integrity.append(f"row count {len(new_rows)} != 20")
    if not (MIN_REPLACE <= len(chosen) <= MAX_REPLACE):
        integrity.append(f"replacements {len(chosen)} outside [{MIN_REPLACE},{MAX_REPLACE}]")
    names = [r["name"] for r in new_rows]
    seqs = [r["sequence"] for r in new_rows]
    if len(set(names)) != 20:
        integrity.append("duplicate names")
    if len(set(seqs)) != 20:
        integrity.append("duplicate sequences")
    if list(new_rows[0].keys()) != HEADER:
        integrity.append("header changed")
    for r in new_rows:
        if not set(r["sequence"]) <= CANON:
            integrity.append(f"non-canonical AA in {r['name']}")
        for reason in soluble.failures(r["sequence"]):
            integrity.append(f"soluble_filter:{r['name']}:{reason}")
        if not (52 <= len(r["sequence"]) <= 100):
            integrity.append(f"length {len(r['sequence'])} out of range for {r['name']}")
    # byte-level preservation: every retained row must be the EXACT raw v7 line, in order
    base_lines = baseline_bytes.splitlines(keepends=True)
    if not base_lines or base_lines[0] != b"name,sequence,molecule_class\r\n":
        integrity.append("baseline header is not the expected exact bytes")
    raw_by_name = {}
    for line in base_lines[1:]:
        nm = line.split(b",", 1)[0].decode("ascii", "replace")
        raw_by_name[nm] = line
    if set(raw_by_name) != set(base_names):
        integrity.append("could not map every baseline row to its raw line")
    new_line = f"{added},{inputs[added]['binder']},single_chain\r\n".encode()
    out_header = base_lines[0] if base_lines else b""
    out_lines = [out_header]
    for n in names:
        out_lines.append(new_line if n == added else raw_by_name.get(n, b""))
    if [ln for ln in out_lines[1:] if ln != new_line] != \
            [raw_by_name[n] for n in base_names if n != slot]:
        integrity.append("retained rows are not byte-identical to v7 / order changed")
    if len(out_lines) != 21:
        integrity.append(f"raw output has {len(out_lines) - 1} data rows, expected 20")
    if integrity:
        for m in integrity:
            rec("FAIL", m)
        print("\nDECISION: NO PROMOTION — integrity failures; nothing written.")
        return finish(3)
    rec("ok", "CSV integrity: 20 rows, unique, canonical, 52-100, 19 non-variant rows "
              "byte-identical and in v7 order")

    if a.dry_run:
        rec("ok", "dry-run: all conditions met; would write v8")
        print("\nDECISION (dry-run): WOULD PROMOTE v8")
        return finish(0)

    v7_before = open(a.baseline, "rb").read()
    out = pathlib.Path(a.output)
    fd, tmp = tempfile.mkstemp(dir=str(out.parent), suffix=".tmp")
    with os.fdopen(fd, "wb") as f:
        f.write(b"".join(out_lines))
    os.replace(tmp, out)
    if open(a.baseline, "rb").read() != v7_before:
        rec("FAIL", "v7 changed during write — investigate immediately")
        return finish(4)
    rec("ok", f"atomically wrote {out}; v7 unchanged")
    print(f"\nDECISION: PROMOTE v8 — {added} replaces {slot}")
    return finish(0)


if __name__ == "__main__":
    sys.exit(main())
