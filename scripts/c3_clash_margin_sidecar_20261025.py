#!/usr/bin/env python3
"""Reporting-only clash-margin sidecar (Kimi + Astra 07:05, both approved).

Emits, per RUN (never collapsed to a design level, never hiding discordance):
  design, seed/run id, verifier status, n clash pairs, minimum inter-chain heavy-atom
  distance (uncensored), the two atoms forming that minimum, and the frozen threshold.

NO gate change, NO eligibility change, NO re-scoring, NO frozen artifact touched.
Values come from the independent audit, not from the shared gate helper.
"""
import csv, json, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
AUD = ROOT / 'results/c3_clash_audit_20261025/audit.json'
OUT = ROOT / 'results/c3_clash_margin_sidecar_20261025'


def main():
    if not AUD.exists():
        print('no audit.json; run c3_clash_audit_independent_20261025.py first', file=sys.stderr)
        return 4
    a = json.loads(AUD.read_text())
    OUT.mkdir(exist_ok=True)
    rows = []
    for design, g in a['groups'].items():
        for r in g['runs']:
            if r.get('status') != 'READ':
                rows.append({'design': design, 'cohort': g['cohort'], 'run': None,
                             'verifier_status': None, 'clash_pairs': None,
                             'min_interchain_dist_A': None, 'closest_binder_atom': None,
                             'closest_target_atom': None, 'cutoff_A': a['cutoff_a'],
                             'note': r.get('status')})
                continue
            atoms = r.get('min_pair_atoms') or (None, None)
            rows.append({
                'design': design,
                'cohort': g['cohort'],
                'run': r.get('seed'),
                'verifier_status': r.get('verifier_status'),
                'clash_pairs': r.get('n_clash_pairs'),
                'min_interchain_dist_A': r.get('min_interchain_dist'),
                'closest_binder_atom': atoms[0],
                'closest_target_atom': atoms[1],
                'cutoff_A': a['cutoff_a'],
                'note': 'descriptive only; not a validated ranking score; gate unchanged',
            })
    rows.sort(key=lambda x: (x['design'], str(x['run'])))
    path = OUT / 'clash_margins.csv'
    with open(path, 'w', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]))
        w.writeheader()
        w.writerows(rows)

    runs = [r for r in rows if r['verifier_status'] in ('PASS', 'fail')]
    near = [r for r in runs if r['min_interchain_dist_A'] is not None
            and r['min_interchain_dist_A'] < a['cutoff_a'] + 0.05]
    fails = [r for r in runs if r['verifier_status'] == 'fail']
    md = ['# Clash-margin sidecar (reporting only)', '',
          f"- runs reported: **{len(runs)}** (seed-level, discordance preserved)",
          f"- frozen cutoff: **{a['cutoff_a']} A**; gate, eligibility and scores **unchanged**",
          f"- failing runs: **{len(fails)}**; runs within 0.05 A of the line (either side): **{len(near)}**",
          '', 'Descriptive metadata. Not a validated ranking score, not a gate change, not evidence that',
          'grazing failures are physically acceptable.', '',
          '| design | run | status | pairs | min dist (A) | closest atoms |', '|---|---|---|---|---|---|']
    for r in runs:
        md.append(f"| `{r['design']}` | {r['run']} | {r['verifier_status']} | {r['clash_pairs']} | "
                  f"{r['min_interchain_dist_A']} | {r['closest_binder_atom']}–{r['closest_target_atom']} |")
    (OUT / 'clash_margins.md').write_text('\n'.join(md) + '\n')
    print(f"SIDECAR: {len(runs)} runs -> {path}")
    print(f"  failing={len(fails)} within_0.05A={len(near)}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
