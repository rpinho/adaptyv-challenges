#!/usr/bin/env python3
"""Stratify the 32 frozen FastRelax candidates by clash severity + atom type (read-only, $0, CPU).

Why: both consultants required the cohort to be stratified "by severity and atom type" before any
pilot, and to "exclude backbone–backbone collisions from repair eligibility". The 06:48 clash audit
already carries every atom pair, so the stratification needs no licence and no GPU.

Inputs (frozen, read-only):
  results/c3_clash_audit_20261025/audit.json   per-run pairs with binder/target atom identities
  results/c3_r3_20261025/fastrelax_candidates_20261025.json   the frozen 32-design manifest
Outputs:
  results/c3_fastrelax_cohort_20261025/{cohort.csv,summary.md,summary.json}
No gate, score, ranking or CSV change. No relaxation is run here.
"""
import json, csv, pathlib, collections

ROOT = pathlib.Path(__file__).resolve().parents[1]
AUDIT = ROOT / "results/c3_clash_audit_20261025/audit.json"
MANIFEST = ROOT / "results/c3_r3_20261025/fastrelax_candidates_20261025.json"
OUT = ROOT / "results/c3_fastrelax_cohort_20261025"
BACKBONE_ATOMS = {"N", "CA", "C", "O"}

def load_manifest_names(path):
    d = json.load(open(path))
    for key in ("candidates", "designs", "rows", "names"):
        if isinstance(d, dict) and key in d:
            v = d[key]
            if isinstance(v, list):
                return [x if isinstance(x, str) else (x.get("design_id") or x.get("name") or x.get("design")) for x in v]
    if isinstance(d, list):
        return [x if isinstance(x, str) else (x.get("name") or x.get("design")) for x in d]
    raise SystemExit(f"unrecognised manifest shape: {list(d)[:10] if isinstance(d, dict) else type(d)}")

def atom_name(s):
    return s.split(":", 1)[1] if ":" in s else s

def severity(min_d):
    if min_d is None: return "none"
    if min_d < 1.2: return "S4_<1.2"
    if min_d < 1.5: return "S3_1.2-1.5"
    if min_d < 1.9: return "S2_1.5-1.9"
    if min_d < 2.0: return "S1_1.9-2.0"
    return "PASS_>=2.0"

