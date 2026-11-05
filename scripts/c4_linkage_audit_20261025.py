#!/usr/bin/env python
"""C4 bound-vs-unbound protonation linkage audit (CPU only).

Question (Kimi 05:49 ruling): does the C4 apical preview's ranking criterion establish
acid-conditional BINDING (bind at pH 5.5, not 7.4)?  Elevated bound-state pKa alone cannot.
This recomputes the Wyman linkage from each design's BOUND complex against its own
UNBOUND binder and unbound target, at two pH pairs, and reports sign controls.

Sign convention used by scripts/ph_linkage.py and METHOD.md:
    L = log10 Ka(pH_low) - log10 Ka(pH_high)
For C4's conditional-binding objective we need L > 0 (tighter binding at the lower pH).
L < 0 is the C3/endosomal-release direction.

Controls (hard-coded, not tuned):
  * null      : identical bound and free pKa sets -> L must be exactly 0
  * acid-ON   : pKa raised by 1.0 on binding at pH 6.0 -> L must be > 0
  * acid-OFF  : pKa depressed by 1.0 on binding at pH 6.0 -> L must be < 0
If any control fails, the audit is INVALID and the script exits non-zero.

Read-only on all inputs. Writes only results/c4_linkage_audit_20261025/.
"""
import csv, json, math, os, shutil, subprocess, sys, tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "results"
OUT = RESULTS / "c4_linkage_audit_20261025"
PREVIEW = RESULTS / "c4_apical_preview_20261024.csv"
COMPLEX_DIR = RESULTS / "c4_rebuild_20261024" / "remote_pdbs"
VENV_PROPKA = ROOT / ".venv-rosetta" / "bin" / "propka3"

TITRATABLE = {"HIS", "ASP", "GLU", "LYS", "TYR", "CYS", "ARG", "N+", "C-"}


def term(pb, pf, ph):
    return math.log10(1 + 10 ** (pb - ph)) - math.log10(1 + 10 ** (pf - ph))


def linkage(bound, free, ph_low, ph_high, min_shift=0.1):
    total, rows = 0.0, []
    for key, pb in bound.items():
        if key not in free:
            continue
        pf = free[key]
        if abs(pb - pf) < min_shift:
            continue
        c = term(pb, pf, ph_low) - term(pb, pf, ph_high)
        total += c
        rows.append(dict(chain=key[0], resnum=key[1], resname=key[2],
                         pka_free=round(pf, 2), pka_bound=round(pb, 2),
                         dpka=round(pb - pf, 2), contribution=round(c, 4)))
    rows.sort(key=lambda r: r["contribution"])
    return total, rows


def run_propka(pdb, workdir):
    dst = os.path.join(workdir, os.path.basename(pdb))
    if os.path.abspath(dst) != os.path.abspath(pdb):
        shutil.copy(pdb, dst)
    exe = str(VENV_PROPKA) if VENV_PROPKA.exists() else "propka3"
    try:
        subprocess.run([exe, os.path.basename(dst)], cwd=workdir, check=True,
                       capture_output=True, timeout=1800)
    except subprocess.CalledProcessError as e:
        sys.stderr.write("propka failed %s: %s\n" % (pdb, e.stderr.decode()[-300:]))
        return None
    pka_file = os.path.splitext(dst)[0] + ".pka"
    if not os.path.exists(pka_file):
        return None
    out, in_summary = {}, False
    for line in open(pka_file):
        if line.startswith("SUMMARY OF THIS PREDICTION"):
            in_summary = True; continue
        if in_summary:
            if line.startswith("---") or not line.strip():
                if out: break
                continue
            # PROPKA3 summary: RESN NUM CHAIN pKa [model-pKa]
            p = line.split()
            if len(p) >= 4 and p[0] in TITRATABLE:
                try:
                    out[(p[2], int(p[1]), p[0])] = float(p[3])
                except ValueError:
                    pass
    return out


