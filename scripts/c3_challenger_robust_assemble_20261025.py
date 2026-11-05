#!/usr/bin/env python3
"""Assemble an ALL-FIVE-ROBUST challenger as evidence only.

Motivation: the 08:26 sensitivity check showed the existing filtered challenger's "20/20 clash-clean"
is rank_001-only; only 2/8 replacements are clean across all five archived models. This script asks
whether a selection rule that requires all-five cleanliness can still fill 8 seats. It can.

Rule fixed BEFORE selection (same structure as the existing challenger, one criterion strengthened):
  1. keep v8's 12 ELIGIBLE rows;
  2. drop the 8 flagged rows; fill 8 seats from the depth-arm pool;
  3. candidate must be all-rules PASS, iPTM >= 0.85, refold PASS AND clash-clean in ALL FIVE models;
  4. candidate must NOT be near-identical to ANY retained row (frozen TM>=0.65/coverage>=0.80);
  5. at most one design per structural component;
  6. order by highest iPTM, tie-break lowest name.

EVIDENCE ONLY. v8 and the existing challenger are never modified. No submission, no upload.
"""
import csv, json, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
V8 = ROOT / 'results/c3_submission_v8_20261025.csv'
ELIG = ROOT / 'results/c3_v8_eligibility_20261025/eligibility.json'
LEDGER = ROOT / 'results/c3_sampling_depth_v1_20261025/coverage_ledger.json'
SEQ = ROOT / 'results/c3_sampling_depth_v1_20261025/sequences.csv'
CROSS = ROOT / 'results/c3_r3_20261025/cross_tm_20261025.json'
SENS = ROOT / 'results/c3_pool_five_model_20261025/per_design.json'
OUT = ROOT / 'results/c3_challenger_robust_20261025'
TM, COV, FLOOR = 0.65, 0.80, 0.85


def near(rec):
    return bool(rec) and rec.get('tm', 0) >= TM and rec.get('coverage', 0) >= COV


