#!/usr/bin/env python3
"""Regenerate the pool epitope sweep. $0, CPU-only, read-only. Writes no CSV, submits nothing.

WHY THIS FILE EXISTS
--------------------
`results/c3_sprint_8h_20261025/pool_epitope_sweep.json` shipped with a field named
`jaccard_vs_dominant`, and the generator that produced it was never put on disk. That made the
number unreproducible and, worse, meant its DEFINITION could not be audited. It has now been
audited and the definition was wrong. This script reimplements it exactly (so the old numbers can
be reproduced and checked) AND computes the metric that should have been used.

WHAT THE OLD FIELD ACTUALLY WAS (diagnosed 2026-10-25 13:05 ET, not assumed)
---------------------------------------------------------------------------
`jaccard_vs_dominant` was NOT a consensus profile and NOT a union profile. It was the Jaccard
overlap between each design's target-contact patch and the patch of ONE FIXED ANCHOR DESIGN,
`p4_H8_81_100_910228_sd1` (21 residues).

Evidence it is exact, not approximate: recomputing J(design, anchor_patch) reproduces all 25
shipped values to |delta| < 1e-6, mean |delta| = 0.0002 (see self-check below).

Two consequences, and they point in opposite directions from what was suspected:
  * There is NO denominator inflation. The union of all 25 patches is 35 residues; the anchor is
    21. The earlier "consensus/union denominator" hypothesis is DISCONFIRMED.
  * The error is nonetheless real and biased the same way: distance to an arbitrary anchor is
    systematically LOWER than distance to the true nearest neighbour (mean -0.124 over 25 rows),
    so the old column OVERSTATED epitope diversity. Any "nearly distinct" reading of its
    minimum (0.542) must be withdrawn.

The anchor happens to be a member of the pool, so it scores 1.000 against itself - which is why a
"minimum of 0.542" was possible in a pool whose true minimum nearest-neighbour overlap is 0.708.

METRICS REPORTED HERE
---------------------
  jaccard_max_nn      max Jaccard against ANY other design in the pool (self excluded).
                      This is the correct "is this design's epitope distinct?" statistic: a design
                      is distinct only if it is far from every other member, not far from one
                      arbitrary reference.
  jaccard_vs_anchor   legacy definition, retained ONLY to reproduce the shipped file. Do not cite.

Contact definition (matching epitope_agonist_audit.py, the shipped audit):
  target residue is a contact if any of its heavy atoms is within 4.5 A of any binder heavy atom.
  binder chain = smaller chain by atom count; target chain = larger.
  This is a PREDICTED interface from AF2m, not measured binding. No affinity, no agonism.

Usage:  python3 scripts/c3_epitope_sweep_20261025.py
Output: results/c3_sprint_8h_20261025/pool_epitope_sweep_v2.json  (original left untouched)
"""
import csv, json, sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPR = ROOT / 'results/c3_sprint_8h_20261025'
ART = ROOT / 'results/c3_pod_artifacts_20261025'
V8 = ROOT / 'results/c3_submission_v8_20261025.csv'
OLD = SPR / 'pool_epitope_sweep.json'
OUT = SPR / 'pool_epitope_sweep_v2.json'

CUT = 4.5
J_SAME = 0.5
ANCHOR = 'p4_H8_81_100_910228_sd1'
CUTS = (4.0, 4.5, 5.0)


def chains_of(pdb):
    ch = Counter()
    for line in open(pdb):
        if line.startswith('ATOM') and line[21].strip():
            ch[line[21]] += 1
    return ch


def interface_patch(pdb, cut=CUT):
    """Frozenset of target (resnum, icode) residues contacting the binder. None if not a complex."""
    ch = chains_of(pdb)
    if len(ch) < 2:
        return None
    binder = min(ch, key=lambda k: ch[k])
    target = max(ch, key=lambda k: ch[k])
    batoms, tres = [], defaultdict(list)
    for line in open(pdb):
        if not line.startswith('ATOM'):
            continue
        if (line[77:78].strip() or 'C') == 'H':      # skip hydrogens
            continue
        xyz = (float(line[30:38]), float(line[38:46]), float(line[46:54]))
        if line[21] == binder:
            batoms.append(xyz)
        elif line[21] == target:
            tres[(int(line[22:26]), line[26].strip())].append(xyz)
    c2 = cut * cut
    return frozenset(k for k, v in tres.items()
                     if any((a[0]-b[0])**2 + (a[1]-b[1])**2 + (a[2]-b[2])**2 <= c2
                            for a in v for b in batoms))


def pdb_for(name):
    """Same resolution order as epitope_agonist_audit.py - the shipped audit's PDB choice."""
    p = ART / f'{name}_complex.pdb'
    if p.exists():
        return p
    alt = sorted(ROOT.glob(f'results/**/{name}/*rank_001*multimer*.pdb'))
    return alt[0] if alt else None


def jac(a, b):
    u = len(a | b)
    return len(a & b) / u if u else 0.0


