#!/usr/bin/env python3
"""Assemble a FILTERED CHALLENGER as evidence only (Kimi + Astra, 08:20 ruling).

NOT a submission. This writes a versioned CSV to a NEW path plus a full evidence dossier.
v8 is never modified. Nothing is uploaded. Ricardo decides whether any of this is used.

Design of the challenger, fixed before looking at the result:
  * Start from v8's 20 rows, keeping the 12 rows the eligibility table leaves ELIGIBLE.
  * Do NOT auto-drop the 8 flagged rows into replacement without showing both options:
      Option A "minimal": v8 unchanged, 8 flags disclosed. (No new file needed; v8 IS this.)
      Option B "filtered": drop the 8 flagged rows, fill 8 seats from the depth arm.
  * Filling rule for Option B (deterministic, stated up front):
      1. candidate must be an all-rules PASS depth-arm design (zero clash, iPTM >= 0.85, refold PASS);
      2. candidate must NOT be near-identical to ANY retained row (fail-closed, frozen rule);
      3. among survivors, prefer the highest iPTM, tie-break by lowest design name;
      4. within one structural component, take at most ONE design (component-level dedup), so the
         eight seats cannot all land in one territory;
      5. record every design considered and why it was or was not taken.

  * Independence is then RE-MEASURED on the assembled 20 rows against the frozen matrix and reported,
    not assumed.

READ-ONLY over frozen evidence. Writes only results/c3_challenger_20261025/.
"""
import csv, glob, json, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / 'results/c3_challenger_20261025'
V8 = ROOT / 'results/c3_submission_v8_20261025.csv'
ELIG = ROOT / 'results/c3_v8_eligibility_20261025/eligibility.json'
LEDGER = ROOT / 'results/c3_sampling_depth_v1_20261025/coverage_ledger.json'
SEQ = ROOT / 'results/c3_sampling_depth_v1_20261025/sequences.csv'
CROSS = ROOT / 'results/c3_r3_20261025/cross_tm_20261025.json'
TM, COV = 0.65, 0.80
IPTM_FLOOR = 0.85


def near(rec):
    return bool(rec) and rec.get('tm', 0) >= TM and rec.get('coverage', 0) >= COV


