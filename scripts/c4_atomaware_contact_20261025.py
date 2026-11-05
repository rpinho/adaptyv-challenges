#!/usr/bin/env python3
"""C4 crystal-calibrated inter-chain contact audit ($0, CPU) — Astra 2026-10-25 §4 item 1.

WITHDRAWN METRIC: the naive vdW-overlap count in this file (0/33 clean) is NOT valid and must not
be cited. Calibrated against the experimental TfR1 crystal 1CX8 it produced 3-5 "serious clashes"
at real dimer interfaces that are ordinary H-bonds (e.g. ASN758:CB...ARG183:O at 2.55 A), i.e. it
over-flags. See results/c4_atomaware_20261025/FINDING.md. The valid, calibrated measurement is the
crystal-referenced minimum-distance comparison in pool_vs_crystal.json.


The frozen C4 gate is a single atom-BLIND 2.0 A heavy-atom distance cutoff: it treats a C...O pair
and an H-bonding N...O pair identically. Astra's first recommended $0 computation was an atom-aware
overlap audit. Reduce/Probe are not installed on this machine, so this implements the same idea
directly from heavy-atom coordinates:

  overlap(A,B) = r_vdW(A) + r_vdW(B) - d(A,B)        (positive = interpenetration)

A pair is a SERIOUS clash at overlap >= 0.4 A (Probe's standard serious-clash threshold), and an
acceptable close contact if it involves a potential H-bond donor/acceptor and overlap < 0.4 A.
Only heavy atoms are scored and no hydrogens are added, so this is a LOWER BOUND on atom-aware
clashes (adding H can only add overlap). Reported as such, never as "Probe-validated".

Cohort: every eligible acid-ON design (iPTM>=0.60 and L6>0) under the frozen selection rule,
measured from the canonical provenance-verified copy. READ-ONLY; writes only
results/c4_atomaware_20261025/.
"""
import csv, json, math, pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / 'results/c4_atomaware_20261025'
CANON = ROOT / 'results/c4_rebuild_20261024/remote_pdbs'
RANKED = ROOT / 'results/c4_ranked_20261025/c4_acid_ranked_20261025.csv'
V2_19 = ROOT / 'results/c4_ranked_20261025/c4_tfr1_acid_candidates_v2_bothcopy_2p0Ascreen_19rows.csv'

# Bondi/Probe-style van der Waals radii (A).
VDW = {'C': 1.70, 'N': 1.55, 'O': 1.52, 'S': 1.80, 'P': 1.80, 'F': 1.47,
       'CL': 1.75, 'BR': 1.85, 'I': 1.98, 'SE': 1.90, 'H': 1.20}
SERIOUS_OVERLAP = 0.4      # Probe's serious-clash threshold
SCAN = 5.0

# Potential H-bond partners: N, O (and S weakly).
HB = {'N', 'O'}


def parse_heavy(path):
    """{chain: [ (resseq,resname,atomname,element,(x,y,z)) ]} for heavy atoms only."""
    chains = {}
    for line in open(path):
        if not line.startswith(('ATOM', 'HETATM')):
            continue
        if line[16] not in (' ', 'A'):
            continue
        name = line[12:16].strip()
        el = line[76:78].strip().upper() or name[0]
        if el == 'H' or name.startswith('H'):
            continue
        try:
            resseq = int(line[22:26])
            xyz = (float(line[30:38]), float(line[38:46]), float(line[46:54]))
        except ValueError:
            continue
        chains.setdefault(line[21], []).append(
            (resseq, line[17:20].strip(), name, el, xyz))
    return chains