def main():
    if not OLD.exists():
        sys.exit(f'missing {OLD} - cannot reproduce the shipped values')
    shipped = json.loads(OLD.read_text())['jaccard_vs_dominant']
    names = sorted(shipped)

    patches, missing = {}, []
    for n in names:
        p = pdb_for(n)
        patch = interface_patch(p) if p else None
        if patch is None:
            missing.append(n)
            continue
        patches[n] = patch
    if missing:
        sys.exit(f'no usable structure for: {missing}')

    # ---- legacy reproduction check -------------------------------------------------
    anchor = patches[ANCHOR]
    legacy_err = [abs(jac(patches[n], anchor) - shipped[n]) for n in names]
    max_err = max(legacy_err)

    # ---- correct metric ------------------------------------------------------------
    nn = {}
    for n in names:
        others = [(jac(patches[n], patches[m]), m) for m in names if m != n]
        best = max(others)
        nn[n] = dict(jaccard_max_nn=round(best[0], 3), nearest=best[1])

    # cutoff sensitivity of the distinct count, under the correct metric
    sweep = {}
    for cut in CUTS:
        pm = {n: interface_patch(pdb_for(n), cut) for n in names}
        if any(v is None for v in pm.values()):
            continue
        vals = []
        for n in names:
            vals.append(max(jac(pm[n], pm[m]) for m in names if m != n))
        sweep[str(cut)] = dict(min_max_nn=round(min(vals), 3),
                               n_distinct_lt_0_5=sum(1 for v in vals if v < J_SAME))

    # identical-patch groups (J = 1.0 exactly) - the sharpest statement available
    groups = defaultdict(list)
    for n in names:
        groups[frozenset(patches[n])].append(n)
    identical = [sorted(v) for v in groups.values() if len(v) > 1]

    v8 = {r['name'] for r in csv.DictReader(open(V8))}
    v9b = {r['name'] for r in csv.DictReader(
        open(SPR / 'c3_candidate_v9_B-plddt_20261025.csv'))}
    admitted = sorted(v9b - v8)

    out = dict(
        method=dict(
            contact_rule=f'target heavy atom within {CUT} A of any binder heavy atom',
            binder_chain='smaller chain by atom count', target_chain='larger chain',
            structure='AF2m rank_001 model, predicted complex',
            jaccard_max_nn='max J over all other pool members, self excluded (CORRECT)',
            jaccard_vs_anchor=f'J vs fixed anchor {ANCHOR} (LEGACY, reproduces shipped file)'),
        n_admissible=len(names), n_with_structure=len(patches), n_missing=len(missing),
        anchor=ANCHOR, anchor_patch_size=len(anchor),
        union_patch_size=len(frozenset().union(*patches.values())),
        legacy_reproduction=dict(max_abs_delta=round(max_err, 8),
                                 reproduces_shipped=bool(max_err < 1e-3)),
        jaccard_max_nn={n: nn[n]['jaccard_max_nn'] for n in names},
        nearest_member={n: nn[n]['nearest'] for n in names},
        min_max_nn=round(min(v['jaccard_max_nn'] for v in nn.values()), 3),
        n_distinct_j_lt_0_5=sum(1 for v in nn.values() if v['jaccard_max_nn'] < J_SAME),
        cutoff_sensitivity=sweep,
        identical_patch_groups=identical,
        patch_sizes={n: len(patches[n]) for n in names},
        admitted_rows={n: dict(jaccard_max_nn=nn[n]['jaccard_max_nn'],
                               nearest=nn[n]['nearest']) for n in admitted if n in nn},
        caveats=[
            'Predicted AF2m interfaces only. Not measured binding, not affinity, not agonism.',
            'Single model (rank_001). Epitope stability across the other 4 AF2m models was not '
            'assessed here; a patch that moves between models is not a stable epitope.',
            'Absence of diversity is the robust claim. Presence of a distinct epitope would '
            'require model-ensemble support this file does not provide.',
        ])
    OUT.write_text(json.dumps(out, indent=1))

    # ---- console report -----------------------------------------------------------
    print(f'pool {len(names)} designs, all {len(patches)} with structures')
    print(f'legacy anchor = {ANCHOR} ({len(anchor)} res); union = {out["union_patch_size"]} res')
    print(f'legacy reproduction: max |delta| = {max_err:.2e} '
          f'({"EXACT" if max_err < 1e-3 else "MISMATCH"})')
    print(f'\ncorrect metric: min max-J (nearest neighbour) = {out["min_max_nn"]}'
          f'  -> {out["n_distinct_j_lt_0_5"]} distinct at J<{J_SAME}')
    print(f'  (legacy column said min {min(shipped.values()):.3f} - an anchor artifact)')
    for cut, d in sweep.items():
        print(f'  cutoff {cut} A: min max-J {d["min_max_nn"]}, distinct {d["n_distinct_lt_0_5"]}')
    print(f'\nidentical-patch groups (J = 1.000): {identical}')
    print(f'\nadmitted (non-v8) rows, nearest-neighbour max-J:')
    for n in admitted:
        if n in nn:
            print(f'  {n:32s} {nn[n]["jaccard_max_nn"]:.3f}  (nearest {nn[n]["nearest"]})')
    print(f'\nwrote {OUT.relative_to(ROOT)}')


if __name__ == '__main__':
    main()
