#!/usr/bin/env python3
"""Evaluate the LigandMPNN side-chain-context clash pilot (Astra Q1).

Applies the UNCHANGED E3 structural gate (same constants, same frozen groove set, same
clash rule <2.0 A on the same complex_rank_001.pdb stage) to both conditions, then reports
the matched-pair comparison Astra asked for: does target atomic context improve the yield of
clash-free AND fully eligible designs? Both denominators are reported (including refold
failures / unscored), never only the survivors.
"""
import collections
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / 'results/c3_e3_ligandmpnn_20261025'
SCREEN = OUT / 'screen'
PODS = ['p1', 'p2', 'p4', 'p5']


def load_scores():
    scores, errs = {}, {}
    for pod in PODS:
        for p in (SCREEN / pod).glob('**/scores.json'):
            d = json.loads(p.read_text())
            scores[d['name']] = {**d, 'pod': pod}
        for p in (SCREEN / pod).glob('**/error.json'):
            d = json.loads(p.read_text())
            errs[d['name']] = {**d, 'pod': pod}
    return scores, errs


def structural():
    """Run the shared gate once per pod dir so no design name can be shadowed."""
    merged = {}
    for pod in PODS:
        d = SCREEN / pod
        if not d.exists():
            continue
        tmp = OUT / f'struct_{pod}.json'
        r = subprocess.run(
            [sys.executable, str(ROOT / 'scripts/c3_structural_check.py'),
             '--screen-dir', str(d),
             '--seqs-csv', str(OUT / 'pilot/screen_input_20261025.csv'),
             '--out', str(tmp)],
            capture_output=True, text=True)
        if r.returncode != 0:
            print(f'  struct {pod} rc={r.returncode} {r.stderr[-300:]}')
        if tmp.exists():
            data = json.loads(tmp.read_text())
            for k, v in data.items():
                if k in merged and merged[k].get('sequence_sha256') != v.get('sequence_sha256'):
                    raise SystemExit(f'SHADOWED name {k} in {pod}')
                merged[k] = {**v, 'pod': pod}
    return merged


def main():
    scores, errs = load_scores()
    st = structural()
    parents = {p['name'] for p in json.loads((OUT / 'parents.json').read_text())}
    rows = []
    for pname in sorted(parents):
        for cond in ('0', '1'):
            name = f'lm{cond}_{pname}'
            s = scores.get(name) or {}
            v = st.get(name) or {}
            rows.append({
                'parent': pname, 'condition': int(cond), 'name': name,
                'status': ('SCORED' if name in scores else
                           'ERROR' if name in errs else 'UNSCORED'),
                'iptm': s.get('iptm'), 'ptm': s.get('ptm'),
                'mean_plddt': s.get('mean_plddt'),
                'clashes': v.get('heavy_atom_pairs_lt2A'),
                'contacts': v.get('target_binder_contacts_le5A'),
                'groove': v.get('groove_residues_contacted'),
                'binder_mean_plddt': v.get('binder_mean_plddt'),
                'eligible': bool(v.get('pass')),
                'fail': (v.get('reason') or v.get('chain_integrity_problems') or None),
            })
    # ---- aggregates, both denominators ----
    agg = {}
    for cond in (0, 1):
        sub = [r for r in rows if r['condition'] == cond]
        scored = [r for r in sub if r['status'] == 'SCORED']
        measured = [r for r in scored if r['clashes'] is not None]
        agg[cond] = {
            'n_assigned': len(sub),
            'n_scored': len(scored),
            'n_structural_measured': len(measured),
            'n_eligible': sum(1 for r in measured if r['eligible']),
            'n_clash_free': sum(1 for r in measured if r['clashes'] == 0),
            'n_iptm_ge_085': sum(1 for r in scored if (r['iptm'] or 0) >= 0.85),
            'total_clashes': sum(r['clashes'] for r in measured),
            'mean_iptm': (round(sum(r['iptm'] for r in scored) / len(scored), 4)
                          if scored else None),
        }
    # ---- matched pairs ----
    pairs = []
    for pname in sorted(parents):
        a = next(r for r in rows if r['parent'] == pname and r['condition'] == 0)
        b = next(r for r in rows if r['parent'] == pname and r['condition'] == 1)
        if a['clashes'] is None or b['clashes'] is None:
            verdict = 'INCOMPLETE'
        elif a['eligible'] and not b['eligible']:
            verdict = 'CONTEXT_WORSE'
        elif b['eligible'] and not a['eligible']:
            verdict = 'CONTEXT_BETTER'
        elif a['eligible'] and b['eligible']:
            verdict = 'BOTH_ELIGIBLE'
        else:
            verdict = 'BOTH_FAIL'
        pairs.append({'parent': pname, 'clash_sc0': a['clashes'], 'clash_sc1': b['clashes'],
                      'eligible_sc0': a['eligible'], 'eligible_sc1': b['eligible'],
                      'iptm_sc0': a['iptm'], 'iptm_sc1': b['iptm'], 'verdict': verdict})
    vc = collections.Counter(p['verdict'] for p in pairs)
    result = {'settings': {'model_type': 'ligand_mpnn',
                           'checkpoint': 'ligandmpnn_v_32_010_25.pt',
                           'temperature': 0.1, 'seed': 20261029,
                           'conditions': {'0': 'side_chain_context off',
                                          '1': 'side_chain_context on'},
                           'gate': 'unchanged E3 structural gate'},
              'aggregate': agg, 'pairs': pairs, 'pair_verdicts': dict(vc),
              'rows': rows}
    dst = OUT / 'pilot' / 'evaluation_20261025.json'
    dst.write_text(json.dumps(result, indent=1) + '\n')
    print(json.dumps({'aggregate': agg, 'pair_verdicts': dict(vc)}, indent=1))
    print(f'-> {dst}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
