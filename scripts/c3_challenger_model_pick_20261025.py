#!/usr/bin/env python3
"""READ-ONLY: does the challenger's '20/20 clash-clean' survive an alternate model pick?

The filtered challenger's headline claim is that all 20 rows are clash-clean under one parser.
For the 8 depth-arm replacements that claim is measured ONLY on rank_001 — the top-iPTM model,
which the five-model study showed is the optimistic pick. This script re-scores all five archived
models per replacement design with the frozen verifier's own primitives, exactly as
c3_five_model_pick_20261025.py does for the 16 recovered R3 designs.

Questions:
  1. For each replacement, does rank_001 clash? (tests the replacement part of the claim)
  2. Do any alternate picks clash where rank_001 does not?
  3. Do alternates still clear the full gate (structural + iPTM floor)?
  4. How many of the 8 survive "every model clash-clean"?

Writes only results/c3_challenger_sensitivity_20261025/. No CSV, no gate change, no submission.
"""
import csv, json, pathlib, sys, re

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import c3_round2_verify_20261025 as V

CHAL = ROOT / 'results/c3_challenger_20261025/c3_challenger_filtered_20261025.csv'
INPUT = ROOT / 'results/c3_sampling_depth_v1_20261025/screen_input.csv'
GROOVE = ROOT / 'results/c3_groove_reference_20261025.json'
OUT = ROOT / 'results/c3_challenger_sensitivity_20261025'
TARGET_SHA = V.TARGET_SHA
REPLACEMENTS = [
    'p4_H8_81_100_910228_sd1', 'p1_H8_52_64_910011_sd1', 'p3_H8_81_100_910205_sd1',
    'p4_H8_65_80_910127_sd1', 'p1_H8_52_64_910009_sd2', 'p1_H8_52_64_910012_sd1',
    'p4_H8_52_64_910030_sd1', 'p5_H4_65_80_910406_sd1',
]


def design_dir(name):
    d = ROOT / f'results/c3_sampling_depth_v1_20261025/out'
    hits = sorted(d.glob(f'*/{name}'))
    return hits[0] if hits else None


def find_models(d):
    out = {}
    for p in sorted(d.glob('*scores_rank_*_alphafold2_multimer_v3_*.json')):
        m = re.search(r'scores_rank_(\d+)_', p.name)
        if not m:
            continue
        rank = int(m.group(1))
        stem = p.name.split('_scores_rank_')[0]
        cands = sorted(d.glob(f'{stem}_unrelaxed_rank_{rank:03d}_*.pdb')) or \
                sorted(d.glob(f'{stem}_rank_{rank:03d}_*.pdb'))
        out[rank] = (p, cands[0] if cands else None)
    return out


def metric_one(name, binder_expect, target_expect, scorep, pdbp, groove_set):
    r = {'name': name, 'score_file': scorep.name if scorep else None,
         'pdb_file': pdbp.name if pdbp else None}
    if scorep is None or pdbp is None:
        r['status'] = 'incomplete'; return r
    try:
        s = json.loads(scorep.read_text())
    except Exception as e:
        r['status'] = 'bad_evidence'; r['error'] = str(e); return r
    r['iptm'] = s.get('iptm'); r['ptm'] = s.get('ptm')
    chains = V.parse_pdb(pdbp)
    if len(chains) != 2:
        r['status'] = 'fail'; r['reasons'] = [f'expected 2 chains, found {sorted(chains)}']; return r
    by_seq = {c: V.seq_of(chains[c]) for c in chains}
    bids = [c for c, q in by_seq.items() if q == binder_expect]
    tids = [c for c, q in by_seq.items() if q == target_expect]
    if len(bids) != 1 or len(tids) != 1 or bids[0] == tids[0]:
        r['status'] = 'fail'; r['reasons'] = ['chain assignment ambiguous']; return r
    binder, target = chains[bids[0]], chains[tids[0]]
    r['sequence_bound'] = (V.seq_of(binder) == binder_expect and V.seq_of(target) == target_expect)
    r['target_sha_ok'] = V.sha(V.seq_of(target)).startswith(TARGET_SHA)
    bf = [b for res in binder for b in res['bfac'].values()]
    r['binder_mean_plddt'] = round(sum(bf) / len(bf), 2) if bf else 0.0
    ncon, pairs = V.contacts(binder, target, V.GROOVE_CONTACT_A)
    hits = sorted({ti + 1 for _, ti in pairs} & groove_set)
    nclash, _ = V.contacts(binder, target, V.CLASH_A)
    r.update({'contacts_le5A': ncon, 'groove_residues_contacted': len(hits),
              'clashes_lt2A': nclash, 'chain_integrity_problems': V.chain_integrity(binder)[:3]})
    why = []
    if not r['sequence_bound']: why.append('sequence mismatch')
    if not r['target_sha_ok']: why.append('target sha mismatch')
    if r['binder_mean_plddt'] < V.BINDER_PLDDT_MIN: why.append(f"pLDDT {r['binder_mean_plddt']}")
    if len(hits) < V.MIN_GROOVE: why.append(f'groove {len(hits)}')
    if ncon < V.MIN_CONTACTS: why.append(f'contacts {ncon}')
    if nclash: why.append(f'clashes {nclash}')
    if r['chain_integrity_problems']: why.append('chain integrity')
    r['structural_pass'] = not why
    r['structural_reasons'] = why
    r['iptm_ok'] = isinstance(r['iptm'], (int, float)) and r['iptm'] >= V.FLOOR
    r['all_structural_gates_pass'] = bool(r['structural_pass'] and r['iptm_ok'])
    r['clash_clean'] = nclash == 0
    return r


