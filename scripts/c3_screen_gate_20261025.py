#!/usr/bin/env python3
"""C3 promotion gate — FAIL-CLOSED (repaired per Kimi audit 2026-10-25).

Sole writer of results/c3_submission_v7_20261025.csv. It writes NOTHING unless every
pre-registered condition is demonstrated by an evidence record bound to the candidate's
exact sequence. Missing / malformed / empty / stale evidence is a hard failure with a
non-zero exit code and no output file (fail-closed, per the audit).

Evidence files (all required):
  results/c3_screen_af2m_scores_combined_20261025.json   iPTM/pTM/pLDDT per design
  results/c3_refold_checks_20261025.json                 ESMFold exact-sequence refold
  results/c3_structural_checks_20261025.json             complex structural checks
  results/c3_groove_reference_20261025.json              fixed groove definition
  results/c3_screen_shortlist_20261024.csv               candidate sequences

Promotion requires, simultaneously:
  1. complete 44/44 screen over the exact input names; all 8 BindCraft anchors scored
  2. floor = max(0.76, min anchor iPTM), never lowered
  3. each added candidate: shortlist member, iPTM >= floor
  3b. each added candidate: passes the pre-registered soluble/non-TM filters
      (canonical AAs, max-19 GRAVY <2.0, overall GRAVY <0.4, KRDEH >=0.18)
  4. each added candidate: refold mean pLDDT >=80, >=90% residues >=70, CA RMSD <=3.0 A
  5. each added candidate: binder pLDDT >=80, >=5 groove residues, >=20 contacts <=5 A,
     no heavy-atom pair <2 A, no chain-integrity problem
  6. evidence is bound to the exact sequence (sha256 of the sequence must match the record)
  7. replacements only of c3_v_* slots; all 13 non-variant v6 rows unchanged in content
  8. 1..7 replacements; common rows keep v6 order and content
  9. 3-mer Jaccard audit: set minimum pairwise similarity must not decrease, and each new
     candidate must not be closer to the retained set than the variant it replaces
 10. independent backbone count increases by >=1 (TM <0.65 OR coverage <0.80 against EVERY
     retained backbone, i.e. NOT (TM>=0.65 AND coverage>=0.80))
 11. valid 20-row output; v6 sha256 unchanged; atomic write

Exit codes: 0 promotion written, 3 no promotion (evidence complete, criteria not met),
            4 missing/invalid evidence (fail-closed, nothing written).
"""
import argparse
import csv
import hashlib
import json
import os
import pathlib
import sys
import tempfile

import c3_soluble_filters_20261025 as soluble

ROOT = pathlib.Path("/Users/ricardo/dev/adaptyv-c4")
AUDIT_FLOOR = 0.76
VARIANT_PREFIX = "c3_v_"
HEADER = ["name", "sequence", "molecule_class"]
CANON = set("ACDEFGHIKLMNPQRSTVWY")
V6_SHA = "8e9b2d741586e8b360fbed401b4de77317d579e183409cf4928de42661096891"
TM_IDENTICAL, COV_IDENTICAL = 0.65, 0.80
MIN_REPLACE, MAX_REPLACE = 1, 7


def sha(s):
    return hashlib.sha256(s.encode()).hexdigest()


def kmers(s, k=3):
    return {s[i:i + k] for i in range(len(s) - k + 1)}


def jaccard(a, b):
    ka, kb = kmers(a), kmers(b)
    return len(ka & kb) / len(ka | kb) if (ka | kb) else 0.0


class EvidenceError(Exception):
    pass


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


