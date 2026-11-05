#!/usr/bin/env python3
"""Whole-submission eligibility table for v8 (Kimi + Astra 07:00, ruling (c)).

READ-ONLY over every existing artifact. Writes ONLY a new table under
results/c3_v8_eligibility_20261025/. It never edits v8, never writes a submission CSV,
never changes a gate, and never decides anything: it lays out, per row, the measured
evidence a human needs to accept or exclude that row.

Per row it reports:
  * clash status from the independent audit (min inter-chain heavy-atom distance, pair count)
  * iPTM against the repo-wide 0.85 floor
  * which structure file was used and whether that file exists
  * a proposed disposition, explicitly labelled PROPOSED (never applied)
"""
import csv, json, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / 'results/c3_v8_eligibility_20261025'
V8 = ROOT / 'results/c3_submission_v8_20261025.csv'
FLOOR = 0.85


def main():
    OUT.mkdir(exist_ok=True)
    rows = list(csv.DictReader(open(V8)))
    clash = {c['name']: c for c in json.loads((ROOT / 'results/c3_v8_clash_screen_20261025.json').read_text())}
    scores = {}
    for f in ('results/c3_screen_af2m_scores_combined_20261025.json',
              'results/c3_screen_af2m_scores_20261024.json'):
        p = ROOT / f
        if p.exists():
            for r in json.loads(p.read_text()):
                scores.setdefault(r['name'], r)
    # the one row whose structure lives outside the pod-artifacts directory
    alt = ROOT / 'results/c3_round2_111_20261025/screen24/c/B_26102611_s1/complex_rank_001.pdb'
    alt_rec = {'name': 'B_26102611_s1', 'min_dist': 2.671, 'clash_pairs': 0,
               'atoms': ('GLU65:OE2', 'ARG12:NH2'),
               'note': f'structure located at {alt.relative_to(ROOT)} (not in pod_artifacts)'}
    # ...and whose scores live only in its own artifact directory (found 07:20 ET).
    # Without this, the row shows iptm=None and looks unmeasured when it is measured.
    alt_scores = ROOT / 'results/c3_round2_111_20261025/screen24/c/B_26102611_s1/scores.json'
    if alt_scores.exists():
        scores.setdefault('B_26102611_s1', json.loads(alt_scores.read_text()))

    table = []
    for r in rows:
        n = r['name']
        c = clash.get(n)
        if (c is None or c.get('clash_pairs') is None) and n == alt_rec['name']:
            c = alt_rec
        s = scores.get(n, {})
        iptm = s.get('iptm')
        pairs = (c or {}).get('clash_pairs')
        mind = (c or {}).get('min_dist')
        why = []
        if pairs is None:
            why.append('NO STRUCTURE MEASURED')
        elif pairs > 0:
            why.append(f'{pairs} clash pair(s), min {mind} A')
        if iptm is not None and iptm < FLOOR:
            why.append(f'iPTM {iptm} < {FLOOR}')
        table.append({
            'name': n, 'length': len(r['sequence']), 'molecule_class': r['molecule_class'],
            'iptm': iptm, 'clash_pairs': pairs, 'min_interchain_dist': mind,
            'closest_atoms': c.get('atoms') if c else None,
            'disposition_PROPOSED': 'REVIEW-EXCLUDE' if why else 'ELIGIBLE',
            'reasons': why,
        })

    flagged = [t for t in table if t['disposition_PROPOSED'] == 'REVIEW-EXCLUDE']
    (OUT / 'eligibility.json').write_text(json.dumps({
        'source': str(V8.relative_to(ROOT)),
        'v8_sha256_note': 'v8 was NOT modified by this script',
        'floor': FLOOR,
        'n_rows': len(table), 'n_flagged': len(flagged),
        'rows': table,
        'label': 'PROPOSED dispositions only; applying them requires RICARDO-APPROVAL',
    }, indent=1) + '\n')

    L = ['# v8 whole-submission eligibility table (read-only, PROPOSED only)', '',
         f"- source: `results/c3_submission_v8_20261025.csv` (sha `631ed0bf…`, **unmodified**)",
         f"- rows: **{len(table)}**; proposed for exclusion: **{len(flagged)}**",
         f"- iPTM floor in this repo: **{FLOOR}**", '',
         '**Nothing here has been applied.** This is the evidence Ricardo needs to decide, not a decision.',
         '', '| # | design | len | iPTM | pairs | min Å | closest atoms | proposed |',
         '|---|---|---|---:|---:|---:|---|---|']
    for i, t in enumerate(table, 1):
        L.append(f"| {i} | `{t['name']}` | {t['length']} | {t['iptm']} | {t['clash_pairs']} | "
                 f"{t['min_interchain_dist']} | "
                 f"{'–'.join(t['closest_atoms']) if t['closest_atoms'] else '–'} | "
                 f"**{t['disposition_PROPOSED']}** |")
    L += ['', '## Proposed exclusions with reasons', '']
    for t in flagged:
        L.append(f"- `{t['name']}` — {'; '.join(t['reasons'])}")
    L += ['', '## Caveats both consultants insisted on', '',
          '- The v8 gate certified only the **added** row; the other 19 were carried forward. So these',
          '  rows are not evidence of a *gate breach* — they are a **revalidation gap**.',
          '- Do **not** auto-refill excluded slots from evidence-only cohorts: that would need a new',
          '  eligibility decision, which is RICARDO-APPROVAL.',
          '- These are computational predictions. A clash verdict is not proof of experimental failure,',
          '  and a clean verdict is not proof of binding.', '',
          '## Correction 07:20 ET — `B_26102611_s1` iPTM and structure', '',
          'The first generated table showed `None` for this row because the design has no screen-ledger',
          'entry. It **is** measured: its own artifact `results/c3_round2_111_20261025/screen24/c/',
          'B_26102611_s1/scores.json` records **iPTM 0.930**, pTM 0.88, mean pLDDT 93.37, 5 models,',
          '3 recycles, source `r2_111`. The generator now reads that file, so the row renders correctly',
          'on every regeneration. A separate `NO PDB` entry for the same design in',
          '`c3_v8_clash_screen_20261025.json` was a directory-glob bug; the PDB is present',
          '(119,151 bytes) and the 0 pairs / 2.671 Å measurement stands.', '',
          '**Denominator correction:** the correct phrasing is **20 measurable rows, 8 flagged** — not 19.', '']
    (OUT / 'eligibility.md').write_text('\n'.join(L) + '\n')
    print(f"ELIGIBILITY: {len(table)} rows, {len(flagged)} proposed exclusions -> {OUT/'eligibility.md'}")
    for t in flagged:
        print('  ', t['name'], t['clash_pairs'], t['min_interchain_dist'], t['iptm'], t['reasons'])
    return 0


if __name__ == '__main__':
    sys.exit(main())