def main():
    inp = {r['name']: r for r in csv.DictReader(open(INPUT))}
    groove_set = set(json.loads(GROOVE.read_text())['groove_residues_1based'])
    chal_names = [r['name'] for r in csv.DictReader(open(CHAL))]
    missing = [n for n in REPLACEMENTS if n not in chal_names]
    if missing:
        print('WARNING: replacement(s) absent from challenger CSV:', missing)

    rows = []
    for name in REPLACEMENTS:
        d = design_dir(name)
        row = inp.get(name)
        if d is None or row is None:
            rows.append({'name': name, 'status': 'no_design_dir_or_input'}); continue
        models = find_models(d)
        per = [metric_one(name, row['binder'].strip(), row['target'].strip(),
                          models[k][0], models[k][1], groove_set) for k in sorted(models)]
        r1 = next((m for m in per if m['score_file'] and 'rank_001' in m['score_file']), None)
        alts = [m for m in per if m is not r1]
        alt_clash = [m for m in alts if m.get('clash_clean') is False]
        alt_pass = [m for m in alts if m.get('all_structural_gates_pass')]
        clash_only = [m for m in alts if m.get('structural_pass') is True and m.get('iptm_ok') is False]
        rows.append({
            'name': name, 'n_models': len(per), 'rank1': r1, 'per_model': per,
            'rank1_clash_clean': bool(r1 and r1.get('clash_clean')),
            'rank1_gate_pass': bool(r1 and r1.get('all_structural_gates_pass')),
            'n_alt_clashing': len(alt_clash),
            'alt_clashing_ranks': [m['score_file'] for m in alt_clash],
            'n_alt_full_gate_pass': len(alt_pass),
            'alt_clash_only_iptm_below_floor': [m['score_file'] for m in clash_only],
            'n_models_valid': len([m for m in per if m.get('clash_clean') is not None]),
            'models_complete': (len(per) == 5 and all(m.get('clash_clean') is not None for m in per)),
            'all_models_clash_clean': bool(len(per) == 5
                                           and all(m.get('clash_clean') is not None for m in per)
                                           and all(m.get('clash_clean') for m in per)),
            'any_model_gate_pass': bool((r1 and r1.get('all_structural_gates_pass')) or alt_pass),
        })

    measured = [r for r in rows if r.get('n_models')]
    n = len(measured)
    r1_clean = [r for r in measured if r['rank1_clash_clean']]
    all_clean = [r for r in measured if r['all_models_clash_clean']]
    with_alt_clash = [r for r in measured if r['n_alt_clashing']]
    gate_pass = [r for r in measured if r['any_model_gate_pass']]

    summary = {
        'designs_measured': n,
        'replacement_designs_expected': len(REPLACEMENTS),
        'rank1_clash_clean': len(r1_clean),
        'rank1_clash_clean_names': [r['name'] for r in r1_clean],
        'all_five_models_clash_clean': len(all_clean),
        'all_five_models_clash_clean_names': [r['name'] for r in all_clean],
        'designs_with_at_least_one_clashing_alternate': len(with_alt_clash),
        'names_with_alt_clash': [r['name'] for r in with_alt_clash],
        'designs_passing_full_gate_in_any_model': len(gate_pass),
        'names_passing_any_model': [r['name'] for r in gate_pass],
        'claim_scope': 'eight replacement designs only; the 12 carried-over rows have one archived model each',
        'claim_rank1_reproduced_on_replacements': len(r1_clean) == len(REPLACEMENTS),
        'claim_survives_all_models_on_replacements': len(all_clean) == len(REPLACEMENTS),
        'models_complete_count': len([r for r in measured if r.get('models_complete')]),
        'method': ('frozen verifier primitives; five archived AF2M models per design; '
                   "rank_001 = the configured multimer ranking's top pick; clash rule heavy-atom <= 2.0 A"),
        'caveat': ('A design whose rank_001 is clean but whose alternates clash is not proven '
                   'dirty; it means the pick matters and the claim is model-dependent.'),
    }
    OUT.mkdir(exist_ok=True)
    (OUT / 'summary.json').write_text(json.dumps(summary, indent=1) + '\n')
    (OUT / 'per_design_models.json').write_text(json.dumps(rows, indent=1) + '\n')

    print(f"designs measured: {n}/{len(REPLACEMENTS)}")
    print(f"rank_001 clash-clean: {len(r1_clean)}/{n}")
    print(f"ALL five models clash-clean: {len(all_clean)}/{n}")
    print(f"designs with >=1 clashing alternate: {len(with_alt_clash)}/{n}")
    print(f"designs passing full gate in any model: {len(gate_pass)}/{n}")
    for r in measured:
        r1 = r['rank1']
        print(f"  {r['name']:<32} rank1 clash={r1.get('clashes_lt2A')} iPTM={r1.get('iptm')} "
              f"struct={r1.get('structural_pass')} | altClash={r['n_alt_clashing']} "
              f"altPass={r['n_alt_full_gate_pass']} allClean={r['all_models_clash_clean']}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
