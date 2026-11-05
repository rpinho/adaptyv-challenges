#!/usr/bin/env python3
"""C4 deliverable copy-sensitivity audit ($0, CPU).

Question (queued in the 09:12 handoff): does the ranked C4 set's clash verdict depend on WHICH
archived PDB copy is measured? The generator pins results/c4_rebuild_20261024/remote_pdbs/
(343/343 hash-matched), but 33/33 acid-ON designs have multiple copies and one known design
(tfr1_c4_acid_site1_158) disagreed across copies.

Method: for every design in the shipped ranked CSV, measure ALL archived copies with the same
frozen parser and 2.0 A heavy-atom inter-chain rule as c4_clash_verify_20261025.py. Then re-run
the generator's frozen selection under the ALTERNATIVE copy preference to see whether the 20-slot
file survives. READ-ONLY on all inputs and on the shipped CSV; writes only
results/c4_copy_sensitivity_20261025/.
"""
import csv, glob, json, pathlib, sys
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from c3_clash_audit_independent_20261025 import parse_pdb, clashing_pairs, min_interchain_distance

OUT = ROOT / 'results/c4_copy_sensitivity_20261025'
CSV_IN = ROOT / 'results/c4_ranked_20261025/c4_acid_ranked_20261025.csv'
CANON = ROOT / 'results/c4_rebuild_20261024/remote_pdbs'
ALT = ROOT / 'results/boltz2_complexes/boltz2_c4_acid'
CUTOFF = 2.0


def measure(p):
    ch = parse_pdb(p)
    if len(ch) != 2:
        return {'chains': len(ch), 'n_clash_pairs': None, 'min_dist': None, 'worst_pair': None}
    order = sorted(ch, key=lambda c: len(ch[c]))
    pairs = clashing_pairs(ch[order[0]], ch[order[1]], CUTOFF)
    mind, _, _ = min_interchain_distance(ch[order[0]], ch[order[1]], 6.0)
    return {'chains': len(ch), 'n_clash_pairs': len(pairs), 'min_dist': round(float(mind), 3),
            'worst_pair': pairs[0] if pairs else None}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    names = [r['name'] for r in csv.DictReader(open(CSV_IN))]
    rows, flips = [], []
    for n in names:
        copies = {}
        for label, d in (('canonical', CANON), ('alt_raw', ALT)):
            p = d / f'{n}_complex.pdb'
            if p.exists():
                copies[label] = {'path': str(p.relative_to(ROOT)), **measure(p)}
        canon = copies.get('canonical', {})
        alt = copies.get('alt_raw', {})
        verdict_c = canon.get('n_clash_pairs') == 0
        verdict_a = alt.get('n_clash_pairs') == 0
        rec = {'name': n, 'copies': copies,
               'canonical_clean': verdict_c, 'alt_clean': verdict_a,
               'verdict_agrees': verdict_c == verdict_a}
        if not rec['verdict_agrees']:
            flips.append(rec)
        rows.append(rec)

    # Re-run the generator's frozen selection with the ALTERNATIVE copy preferred.
    # Import the generator's pool logic by replaying its inputs read-only.
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        'cw', ROOT / 'scripts/c3_round2_cluster_crosswalk_20261025.py')
    cw = importlib.util.module_from_spec(spec); spec.loader.exec_module(cw)
    audit = json.load(open(ROOT / 'results/c4_selection_audit_20261025/audit.json'))
    link = json.load(open(ROOT / 'results/c4_linkage_audit_20261025/summary.json'))
    recs = [r for r in audit['records'] if r.get('L6') is not None]
    pool = [r for r in recs if r.get('iptm') is not None and r['iptm'] >= 0.60 and r['L6'] > 0]
    pool.sort(key=lambda r: (-r['L6'], -(r['iptm'] or 0), r['name']))

    chosen, rejected, measured = [], [], {}
    for r in pool:
        if len(chosen) >= 20:
            break
        n = r['name']
        p = ALT / f'{n}_complex.pdb'
        if not p.exists():
            p = CANON / f'{n}_complex.pdb'
        if not p.exists():
            rejected.append({'name': n, 'why': 'no archived structure'}); continue
        chains = parse_pdb(p)
        if len(chains) != 2:
            rejected.append({'name': n, 'why': f'{len(chains)} chains'}); continue
        order = sorted(chains, key=lambda c: len(chains[c]))
        ncl = len(clashing_pairs(chains[order[0]], chains[order[1]], CUTOFF))
        if ncl:
            rejected.append({'name': n, 'why': 'alt-copy clash', 'n_clash_pairs': ncl}); continue
        rec = cw.load(p, n)
        if rec is None:
            rejected.append({'name': n, 'why': '<20 CA'}); continue
        dup = None
        for name, prior in measured.items():
            c = cw.compare(rec, prior)
            if c and c['tm'] >= 0.65 and c['coverage'] >= 0.80:
                dup = {'name': name, 'tm': c['tm'], 'coverage': c['coverage']}; break
        if dup:
            rejected.append({'name': n, 'why': 'near-identical to retained', 'to': dup['name'],
                             'tm': dup['tm'], 'coverage': dup['coverage']}); continue
        dmin, _, _ = min_interchain_distance(chains[order[0]], chains[order[1]], 6.0)
        chosen.append(dict(r, n_clash_pairs=0, d_min=round(float(dmin), 3)))
        measured[n] = rec

    alt_names = [r['name'] for r in chosen]
    dropped = [n for n in names if n not in alt_names]
    added = [n for n in alt_names if n not in names]
    payload = {
        'question': 'does the shipped C4 ranked set survive measurement of the alternative PDB copy?',
        'cutoff_A': CUTOFF,
        'rows_in_shipped_csv': len(names),
        'copies_measured_per_design': {'canonical': str(CANON.relative_to(ROOT)),
                                       'alt_raw': str(ALT.relative_to(ROOT))},
        'designs_with_identical_copies': sum(1 for r in rows
            if all(c['n_clash_pairs'] == r['copies']['canonical']['n_clash_pairs']
                   for c in r['copies'].values())),
        'designs_with_verdict_flip': len(flips),
        'flip_names': [f['name'] for f in flips],
        'alt_selection_slots_filled': len(chosen),
        'alt_selection_dropped_vs_shipped': dropped,
        'alt_selection_added_vs_shipped': added,
        'alt_selection_rejections': rejected,
        'rows': rows,
        'caveats': [
            'the canonical copy is the provenance-verified one (343/343 hash-matched in c4_reconciliation_20261025.md); the alt raw copy is not established as authoritative',
            'a verdict flip shows the clash verdict is copy-sensitive for that design, NOT which copy is right',
            'a 2.0 A heavy-atom screen is atom-type-blind and permissive; passing it is not interface plausibility',
        ],
    }
    (OUT / 'copy_sensitivity.json').write_text(json.dumps(payload, indent=1) + '\n')
    print(json.dumps({k: v for k, v in payload.items() if k not in ('rows',)}, indent=1)[:3000])


if __name__ == '__main__':
    main()