def main():
    audit = json.load(open(AUDIT))
    names = load_manifest_names(MANIFEST)
    groups = audit["groups"]
    rows = []
    for name in names:
        g = groups.get(name)
        if g is None:
            rows.append(dict(design=name, runs=0, severity="NO_AUDIT", worst_min=None, clash_pairs=None,
                             atom_classes="", backbone_backbone=False, repair_eligible=None, note="absent from audit"))
            continue
        worst, pairs_total, classes, bb = None, 0, set(), False
        for r in g.get("runs", []):
            md = r.get("min_interchain_dist")
            if md is not None and (worst is None or md < worst): worst = md
            pairs_total = max(pairs_total, r.get("n_clash_pairs") or 0)
            for p in r.get("pairs") or []:
                b, t = atom_name(p["binder"]), atom_name(p["target"])
                if b in BACKBONE_ATOMS and t in BACKBONE_ATOMS:
                    classes.add("bb-bb"); bb = True
                elif b in BACKBONE_ATOMS or t in BACKBONE_ATOMS:
                    classes.add("bb-side")
                else:
                    classes.add("side-side")
        sev = severity(worst)
        rows.append(dict(design=name, runs=len(g.get("runs", [])), severity=sev, worst_min=worst,
                         clash_pairs=pairs_total, atom_classes=";".join(sorted(classes)) or "none",
                         backbone_backbone=bb,
                         repair_eligible=(sev != "none" and not bb),
                         note=g.get("cohort", "")))
    OUT.mkdir(parents=True, exist_ok=True)
    fields = ["design","runs","severity","worst_min","clash_pairs","atom_classes","backbone_backbone","repair_eligible","note"]
    with open(OUT/"cohort.csv","w",newline="") as f:
        w=csv.DictWriter(f,fieldnames=fields); w.writeheader(); w.writerows(rows)
    by_sev=collections.Counter(r["severity"] for r in rows)
    bb_excluded=[r["design"] for r in rows if r["backbone_backbone"]]
    ineligible=[r["design"] for r in rows if r["repair_eligible"] is False]
    # Pair-level accounting (Astra/Kimi 07:45 correction). The "atom_class_totals" key below is a
    # DESIGN count, not a pair count: design categories overlap and do not sum to a pair total.
    # The earlier "55 pairs across these 32 designs" conflated this cohort with the full audit.
    def pair_accounting(group_keys):
        tot = 0; cls = collections.Counter(); runs = 0
        for name in group_keys:
            g = groups.get(name)
            if not g: continue
            for r in g.get("runs", []):
                runs += 1
                for p in r.get("pairs") or []:
                    tot += 1
                    b, tg = atom_name(p["binder"]), atom_name(p["target"])
                    bc, tc = b in BACKBONE_ATOMS, tg in BACKBONE_ATOMS
                    cls["bb-bb" if (bc and tc) else ("bb-side" if (bc or tc) else "side-side")] += 1
        return tot, cls, runs

    c_tot, c_cls, c_runs = pair_accounting([r["design"] for r in rows if r["runs"]])
    a_tot, a_cls, a_runs = pair_accounting(list(groups))
    summary=dict(n_manifest=len(names), n_audited=sum(1 for r in rows if r["runs"]),
                 by_severity=dict(sorted(by_sev.items())),
                 backbone_backbone_excluded=sorted(set(bb_excluded)),
                 repair_ineligible_count=len(set(ineligible)),
                 repair_eligible_count=sum(1 for r in rows if r["repair_eligible"] is True),
                 repair_label="not excluded by the stated backbone-backbone rule; repairability untested",
                 designs_with_bb_side_pair=sum(1 for r in rows if "bb-side" in (r["atom_classes"] or "")),
                 design_atom_class_counts=dict(collections.Counter(
                     c for r in rows for c in (r["atom_classes"] or "").split(";") if c and c != "none")),
                 pair_accounting=dict(
                     cohort_designs=len([r for r in rows if r["runs"]]), cohort_runs=c_runs,
                     cohort_pairs_total=c_tot, cohort_side_side=c_cls["side-side"],
                     cohort_bb_side=c_cls["bb-side"], cohort_bb_bb=c_cls["bb-bb"],
                     all_audited_groups=len(groups), all_audited_runs=a_runs,
                     all_pairs_total=a_tot, all_side_side=a_cls["side-side"],
                     all_bb_side=a_cls["bb-side"], all_bb_bb=a_cls["bb-bb"]),
                 no_audit=[r["design"] for r in rows if r["runs"]==0])
    json.dump(summary,open(OUT/"summary.json","w"),indent=1)
    md=["# FastRelax cohort — stratified by severity and atom type ($0, read-only)","",
        "Built from the frozen 06:48 clash audit + the frozen 32-candidate manifest. No relaxation was run;",
        "this only prepares the cohort both consultants required before a pilot. Licence remains RICARDO-APPROVAL.","",
        f"- manifest designs: **{summary['n_manifest']}**; audited: **{summary['n_audited']}**; not audited: {len(summary['no_audit'])}",
        f"- not excluded by the stated backbone–backbone rule: **{summary['repair_eligible_count']}** "
        f"(repairability untested; 5 carry a backbone–sidechain contact)",
        f"- excluded for backbone–backbone collision: **{len(summary['backbone_backbone_excluded'])}**","",
        "| severity band | designs |","|---|---:|"]
    for k,v in summary["by_severity"].items(): md.append(f"| {k} | {v} |")
    md += ["", "Bands are descriptive strata for a pilot design, not a gate or a ranking.","",
           "Status: PROPOSED cohort only. Gate, scores, ranking and all CSVs unchanged.","",
        "## Atom-type split — reconciled against the raw audit (Astra + Kimi, 07:45)","",
        "The earlier draft cited **55 clash pairs across these 32 designs**. That figure is wrong for this",
        "cohort: **55 is the pair count across all 38 audited groups**. Pair-level recount:","",
        "| pair class | 32-design cohort | all 38 audited groups |","|---|---:|---:|",
        f"| sidechain–sidechain | **{c_cls['side-side']}** | {a_cls['side-side']} |",
        f"| backbone–sidechain | **{c_cls['bb-side']}** | {a_cls['bb-side']} |",
        f"| backbone–backbone | **{c_cls['bb-bb']}** | {a_cls['bb-bb']} |",
        f"| **total** | **{c_tot}** | **{a_tot}** |","",
        "Accounting is exact and every pair is classified once. The `30 / 5 / 0` split quoted earlier was a",
        "**design** count (designs containing each class), not a pair split; design categories overlap, so",
        "they do not sum to a pair total. Exclusions remain empty by exhaustive accounting, not assumption.",""]
    (OUT/"summary.md").write_text("\n".join(md))
    print(json.dumps(summary,indent=1))

if __name__=="__main__":
    main()