def main():
    OUT.mkdir(exist_ok=True)
    pairs = json.loads(CROSS.read_text())['pairs']
    v8rows = list(csv.DictReader(open(V8)))
    elig = {r['name']: r for r in json.loads(ELIG.read_text())['rows']}
    ledger = {r['name']: r for r in json.loads(LEDGER.read_text())['rows']}
    seqs = {r['name']: r['sequence'] for r in csv.DictReader(open(SEQ))}
    sens = {r['name']: r for r in json.loads(SENS.read_text())}

    retained = [r for r in v8rows if elig[r['name']]['disposition_PROPOSED'] == 'ELIGIBLE']
    dropped = [r for r in v8rows if elig[r['name']]['disposition_PROPOSED'] != 'ELIGIBLE']
    n_seats = len(dropped)
    retained_names = [r['name'] for r in retained]

    pool = [r for r in ledger.values()
            if r.get('status') == 'PASS' and isinstance(r.get('iptm'), (int, float))
            and r['iptm'] >= FLOOR and r.get('refold_pass') is True
            and sens.get(r['name'], {}).get('all_models_clash_clean') is True]

    universe = sorted({ledger[r['name']]['backbone'] for r in retained if r['name'] in ledger}
                      | {r['backbone'] for r in pool})
    parent = {n: n for n in universe}

    def find(x):
        parent.setdefault(x, x)
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    for a in universe:
        for b, rec in pairs.get(a, {}).items():
            if b in parent and near(rec):
                ra, rb = find(a), find(b)
                if ra != rb:
                    parent[rb] = ra

    used = {find(ledger[n]['backbone']) for n in retained_names if n in ledger}

    def clashes_retained(bb):
        return any(near(pairs.get(bb, {}).get(v)) for v in retained_names)

    considered, chosen = [], []
    for r in sorted(pool, key=lambda r: (-(r.get('iptm') or 0), r['name'])):
        bb = r['backbone']
        rec = {'name': r['name'], 'backbone': bb, 'iptm': r.get('iptm'),
               'plddt': r.get('binder_mean_plddt'),
               'models_clash_clean': 'all five',
               'decision': None}
        if clashes_retained(bb):
            rec['decision'] = 'reject: near-identical to a retained v8 row'
        elif find(bb) in used:
            rec['decision'] = 'reject: component already represented'
        else:
            rec['decision'] = 'TAKE'
            used.add(find(bb))
            chosen.append(r)
        considered.append(rec)
        if len(chosen) == n_seats:
            break

    csv_path = OUT / 'c3_challenger_all5robust_20261025.csv'
    if len(chosen) == n_seats:
        with open(csv_path, 'w', newline='') as fh:
            w = csv.writer(fh)
            w.writerow(['name', 'sequence', 'molecule_class'])
            for r in retained:
                w.writerow([r['name'], r['sequence'], r['molecule_class']])
            for r in chosen:
                w.writerow([r['name'], seqs[r['name']], 'single_chain'])

    payload = {
        'status': 'COMPLETE' if len(chosen) == n_seats else 'INCOMPLETE',
        'label': 'EVIDENCE ONLY — not a submission; v8 and the existing challenger unmodified',
        'selection_rule': ('12 ELIGIBLE v8 rows + 8 seats; all-rules PASS, iPTM>=0.85, refold PASS, '
                           'clash-clean in ALL FIVE archived models, not near-identical to retained, '
                           'one per structural component, highest iPTM first'),
        'v8_rows': len(v8rows), 'retained_rows': len(retained),
        'dropped_flagged_rows': [r['name'] for r in dropped],
        'seats_to_fill': n_seats, 'seats_filled': len(chosen),
        'candidate_pool_size_all5robust': len(pool),
        'chosen': [{'name': r['name'], 'backbone': r['backbone'], 'iptm': r.get('iptm'),
                    'plddt': r.get('binder_mean_plddt'),
                    'rank1_clashes': r.get('clashes_lt2A')} for r in chosen],
        'considered': considered,
        'csv_written': str(csv_path.relative_to(ROOT)) if len(chosen) == n_seats else None,
        'caveats': [
            'structural screening only; no affinity or agonism evidence',
            'this rule excludes 22 of 30 robust designs on component/duplicate grounds',
            'same generation-breadth cost as the filtered challenger (BindCraft/RFD4 incumbents leave)',
            'a new artifact needs Ricardo approval before any use',
            'v8 and c3_challenger_filtered_20261025.csv are byte-unchanged by this script',
        ],
    }
    (OUT / 'challenger_robust.json').write_text(json.dumps(payload, indent=1) + '\n')

    lines = ['# All-five-robust challenger — EVIDENCE ONLY (not a submission)', '',
             f"- status: **{payload['status']}**; seats filled **{len(chosen)}/{n_seats}**",
             f"- rule: {payload['selection_rule']}",
             f"- all-five-robust candidate pool: **{len(pool)} designs**", '',
             '## Seats filled', '',
             '| seat | design | backbone | iPTM | pLDDT | rank_001 clashes |', '|---:|---|---|---:|---:|---:|']
    for i, c in enumerate(payload['chosen'], 1):
        lines.append(f"| {i} | `{c['name']}` | `{c['backbone']}` | {c['iptm']} | {c['plddt']} | {c['rank1_clashes']} |")
    lines += ['', '## What this is not', '']
    lines += [f'- {c}' for c in payload['caveats']]
    lines.append('')
    (OUT / 'README.md').write_text('\n'.join(lines) + '\n')

    print(json.dumps({k: v for k, v in payload.items() if k not in ('considered', 'chosen')}, indent=1))
    print('chosen:')
    for c in payload['chosen']:
        print(' ', c['name'], c['iptm'])
    return 0


if __name__ == '__main__':
    sys.exit(main())