def audit(path):
    chains = parse_heavy(path)
    if len(chains) != 2:
        return None
    order = sorted(chains, key=lambda c: len(chains[c]))
    binder, target = chains[order[0]], chains[order[1]]
    serious, close, worst = [], [], None
    s2 = SCAN * SCAN
    for bres, bname, batom, bel, bxyz in binder:
        for tres, tname, tatom, tel, txyz in target:
            d2 = ((bxyz[0]-txyz[0])**2 + (bxyz[1]-txyz[1])**2 + (bxyz[2]-txyz[2])**2)
            if d2 > s2:
                continue
            d = math.sqrt(d2)
            ov = VDW.get(bel, 1.7) + VDW.get(tel, 1.7) - d
            if ov <= 0:
                continue
            rec = {'binder': f'{bres}{bname}:{batom}', 'target': f'{tres}{tname}:{tatom}',
                   'dist': round(d, 3), 'overlap': round(ov, 3),
                   'elements': f'{bel}/{tel}',
                   'hbond_capable': bel in HB and tel in HB}
            if ov >= SERIOUS_OVERLAP:
                serious.append(rec)
            else:
                close.append(rec)
            if worst is None or ov > worst['overlap']:
                worst = rec
    return {'n_serious_overlap': len(serious), 'n_close_overlap': len(close),
            'max_overlap': worst['overlap'] if worst else None,
            'worst_pair': worst,
            'serious_pairs': sorted(serious, key=lambda r: -r['overlap'])[:5],
            'atomaware_clean': len(serious) == 0,
            }


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    audit_in = json.load(open(ROOT / 'results/c4_selection_audit_20261025/audit.json'))
    recs = {r['name']: r for r in audit_in['records'] if r.get('L6') is not None}
    pool = [n for n, r in recs.items()
            if r.get('iptm') is not None and r['iptm'] >= 0.60 and r['L6'] > 0]
    pool.sort(key=lambda n: (-recs[n]['L6'], -(recs[n]['iptm'] or 0), n))

    shipped = [r['name'] for r in csv.DictReader(open(RANKED))]
    v2 = [r['name'] for r in csv.DictReader(open(V2_19))]

    rows = []
    for n in pool:
        p = CANON / f'{n}_complex.pdb'
        res = audit(p)
        if res is None:
            rows.append({'name': n, 'error': 'not a 2-chain complex'}); continue
        rows.append({'name': n, 'L6': round(recs[n]['L6'], 3),
                     'iptm': round(recs[n]['iptm'], 3),
                     'in_20row_shipped': n in shipped, 'in_19row_v2': n in v2, **res})

    ok = [r for r in rows if 'atomaware_clean' in r]
    clean = [r for r in ok if r['atomaware_clean']]
    dirty = [r for r in ok if not r['atomaware_clean']]
    s_shipped = [r for r in ok if r['in_20row_shipped']]
    s_v2 = [r for r in ok if r['in_19row_v2']]

    payload = {
        'method': 'atom-aware vdW overlap from heavy-atom coordinates; positive overlap = interpenetration',
        'serious_overlap_threshold_A': SERIOUS_OVERLAP,
        'hydrogens': 'none added - reported overlap is a LOWER BOUND vs Probe',
        'cohort': 'all eligible acid-ON designs (iPTM>=0.60, L6>0), canonical copy',
        'n_pool': len(ok),
        'n_atomaware_clean': len(clean),
        'n_with_serious_overlap': len(dirty),
        'shipped_20': {'n': len(s_shipped),
                       'clean': sum(1 for r in s_shipped if r['atomaware_clean']),
                       'dirty': [r['name'] for r in s_shipped if not r['atomaware_clean']]},
        'v2_19': {'n': len(s_v2),
                  'clean': sum(1 for r in s_v2 if r['atomaware_clean']),
                  'dirty': [r['name'] for r in s_v2 if not r['atomaware_clean']]},
        'pool_ranked': [{'name': r['name'], 'L6': r['L6'], 'iptm': r['iptm'],
                         'n_serious': r['n_serious_overlap'], 'max_overlap': r['max_overlap'],
                         'clean': r['atomaware_clean'],
                         'worst_pair': r['worst_pair'],
                         'in_20': r['in_20row_shipped'], 'in_19': r['in_19row_v2']}
                        for r in ok],
        'caveats': [
            'no hydrogens added; Probe/MolProbity with H would find >= these clashes, never fewer',
            'vdW radii are a standard table, not a force field; atom typing is element-only',
            'this measures existing-coordinate quality, NOT Boltz sampling robustness',
            'a clean result here does not establish binding or pH-conditional release',
        ],
    }
    (OUT / 'atomaware_audit.json').write_text(json.dumps(payload, indent=1) + '\n')

    print(f"pool {len(ok)}: atom-aware clean {len(clean)}, with serious overlap {len(dirty)}")
    print(f"shipped 20-row: {payload['shipped_20']['clean']}/{payload['shipped_20']['n']} clean")
    print(f"v2 19-row:     {payload['v2_19']['clean']}/{payload['v2_19']['n']} clean")
    print('\nmost serious overlaps in the pool:')
    for r in sorted(dirty, key=lambda r: -r['max_overlap'])[:10]:
        w = r['worst_pair']
        print(f"  {r['name']:32s} max_ov={r['max_overlap']:.3f} n={r['n_serious_overlap']:2d} "
              f"{w['binder']}-{w['target']} ({w['elements']}, {w['dist']} A) "
              f"{'[20]' if r['in_20row_shipped'] else ''}")


if __name__ == '__main__':
    main()
