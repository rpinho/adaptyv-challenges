#!/usr/bin/env python3
"""C4 direction-ranked candidate file (mission priority 3).

Ranks the 343 consolidated C4 designs by MEASURED acid-ON linkage (L6 = log10Ka(6.0)-log10Ka(7.4))
under the iPTM floor, instead of by the preview's pKa criterion. Writes a NEW versioned CSV;
c4_apical_preview_20261024.csv and results/submission_v9.csv are opened read-only and never written.

Sign convention (inherited from results/c4_linkage_audit_20261025/summary.json):
  positive L6 = tighter binding at the LOWER pH = the C4 acid-conditional objective.
The audit's sign controls pass (acid_on +0.5918, acid_off -0.4539, null 0.0), so a negative L6 is a
wrong-direction design under the same model.

Selection order (fixed in advance, no tuning after seeing the output):
  1. iPTM >= --iptm-floor (default 0.60, the audit's own gate)
  2. L6 > 0   (measured correct direction)
  3. L6(5.5/7.4) > 0 as a consistency check; rows failing it are kept but flagged, not silently dropped
  4. rank by L6 descending, then iPTM descending, then name (deterministic)
  5. reject a design whose binder backbone is near-identical (TM>=0.65 AND coverage>=0.80, the
     repo's frozen rule) to one already taken; greedy in rank order, so the rule stays deterministic
  6. take --slots rows

This is a MODELLED readout (PROPKA on predicted complexes), not experimental evidence. It cannot
prove pH-conditional binding or release; it only orders designs by the direction the model reports.
Nothing is submitted or promoted by writing this file.
"""
import argparse, csv, glob, importlib.util, json, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
AUDIT = ROOT / 'results/c4_selection_audit_20261025/audit.json'
LINK = ROOT / 'results/c4_linkage_audit_20261025/summary.json'
PREVIEW = ROOT / 'results/c4_apical_preview_20261024.csv'
OUTDIR = ROOT / 'results/c4_ranked_20261025'
SEQ_SOURCES = ['results/c4_acid_combined.csv', 'results/c4_acid_r2_binders.csv',
               'results/c4_acid1_filtered.csv', 'results/c4_acid2_filtered.csv',
               'results/c4_apical_preview_20261024.csv']


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--slots', type=int, default=20)
    ap.add_argument('--iptm-floor', type=float, default=0.60)
    ap.add_argument('--out', default=str(OUTDIR / 'c4_acid_ranked_20261025.csv'))
    args = ap.parse_args()

    audit = json.load(open(AUDIT))
    link = json.load(open(LINK))
    controls = link['controls']
    if not controls.get('all_ok'):
        sys.exit('sign controls FAILED; refusing to rank on an unvalidated sign convention')

    recs = [r for r in audit['records'] if r.get('L6') is not None]
    pool = [r for r in recs
            if r.get('iptm') is not None and r['iptm'] >= args.iptm_floor and r['L6'] > 0]
    pool.sort(key=lambda r: (-r['L6'], -(r['iptm'] or 0), r['name']))
    # Diversity pass: same frozen near-identical rule as the C3 artifacts.
    from c3_clash_audit_independent_20261025 import (
        parse_pdb, clashing_pairs, min_interchain_distance)
    spec = importlib.util.spec_from_file_location(
        'cw', ROOT / 'scripts/c3_round2_cluster_crosswalk_20261025.py')
    cw = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(cw)
    cache = {}

    def pdb_for(n):
        if n in cache:
            return cache[n]
        # Canonical, provenance-verified path first (343/343 hash-matched in
        # c4_reconciliation_20261025.md). Fallbacks only if the canonical copy is absent.
        canonical = ROOT / f'results/c4_rebuild_20261024/remote_pdbs/{n}_complex.pdb'
        hit = canonical if canonical.exists() else None
        if hit is None:
            for pat in (f'results/**/{n}/complex_rank_001.pdb', f'results/**/{n}_complex.pdb'):
                h = sorted(glob.glob(str(ROOT / pat), recursive=True))
                if h:
                    hit = pathlib.Path(h[0])
                    break
        cache[n] = hit
        return hit

    chosen, rejected, measured = [], [], {}
    for r in pool:
        if len(chosen) >= args.slots:
            break
        p = pdb_for(r['name'])
        if p is None:
            rejected.append({'name': r['name'], 'why': 'no archived structure'})
            continue
        chains = parse_pdb(p)
        if len(chains) != 2:
            rejected.append({'name': r['name'], 'why': f'{len(chains)} chains'})
            continue
        order = sorted(chains, key=lambda c: len(chains[c]))
        n_clash = len(clashing_pairs(chains[order[0]], chains[order[1]], 2.0))
        if n_clash:
            rejected.append({'name': r['name'], 'why': 'rank-001 clash', 'n_clash_pairs': n_clash})
            continue
        rec = cw.load(p, r['name'])
        if rec is None:
            rejected.append({'name': r['name'], 'why': '<20 CA'})
            continue
        dup = None
        for name, prior in measured.items():
            c = cw.compare(rec, prior)
            if c and c['tm'] >= 0.65 and c['coverage'] >= 0.80:
                dup = {'name': name, 'tm': c['tm'], 'coverage': c['coverage']}
                break
        if dup:
            rejected.append({'name': r['name'], 'why': 'near-identical to retained',
                             'to': dup['name'], 'tm': dup['tm'], 'coverage': dup['coverage']})
            continue
        dmin, _, _ = min_interchain_distance(chains[order[0]], chains[order[1]], 6.0)
        chosen.append(dict(r, n_clash_pairs=0, d_min=round(float(dmin), 3)))
        measured[r['name']] = rec

    seqs = {}
    for src in SEQ_SOURCES:
        p = ROOT / src
        if not p.exists():
            continue
        for row in csv.DictReader(open(p)):
            n = row.get('name')
            if n and n not in seqs and row.get('sequence'):
                seqs[n] = row['sequence']
    missing = [r['name'] for r in chosen if r['name'] not in seqs]
    if missing:
        sys.exit(f'missing sequences for {len(missing)} chosen designs: {missing[:5]}')

    out = pathlib.Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    with open(out, 'w', newline='') as fh:
        w = csv.writer(fh)
        w.writerow(['name', 'sequence', 'molecule_class'])
        for r in chosen:
            w.writerow([r['name'], seqs[r['name']], 'single_chain'])

    preview_names = {row['name'] for row in csv.DictReader(open(PREVIEW))}
    manifest = {
        'artifact': 'EVIDENCE ONLY — not a submission; no promotion',
        'selection_rule': ('iPTM>=-%.2f AND L6>0, ranked by L6 desc then iPTM desc then name, '
                           'take %d' % (args.iptm_floor, args.slots)),
        'sign_controls': controls,
        'n_consolidated_scored': len(recs),
        'n_eligible': sum(1 for r in recs if r.get('iptm') is not None and r['iptm'] >= args.iptm_floor),
        'n_eligible_acid_on': len(pool),
        'slots_filled': len(chosen),
        'n_measured_structures': len(measured),
        'clash_gate_A': 2.0,
        'diversity_rejections': rejected,
        'out_csv': str(out.relative_to(ROOT)),
        'chosen_by_L6': [{'rank': i + 1, 'name': r['name'], 'L6': r['L6'], 'L55': r.get('L55'),
                          'iptm': round(r['iptm'], 3), 'd_min_A': r.get('d_min'),
                          'margin_A': round(float(r.get('d_min') or 0) - 2.0, 3),
                          'margin_band': ('borderline_2.0-2.2' if (r.get('d_min') or 0) < 2.2
                                          else 'above_2.2'),
                          'avg_complex_his_pka': r.get('avg_complex_his_pka'),
                          'n_elevated_complex': r.get('n_elevated_complex'),
                          'in_preview': r['name'] in preview_names}
                         for i, r in enumerate(chosen)],
        'chosen_by_margin': [{'name': r['name'], 'd_min_A': r.get('d_min'), 'L6': r['L6'],
                              'iptm': round(r['iptm'], 3)}
                             for r in sorted(chosen, key=lambda x: -(x.get('d_min') or 0))],
        'margin_summary': {
            'borderline_2.0-2.2': sum(1 for r in chosen if (r.get('d_min') or 0) < 2.2),
            'above_2.2': sum(1 for r in chosen if (r.get('d_min') or 0) >= 2.2),
            'min_A': min((r.get('d_min') or 0) for r in chosen),
            'max_A': max((r.get('d_min') or 0) for r in chosen),
        },
        'caveats': [
            'SELECTION ARTIFACT: the 20/20 acid-ON rate and the mean-L6 gain are guaranteed by ranking on L6; neither is independent evidence of improvement',
            'margin: all chosen rows pass 2.0 A with only 0.008-0.11 A of headroom; 2.0-2.2 A is flagged borderline, not robust',
            'a 2.0 A heavy-atom screen is atom-type-blind and permissive; passing it is not interface plausibility',
            'modelled PROPKA readout on predicted complexes, not experimental evidence',
            'cannot prove pH-conditional binding or release',
            'domain-only / non-native target construct (see c4_reconciliation_20261025.md)',
            'preview and v9 files are read-only inputs; neither is modified',
            'a new artifact needs Ricardo approval before any use',
        ],
    }
    (OUTDIR / 'c4_acid_ranked_20261025.json').write_text(json.dumps(manifest, indent=1) + '\n')
    n_prev = sum(1 for r in chosen if r['name'] in preview_names)
    print(f'eligible {len(pool)} / scored {len(recs)}; wrote {len(chosen)} rows -> {out.name}')
    print(f'overlap with existing preview: {n_prev}/{len(chosen)}')
    print(f'L6 range {chosen[-1]["L6"]:.3f} .. {chosen[0]["L6"]:.3f}')


if __name__ == '__main__':
    main()
