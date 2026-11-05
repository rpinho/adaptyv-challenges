#!/usr/bin/env python3
"""READ-ONLY: pool-wide model-pick sensitivity for the C3 depth arm.

The 8 challenger replacements were selected partly ON their rank_001 clash count, so "2/8 clean
across all five models" is measured on a cohort selected for rank_001 cleanliness. This script
scores the whole eligible pool (all-rules PASS, iPTM>=0.85, refold PASS) across all five archived
models, so the sensitivity rate is measured without that selection effect.

Writes only results/c3_pool_five_model_20261025/. No CSV, no gate change, no submission.
"""
import json, pathlib, sys, glob, re, csv, collections

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import c3_round2_verify_20261025 as V
import importlib.util
spec = importlib.util.spec_from_file_location('cmp_script', ROOT / 'scripts/c3_challenger_model_pick_20261025.py')
M = importlib.util.module_from_spec(spec); spec.loader.exec_module(M)

LEDGER = ROOT / 'results/c3_sampling_depth_v1_20261025/coverage_ledger.json'
INPUT = ROOT / 'results/c3_sampling_depth_v1_20261025/screen_input.csv'
GROOVE = ROOT / 'results/c3_groove_reference_20261025.json'
OUT = ROOT / 'results/c3_pool_five_model_20261025'


def main():
    inp = {r['name']: r for r in csv.DictReader(open(INPUT))}
    groove_set = set(json.loads(GROOVE.read_text())['groove_residues_1based'])
    ledger = json.loads(LEDGER.read_text())['rows']
    pool = [r for r in ledger if r.get('status') == 'PASS'
            and isinstance(r.get('iptm'), (int, float)) and r['iptm'] >= 0.85
            and r.get('refold_pass') is True]
    print(f'pool: {len(pool)} designs')

    per_design = []
    for i, r in enumerate(pool, 1):
        name = r['name']
        d = M.design_dir(name)
        row = inp.get(name)
        if d is None or row is None:
            per_design.append({'name': name, 'status': 'missing'}); continue
        models = M.find_models(d)
        per = [M.metric_one(name, row['binder'].strip(), row['target'].strip(),
                            models[k][0], models[k][1], groove_set) for k in sorted(models)]
        r1 = next((m for m in per if m['score_file'] and 'rank_001' in m['score_file']), None)
        alts = [m for m in per if m is not r1]
        alt_clash = [m for m in alts if m.get('clash_clean') is False]
        alt_pass = [m for m in alts if m.get('all_structural_gates_pass')]
        per_design.append({
            'name': name, 'n_models': len(per),
            'rank1_iptm': (r1 or {}).get('iptm'),
            'rank1_clashes': (r1 or {}).get('clashes_lt2A'),
            'rank1_clash_clean': bool(r1 and r1.get('clash_clean')),
            'n_alt_clashing': len(alt_clash),
            'all_models_clash_clean': bool(r1 and r1.get('clash_clean') and not alt_clash),
            'any_model_gate_pass': bool((r1 and r1.get('all_structural_gates_pass')) or alt_pass),
            'alt_iptm_floor_pass_exists': bool(alt_pass),
        })
        if i % 20 == 0: print(f'  scored {i}/{len(pool)}')

    m = [r for r in per_design if r.get('n_models')]
    n = len(m)
    r1clean = [r for r in m if r['rank1_clash_clean']]
    allclean = [r for r in m if r['all_models_clash_clean']]
    altclash = [r for r in m if r['n_alt_clashing']]
    anypass = [r for r in m if r['any_model_gate_pass']]
    summary = {
        'pool_designs': len(pool), 'designs_measured': n,
        'rank1_clash_clean': len(r1clean),
        'rank1_clash_clean_pct': round(100 * len(r1clean) / n, 1) if n else None,
        'all_five_models_clash_clean': len(allclean),
        'all_five_models_clash_clean_pct': round(100 * len(allclean) / n, 1) if n else None,
        'designs_with_at_least_one_clashing_alternate': len(altclash),
        'alt_clash_pct': round(100 * len(altclash) / n, 1) if n else None,
        'designs_passing_full_gate_in_any_model': len(anypass),
        'any_model_gate_pass_pct': round(100 * len(anypass) / n, 1) if n else None,
        'n_models_per_design_counts': dict(collections.Counter(r['n_models'] for r in m)),
        'selection_bias_note': ('the 8 challenger replacements were selected partly on rank_001 '
                                'clash cleanliness; this pool-wide rate has no such conditioning'),
        'method': 'frozen verifier primitives; five archived AF2M models; clash rule < 2.0 A heavy atom',
    }
    OUT.mkdir(exist_ok=True)
    (OUT / 'summary.json').write_text(json.dumps(summary, indent=1) + '\n')
    (OUT / 'per_design.json').write_text(json.dumps(per_design, indent=1) + '\n')
    print(json.dumps(summary, indent=1))
    return 0


if __name__ == '__main__':
    sys.exit(main())