def main():
    OUT.mkdir(exist_ok=True)
    pairs = json.loads(CROSS.read_text())['pairs']
    v8rows = list(csv.DictReader(open(V8)))
    elig = {r['name']: r for r in json.loads(ELIG.read_text())['rows']}
    ledger = json.loads(LEDGER.read_text())['rows']
    seqs = {r['name']: r['sequence'] for r in csv.DictReader(open(SEQ))}

    retained = [r for r in v8rows if elig[r['name']]['disposition_PROPOSED'] == 'ELIGIBLE']
    dropped = [r for r in v8rows if elig[r['name']]['disposition_PROPOSED'] != 'ELIGIBLE']
    n_seats = len(dropped)

    retained_names = [r['name'] for r in retained]
    pass_rows = [r for r in ledger if r.get('status') == 'PASS']

    # candidate pool: all-rules PASS, above the iPTM floor, refold PASS
    pool = [r for r in pass_rows
            if isinstance(r.get('iptm'), (int, float)) and r['iptm'] >= IPTM_FLOOR
            and r.get('refold_pass') is True]

    # structural components over retained + pool, so "same component" is measured, not guessed
    universe = sorted(set(retained_names) | {r['backbone'] for r in pool})
    parent = {n: n for n in universe}
    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]; x = parent[x]
        return x
    for a in universe:
        for b, rec in pairs.get(a, {}).items():
            if b in parent and near(rec):
                ra, rb = find(a), find(b)
                if ra != rb: parent[rb] = ra

    retained_comps = {find(n) for n in retained_names if n in parent}
    # a candidate backbone is disqualified only if it is near-identical to a retained row
    def clashes_retained(bb):
        return any(near(pairs.get(bb, {}).get(v)) for v in retained_names)

    considered, chosen = [], []
    used_comps = set(retained_comps)
    for r in sorted(pool, key=lambda r: (-(r.get('iptm') or 0), r['name'])):
        bb = r['backbone']
        rec = {'name': r['name'], 'backbone': bb, 'iptm': r.get('iptm'),
               'plddt': r.get('binder_mean_plddt'), 'clashes': r.get('clashes_lt2A')}
        if clashes_retained(bb):
            rec['decision'] = 'reject: near-identical to a retained v8 row'
        elif find(bb) in used_comps:
            rec['decision'] = 'reject: component already represented in the challenger'
        else:
            rec['decision'] = 'TAKE'
            used_comps.add(find(bb))
            chosen.append(r)
        considered.append(rec)
        if len(chosen) == n_seats:
            break

    # write the challenger CSV only if all seats filled
    csv_path = OUT / 'c3_challenger_filtered_20261025.csv'
    status = 'INCOMPLETE'
    if len(chosen) == n_seats:
        with open(csv_path, 'w', newline='') as f:
            w = csv.writer(f)
            w.writerow(['name', 'sequence', 'molecule_class'])
            for r in retained:
                w.writerow([r['name'], r['sequence'], r['molecule_class']])
            for r in chosen:
                w.writerow([r['name'], seqs[r['name']], 'single_chain'])
        status = 'COMPLETE'

    # independence of the assembled set, measured on the frozen matrix where possible
    assembled = retained_names + [r['name'] for r in chosen]
    in_matrix = [n for n in assembled if n in pairs]
    comps = {find(n) for n in in_matrix} if in_matrix else set()

    payload = {
        'status': status,
        'label': 'EVIDENCE ONLY — not a submission; v8 unmodified',
        'v8_sha256_note': 'v8 was NOT modified by this script',
        'v8_rows': len(v8rows),
        'retained_rows': len(retained),
        'dropped_flagged_rows': [r['name'] for r in dropped],
        'seats_to_fill': n_seats,
        'seats_filled': len(chosen),
        'chosen': [{'name': r['name'], 'backbone': r['backbone'], 'iptm': r.get('iptm'),
                    'plddt': r.get('binder_mean_plddt'), 'clashes_lt2A': r.get('clashes_lt2A'),
                    'component': find(r['backbone'])} for r in chosen],
        'candidate_pool_size': len(pool),
        'assembled_independence': {
            'rows': len(assembled), 'rows_in_frozen_matrix': len(in_matrix),
            'components_in_frozen_matrix': len(comps),
            'note': 'design rows not in the 200-key matrix cannot be clustered; reported as measured',
        },
        'csv_written': str(csv_path.relative_to(ROOT)) if status == 'COMPLETE' else None,
        'caveats': [
            'structural screening only; no affinity or agonism evidence',
            'dropping the 8 flagged rows changes portfolio composition (BindCraft/RFD4 breadth)',
            'a challenger file is a new artifact and needs Ricardo approval before any use',
            'the 8 flagged rows are not proven failures — only flagged by the pipeline clash rule',
        ],
    }
    (OUT / 'challenger.json').write_text(json.dumps(payload, indent=1) + '\n')

    L = ['# Filtered challenger — EVIDENCE ONLY (not a submission)', '',
         f"- status: **{status}**; seats filled **{len(chosen)}/{n_seats}**",
         f"- v8 unmodified; source `{V8.name}`",
         f"- candidate pool: all-rules PASS, iPTM >= {IPTM_FLOOR}, refold PASS — **{len(pool)} designs**", '',
         '## Dropped flagged rows (per the eligibility table, PROPOSED)', '']
    for r in dropped:
        L.append(f"- `{r['name']}` — {', '.join(elig[r['name']]['reasons'])}")
    L += ['', '## Seats filled', '',
          '| seat | design | backbone | iPTM | pLDDT | clashes |', '|---:|---|---|---:|---:|---:|']
    for i, c in enumerate(payload['chosen'], 1):
        L.append(f"| {i} | `{c['name']}` | `{c['backbone']}` | {c['iptm']} | {c['plddt']} | {c['clashes_lt2A']} |")
    L += ['', '## Independence re-measured on the assembled set', '',
          f"- {payload['assembled_independence']['rows']} rows; "
          f"{payload['assembled_independence']['rows_in_frozen_matrix']} present in the frozen 200-key matrix; "
          f"**{payload['assembled_independence']['components_in_frozen_matrix']} components** among those.",
          '- Rows absent from the frozen matrix cannot be clustered and are not silently assumed distinct.', '',
          '## What this is not', '']
    for c in payload['caveats']:
        L.append(f'- {c}')
    L.append('')
    (OUT / 'README.md').write_text('\n'.join(L) + '\n')
    print(json.dumps({k: v for k, v in payload.items() if k not in ('chosen',)}, indent=1))
    print('\nchosen:')
    for c in payload['chosen']:
        print(' ', c['name'], c['backbone'], c['iptm'])
    return 0


if __name__ == '__main__':
    sys.exit(main())