def tm_backbone_tools():
    try:
        import tmtools  # noqa: F401
        return True
    except Exception:
        return False


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--baseline", default=str(ROOT / "results/c3_submission_v6_20261023.csv"))
    ap.add_argument("--shortlist", default=str(ROOT / "results/c3_screen_shortlist_20261024.csv"))
    ap.add_argument("--scores", default=str(ROOT / "results/c3_screen_af2m_scores_combined_20261025.json"))
    ap.add_argument("--input", default=str(ROOT / "results/c3_screen_input_20261024.csv"))
    ap.add_argument("--refold", default=str(ROOT / "results/c3_refold_checks_20261025.json"))
    ap.add_argument("--structural", default=str(ROOT / "results/c3_structural_checks_20261025.json"))
    ap.add_argument("--groove", default=str(ROOT / "results/c3_groove_reference_20261025.json"))
    ap.add_argument("--clusters", default=str(ROOT / "results/c3_backbone_clusters_20261025.json"))
    ap.add_argument("--output", default=str(ROOT / "results/c3_submission_v7_20261025.csv"))
    ap.add_argument("--report", default=str(ROOT / "results/c3_gate_20261025_report.json"))
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    checks = []

    def rec(status, detail):
        checks.append({"status": status, "detail": detail})
        print(f"  {status:<4s} {detail}")

    def finish(code):
        out = {"checks": checks, "wrote_v7": None, "exit_code": code}
        pathlib.Path(a.report).write_text(json.dumps(out, indent=2))
        print(f"(report: {a.report})")
        return code

    print("=== C3 gate 2026-10-25 — fail-closed ===")
    try:
        scores_rows = json.loads(pathlib.Path(a.scores).read_text())
        refold = load_json(a.refold, "refold")
        struct = load_json(a.structural, "structural")
        groove = load_json(a.groove, "groove")
        clusters = load_json(a.clusters, "clusters")
        if not isinstance(clusters.get("pairs"), dict):
            raise EvidenceError("backbone clusters lack a 'pairs' map")
        if clusters.get("rows_measured") != clusters.get("rows_expected"):
            raise EvidenceError(
                "backbone clusters incomplete: "
                f"{clusters.get('rows_measured')}/{clusters.get('rows_expected')} rows measured")
    except EvidenceError as ex:
        rec("FAIL", str(ex))
        print("\nDECISION: NO PROMOTION — evidence missing/invalid (fail-closed); nothing written.")
        return finish(4)
    except Exception as ex:
        rec("FAIL", f"scores: unreadable ({ex})")
        return finish(4)

    if not all(k in groove for k in ("groove_residues_1based", "cutoff_a")):
        rec("FAIL", "groove evidence lacks required fields")
        return finish(4)

    base = list(csv.DictReader(open(a.baseline)))
    inputs = list(csv.DictReader(open(a.input)))
    shortlist = {r["name"]: r for r in csv.DictReader(open(a.shortlist))}
    sl_seqs = [r["sequence"] for r in shortlist.values()]
    if len(sl_seqs) != len(set(sl_seqs)):
        rec("FAIL", "shortlist contains duplicate sequences")
        print("\nDECISION: NO PROMOTION — duplicate sequences in shortlist (fail-closed); nothing written.")
        return finish(4)
    score_names = [r.get("name") for r in scores_rows]
    if len(score_names) != len(set(score_names)):
        dups = sorted({n for n in score_names if score_names.count(n) > 1})
        rec("FAIL", f"score table has duplicate design names: {dups[:5]}")
        print("\nDECISION: NO PROMOTION — duplicate names in evidence (fail-closed); nothing written.")
        return finish(4)
    scores = {r["name"]: r for r in scores_rows}

    # --- 11a: baseline integrity
    cur_sha = hashlib.sha256(open(a.baseline, "rb").read()).hexdigest()
    if cur_sha != V6_SHA:
        rec("FAIL", f"baseline sha256 {cur_sha[:16]}… != recorded {V6_SHA[:16]}…")
        return finish(4)
    rec("ok", "baseline v6 sha256 matches the recorded value")

    # --- 1: completeness
    input_names = [r["name"] for r in inputs]
    scored = {n for n, r in scores.items() if isinstance(r.get("iptm"), (int, float))}
    if not (len(input_names) == len(set(input_names)) == 44 and set(input_names) <= scored):
        rec("FAIL", f"screen incomplete: {len(set(input_names) & scored)}/44")
        return finish(3)
    rec("ok", "screen complete 44/44 with unique names")

    base_names = [r["name"] for r in base]
    bindcraft = [n for n in base_names if n.startswith("c3_bc_")]
    variants = [n for n in base_names if n.startswith(VARIANT_PREFIX)]
    fixed = [n for n in base_names if not n.startswith(VARIANT_PREFIX)]
    missing_bc = [n for n in bindcraft if n not in scored]
    if len(bindcraft) != 8 or missing_bc:
        rec("FAIL", f"BindCraft anchors incomplete: {missing_bc}")
        return finish(3)
    rec("ok", "all 8 BindCraft anchors scored")

    # --- 2: floor
    floor = max(AUDIT_FLOOR, min(scores[n]["iptm"] for n in bindcraft))
    rec("ok", f"floor = max({AUDIT_FLOOR}, {min(scores[n]['iptm'] for n in bindcraft):.3f}) = {floor:.3f}")

    # --- 3-6 (pre-check): evidence must EXIST and be bound to the exact sequence for every
    # candidate under consideration. A missing or mis-bound record means the evidence file is
    # stale or truncated, so the whole run fails closed instead of silently narrowing the pool.
    evidence_gaps = []
    for name, row in shortlist.items():
        want = sha(row["sequence"])
        rf, st = refold.get(name), struct.get(name)
        if not isinstance(rf, dict):
            evidence_gaps.append(f"{name}: refold record absent")
        elif rf.get("sequence_sha256") != want:
            evidence_gaps.append(f"{name}: refold sequence mismatch/not bound")
        if not isinstance(st, dict):
            evidence_gaps.append(f"{name}: structural record absent")
        elif st.get("sequence_sha256") != want:
            evidence_gaps.append(f"{name}: structural sequence mismatch/not bound")
    if evidence_gaps:
        rec("FAIL", f"evidence incomplete or mis-bound for {len(evidence_gaps)} candidate record(s): "
                    f"{evidence_gaps[:4]}")
        print("\nDECISION: NO PROMOTION — evidence missing/mis-bound (fail-closed); nothing written.")
        return finish(4)
    rec("ok", f"refold + structural evidence present and sequence-bound for all {len(shortlist)} candidates")

    eligible, rejected = [], []
    for name in sorted(shortlist, key=lambda n: -scores.get(n, {}).get("iptm", 0)):
        seq = shortlist[name]["sequence"]
        seq_sha = sha(seq)
        why = []
        for reason in soluble.failures(seq):
            why.append(f"soluble_filter:{reason}")
        if scores.get(name, {}).get("iptm", 0) < floor:
            why.append("below_floor")
        r = refold.get(name)
        if not isinstance(r, dict):
            why.append("refold_record_absent")
        else:
            if r.get("sequence_sha256") not in (None, seq_sha):
                why.append("refold_sequence_mismatch")
            if r.get("sequence_sha256") is None:
                why.append("refold_not_sequence_bound")
            if not r.get("pass"):
                why.append("refold_fail")
            if (r.get("refold_mean_plddt") or 0) < 80:
                why.append("refold_plddt_lt80")
            if (r.get("refold_frac_residues_plddt_ge70") or 0) < 0.90:
                why.append("refold_frac70_lt0.90")
            rmsd = r.get("ca_rmsd_vs_af2m_binder")
            if rmsd is None or rmsd > 3.0:
                why.append("refold_rmsd_gt3")
        s = struct.get(name)
        if not isinstance(s, dict):
            why.append("structural_record_absent")
        else:
            if s.get("sequence_sha256") not in (None, seq_sha):
                why.append("structural_sequence_mismatch")
            if s.get("sequence_sha256") is None:
                why.append("structural_not_sequence_bound")
            if (s.get("binder_mean_plddt") or 0) < 80:
                why.append("binder_plddt_lt80")
            if (s.get("groove_residues_contacted") or 0) < 5:
                why.append("groove_contacts_lt5")
            if (s.get("target_binder_contacts_le5A") or 0) < 20:
                why.append("total_contacts_lt20")
            if (s.get("heavy_atom_pairs_lt2A") or 0) != 0:
                why.append("clash_lt2A")
            if s.get("chain_integrity_problems"):
                why.append("chain_integrity")
            if not s.get("pass"):
                why.append("structural_fail")
        if why:
            rejected.append({"name": name, "reasons": sorted(set(why)),
                             "iptm": scores.get(name, {}).get("iptm")})
        else:
            eligible.append(name)

    if rejected:
        rec("info", f"{len(rejected)} shortlist candidates rejected; "
                    f"{len(eligible)} fully eligible: {eligible}")
    else:
        rec("ok", f"all {len(eligible)} shortlist candidates carry bound evidence")

    # --- 9-10: diversity and independent backbones
    base_seq = {r["name"]: r["sequence"] for r in base}
    seq_by_name = {n: r["sequence"] for n, r in shortlist.items()}

    def min_pairwise(d):
        keys = list(d)
        vals = [jaccard(d[keys[i]], d[keys[j]])
                for i in range(len(keys)) for j in range(i + 1, len(keys))]
        return min(vals) if vals else 0.0

    baseline_min = min_pairwise(base_seq)

    def n_independent(d, cl):
        """Count rows whose backbone is not near-identical to any other row."""
        pairmap = cl["pairs"] if isinstance(cl, dict) and "pairs" in cl else cl
        names = list(d)
        indep = 0
        for i, n in enumerate(names):
            near = False
            for j, m in enumerate(names):
                if i == j:
                    continue
                c = (pairmap.get(n, {}).get(m) or pairmap.get(m, {}).get(n) or {})
                if (c.get("tm") or 0) >= TM_IDENTICAL and (c.get("coverage") or 0) >= COV_IDENTICAL:
                    near = True
                    break
            if not near:
                indep += 1
        return indep

    base_indep = n_independent(base_seq, clusters)
    chosen = []
    used_variants = set()
    working = dict(base_seq)
    for cand in eligible:
        cseq = seq_by_name[cand]
        pick = None
        for v in variants:
            if v in used_variants:
                continue
            trial = dict(working)
            trial[cand] = cseq
            trial.pop(v, None)
            others = {k: s for k, s in trial.items() if k != cand}
            closer_ok = (sum(jaccard(cseq, others[o]) for o in others) / len(others)
                         <= sum(jaccard(base_seq[v], others[o]) for o in others) / len(others) + 1e-9)
            min_ok = min_pairwise(trial) >= baseline_min - 1e-9
            if closer_ok and min_ok:
                pick = v
                break
        if pick is None:
            rejected.append({"name": cand, "reasons": ["no_diversity_gain_slot"], "iptm": scores[cand]["iptm"]})
            continue
        working.pop(pick, None)
        working[cand] = cseq
        trial_indep = n_independent(working, clusters)
        if trial_indep < base_indep + 1 and not chosen:
            rejected.append({"name": cand, "reasons": ["no_independent_backbone_gain"], "iptm": scores[cand]["iptm"]})
            working = dict(working)
            working.pop(cand, None)
            working[pick] = base_seq[pick]
            continue
        used_variants.add(pick)
        chosen.append((cand, pick))

    if not chosen:
        rec("FAIL", "no candidate satisfies every evidence gate with a diversity/backbone gain")
        for r in rejected[:8]:
            print(f"       {r['name']}: {','.join(r['reasons'])}")
        print("\nDECISION: NO PROMOTION — v6 remains best; nothing written.")
        return finish(3)
    rec("ok", f"{len(chosen)} replacement(s) chosen: {[c for c, _ in chosen]}")

    # --- 7-8, 11: build rows preserving v6 order for unchanged rows
    queues = {}
    for c, v in chosen:
        queues.setdefault(v, []).append(c)
    new_rows, placed = [], []
    for r in base:
        q = queues.get(r["name"])
        if q:
            c = q.pop(0)
            new_rows.append({"name": c, "sequence": seq_by_name[c], "molecule_class": "single_chain"})
            placed.append((c, r["name"]))
        else:
            new_rows.append(dict(r))

    integrity = []
    if len(new_rows) != 20:
        integrity.append(f"row count {len(new_rows)} != 20")
    if not (MIN_REPLACE <= len(placed) <= MAX_REPLACE):
        integrity.append(f"replacements {len(placed)} outside [{MIN_REPLACE},{MAX_REPLACE}]")
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
        # defense in depth: every row written must also pass the soluble/non-TM filters,
        # including rows inherited from the baseline (round-1 shortlist already passed).
        for reason in soluble.failures(r["sequence"]):
            integrity.append(f"soluble_filter:{r['name']}:{reason}")
        if not (52 <= len(r["sequence"]) <= 100):
            integrity.append(f"length {len(r['sequence'])} out of range for {r['name']}")
    newmap = {r["name"]: r for r in new_rows}
    for n in fixed:
        if n not in newmap:
            integrity.append(f"non-variant row dropped: {n}")
        elif newmap[n] != {k: v for k, v in next(r for r in base if r["name"] == n).items()}:
            integrity.append(f"non-variant row altered: {n}")
    if [r["name"] for r in new_rows if r["name"] in fixed] != [n for n in base_names if n in fixed]:
        integrity.append("order of non-variant rows changed")
    if integrity:
        for m in integrity:
            rec("FAIL", m)
        print("\nDECISION: NO PROMOTION — integrity failures; nothing written.")
        return finish(3)
    rec("ok", "CSV integrity: 20 rows, unique, canonical, 52-100, 13 non-variant rows "
              "byte-identical and in v6 order")

    if a.dry_run:
        rec("ok", "dry-run: all conditions met; would write v7")
        print("\nDECISION (dry-run): WOULD PROMOTE")
        return finish(0)

    out = pathlib.Path(a.output)
    fd, tmp = tempfile.mkstemp(dir=str(out.parent), suffix=".tmp")
    with os.fdopen(fd, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=HEADER)
        w.writeheader()
        w.writerows(new_rows)
    os.replace(tmp, out)
    rec("ok", f"atomically wrote {out}")
    for c, v in placed:
        print(f"       {c} (iptm={scores[c]['iptm']:.3f}) replaces {v}")
    print("\nDECISION: PROMOTE — v7 written; v6 preserved as fallback.")
    checks[-1]["detail"] += f" | wrote_v7=true"
    fin = finish(0)
    rep = json.loads(pathlib.Path(a.report).read_text())
    rep["wrote_v7"] = str(out)
    rep["rejected"] = rejected
    rep["placed"] = [{"added": c, "replaced": v} for c, v in placed]
    pathlib.Path(a.report).write_text(json.dumps(rep, indent=2))
    return fin


if __name__ == "__main__":
    sys.exit(main())