def split_chains(pdb, keep, out_path):
    with open(pdb) as fh, open(out_path, "w") as out:
        for line in fh:
            if line.startswith(("ATOM", "HETATM")) and line[21] in keep:
                out.write(line)
            elif line.startswith("TER"):
                out.write(line)
        out.write("END\n")


def score(pdb, binder_chain, target_chain, ph_low, ph_high):
    with tempfile.TemporaryDirectory() as td:
        cx = run_propka(pdb, td)
        if not cx: return None
        bp, tp = os.path.join(td, "binder.pdb"), os.path.join(td, "target.pdb")
        split_chains(pdb, set(binder_chain), bp)
        split_chains(pdb, set(target_chain), tp)
        fb, ft = run_propka(bp, td), run_propka(tp, td)
        if not fb or not ft: return None
        free = dict(fb); free.update(ft)
        L, rows = linkage(cx, free, ph_low, ph_high)
        return dict(L=L, rows=rows, n_groups=len(rows),
                    n_binder_his=sum(1 for r in rows if r["resname"] == "HIS" and r["chain"] in binder_chain),
                    n_target_his=sum(1 for r in rows if r["resname"] == "HIS" and r["chain"] in target_chain))


def controls():
    """Validate the arithmetic and sign convention before scoring anything real."""
    base = {("A", 10, "HIS"): 6.50, ("A", 20, "GLU"): 4.50}
    null_L, _ = linkage(base, base, 6.0, 7.4)
    on = {("A", 10, "HIS"): 7.50, ("A", 20, "GLU"): 4.50}
    off = {("A", 10, "HIS"): 5.50, ("A", 20, "GLU"): 4.50}
    on_L, _ = linkage(on, base, 6.0, 7.4)
    off_L, _ = linkage(off, base, 6.0, 7.4)
    res = dict(null_L=round(null_L, 6), acid_on_L=round(on_L, 4), acid_off_L=round(off_L, 4),
               null_ok=abs(null_L) < 1e-12, acid_on_ok=on_L > 0, acid_off_ok=off_L < 0)
    res["all_ok"] = res["null_ok"] and res["acid_on_ok"] and res["acid_off_ok"]
    return res


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    ctl = controls()
    print("sign controls:", json.dumps(ctl))
    if not ctl["all_ok"]:
        json.dump(ctl, open(OUT / "sign_controls.json", "w"), indent=2)
        raise SystemExit("SIGN CONTROLS FAILED - audit invalid")

    rows = list(csv.DictReader(open(PREVIEW)))
    records, missing = [], []
    for r in rows:
        name = r["name"]
        pdb = COMPLEX_DIR / (name + "_complex.pdb")
        if not pdb.exists():
            missing.append(name); continue
        rec = dict(name=name, sequence_sha256=None, complex_pdb=str(pdb.relative_to(ROOT)),
                   n_his_sequence=r["sequence"].count("H"), molecule_class=r["molecule_class"])
        import hashlib
        rec["sequence_sha256"] = hashlib.sha256(r["sequence"].encode()).hexdigest()
        for label, lo, hi in (("L_5.5_7.4", 5.5, 7.4), ("L_6.0_7.4", 6.0, 7.4)):
            s = score(str(pdb), "B", "A", lo, hi)
            if s is None:
                rec[label] = None; rec[label + "_rows"] = []
            else:
                rec[label] = round(s["L"], 3)
                rec[label + "_n_groups"] = s["n_groups"]
                rec[label + "_n_binder_his"] = s["n_binder_his"]
                rec[label + "_n_target_his"] = s["n_target_his"]
                rec[label + "_rows"] = s["rows"]
        records.append(rec)
        print("%-30s H=%2d L(5.5/7.4)=%s L(6.0/7.4)=%s" % (
            name, rec["n_his_sequence"], rec.get("L_5.5_7.4"), rec.get("L_6.0_7.4")))

    scored = [x for x in records if x.get("L_6.0_7.4") is not None]
    pos = [x for x in scored if x["L_6.0_7.4"] > 0]
    neg = [x for x in scored if x["L_6.0_7.4"] < 0]
    summary = dict(
        audit="c4_linkage_audit_20261025", method="Wyman linkage, bound complex vs isolated chains",
        ph_pairs={"L_5.5_7.4": "log10 Ka(5.5)-log10 Ka(7.4)", "L_6.0_7.4": "log10 Ka(6.0)-log10 Ka(7.4)"},
        sign_convention="positive L = tighter binding at the lower pH = C4 acid-conditional direction",
        controls=ctl, n_preview=len(rows), n_scored=len(scored), n_missing_pdb=len(missing),
        missing_pdb=missing, n_positive_L6=len(pos), n_negative_L6=len(neg),
        n_positive_L55=sum(1 for x in scored if (x.get("L_5.5_7.4") or 0) > 0),
        n_negative_L55=sum(1 for x in scored if (x.get("L_5.5_7.4") or 0) < 0),
        positive_designs=[x["name"] for x in pos], negative_designs=[x["name"] for x in neg],
        interpretation=("PROPKA bound-vs-free linkage on model structures; detects sign contradictions, "
                        "does not establish experimental pH-conditional binding or release. Elevated bound pKa "
                        "alone is not sufficient evidence of switching."),
    )
    json.dump(dict(summary=summary, records=records), open(OUT / "audit.json", "w"), indent=2)
    with open(OUT / "audit_summary.csv", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["name", "n_his_sequence", "L_5.5_7.4", "L_6.0_7.4", "n_groups_6.0", "n_binder_his_6.0", "direction_6.0"])
        for x in sorted(scored, key=lambda z: -(z.get("L_6.0_7.4") or -999)):
            L = x.get("L_6.0_7.4")
            w.writerow([x["name"], x["n_his_sequence"], x.get("L_5.5_7.4"), L,
                        x.get("L_6.0_7.4_n_groups"), x.get("L_6.0_7.4_n_binder_his"),
                        "ACID_ON" if (L or 0) > 0 else ("ACID_OFF" if (L or 0) < 0 else "NEUTRAL")])
    md = ["# C4 linkage audit — bound vs unbound (CPU only)", "",
          "**Status: evidence only. Nothing promoted, no candidate replaced, nothing submitted.**", "",
          "## Controls", "```", json.dumps(ctl), "```", "",
          "Positive L = tighter binding at the lower pH (C4 conditional-binding direction).", "",
          "## Result", "| metric | value |", "|---|---|",
          "| preview rows | %d |" % len(rows), "| scored | %d |" % len(scored),
          "| missing complex PDB | %d |" % len(missing),
          "| L(6.0/7.4) > 0 | **%d** |" % len(pos), "| L(6.0/7.4) < 0 | **%d** |" % len(neg),
          "| L(5.5/7.4) > 0 | %d |" % summary["n_positive_L55"],
          "| L(5.5/7.4) < 0 | %d |" % summary["n_negative_L55"], "",
          "## Ranked by L(6.0/7.4), most acid-ON first", "",
          "| design | H | L 5.5/7.4 | L 6.0/7.4 | direction |", "|---|---|---|---|---|"]
    for x in sorted(scored, key=lambda z: -(z.get("L_6.0_7.4") or -999)):
        L = x.get("L_6.0_7.4")
        md.append("| %s | %d | %s | %s | %s |" % (
            x["name"], x["n_his_sequence"], x.get("L_5.5_7.4"), L,
            "ACID_ON" if (L or 0) > 0 else ("ACID_OFF" if (L or 0) < 0 else "NEUTRAL")))
    md += ["", "## Interpretation", "", summary["interpretation"], "",
           "Sign controls pass, so a negative L here means the modelled complex binds *more* tightly at the "
           "higher pH — the C3/endosomal-release direction, not C4's objective. This audit cannot prove "
           "release; it can only show whether the modelled electrostatics point the wrong way.", ""]
    (OUT / "audit.md").write_text("\n".join(md))
    json.dump(summary, open(OUT / "summary.json", "w"), indent=2)
    print("\nwrote", OUT)

if __name__ == "__main__":
    main()
