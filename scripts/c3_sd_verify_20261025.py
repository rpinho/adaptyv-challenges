#!/usr/bin/env python3
"""Score the sampling-depth arm with the UNCHANGED gate.

Reuses the exact R3/round-2 verifier (`c3_round2_verify_20261025.verify_one`) and the exact R3
refold QC and groove reference. No threshold, weight, or rule is redefined here.

Differences from the R3 verifier are mechanical only:
  * cohort = the arm's frozen `af2m_input.csv` (172 designs), not the R3 input
  * artifacts come from the arm's own `out/<pod>/` tree (no cross-pod duplicate picking)
  * refold comes from the arm's own `refold_checks.json`
  * source tag `c3_sampling_depth_v1_20261025` is the only admitted source

Writes results/c3_sampling_depth_v1_20261025/verify.json. Never writes a submission CSV.
Exits 4 if any duplicate artifact exists (a conflict must stop the analysis).
"""
import csv, hashlib, json, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import c3_round2_verify_20261025 as V  # noqa: E402

SD = ROOT / 'results/c3_sampling_depth_v1_20261025'
SRC = 'c3_sampling_depth_v1_20261025'
TARGET_SHA = '5c2bae2dac5e467bf4e802473450a7ca3729990921bbe5c45cf6025531ef36b3'
GROOVE = ROOT / 'results/c3_groove_reference_20261025.json'


def main():
    inp = SD / 'af2m_input.csv'
    refold = SD / 'refold_checks.json'
    rows = list(csv.DictReader(open(inp)))
    if not rows:
        print('SD VERIFY FAIL empty input', file=sys.stderr)
        return 4
    targets = {r['target'].strip() for r in rows}
    t = next(iter(targets))
    if len(targets) != 1 or len(t) != 111 or \
            hashlib.sha256(t.encode()).hexdigest() != TARGET_SHA:
        print('SD VERIFY FAIL target is not the frozen 111-mer', file=sys.stderr)
        return 4
    if {r['source'] for r in rows} != {SRC}:
        print('SD VERIFY FAIL non-arm source in arm input', file=sys.stderr)
        return 4

    loc = {}
    for p in sorted((SD / 'out').rglob('scores.json')):
        loc.setdefault(p.parent.name, []).append(p.parent)
    dup = sorted(n for n, v in loc.items() if len(v) > 1)

    ref = json.loads(refold.read_text())
    groove = set(json.loads(GROOVE.read_text())['groove_residues_1based'])

    recs = []
    for r in rows:
        n = r['name']
        hits = loc.get(n, [])
        if len(hits) > 1:
            recs.append({'name': n, 'status': 'bad_evidence',
                         'reasons': [f'{len(hits)} duplicate scored artifacts'],
                         'artifact_dirs': [str(x) for x in hits]})
            continue
        d = hits[0] if hits else SD / 'out' / 'none' / n
        rec = V.verify_one(n, r['binder'].strip(), r['target'].strip(), d,
                           ref.get(n), groove, allowed_sources=(SRC,))
        rec['backbone'] = n.rsplit('_sd', 1)[0]
        rec['draw'] = n.rsplit('_sd', 1)[1]
        recs.append(rec)

    complete = [x for x in recs if x['status'] != 'incomplete']
    passed = [x for x in recs if x['status'] == 'PASS']
    iptm_low = [x for x in recs if x['status'] != 'incomplete'
                and any('iPTM' in s for s in x.get('reasons', []))]
    out = {
        'arm': SRC,
        'input_sha256': hashlib.sha256(inp.read_bytes()).hexdigest(),
        'n_expected': len(rows),
        'n_complete': len(complete),
        'n_incomplete': len(recs) - len(complete),
        'n_pass': len(passed),
        'n_bad_evidence': sum(1 for x in recs if x['status'] == 'bad_evidence'),
        'duplicate_artifacts': dup,
        'gate': 'unchanged (same functions and thresholds as R3/round 2)',
        'thresholds': {'iptm_floor': V.FLOOR, 'clash_a': V.CLASH_A,
                       'groove_min': V.MIN_GROOVE, 'contacts_min': V.MIN_CONTACTS,
                       'binder_plddt_min': V.BINDER_PLDDT_MIN},
        'records': recs,
        'note': 'evidence only; never a submission candidate',
    }
    (SD / 'verify.json').write_text(json.dumps(out, indent=1) + '\n')

    # Completion by backbone and by draw (Astra required this if the arm truncates).
    by_draw = {}
    for k in ('1', '2'):
        sub = [x for x in recs if x.get('draw') == k]
        by_draw[f'sd{k}'] = {'expected': len(sub),
                             'complete': sum(1 for x in sub if x['status'] != 'incomplete'),
                             'pass': sum(1 for x in sub if x['status'] == 'PASS')}
    (SD / 'completion_by_draw.json').write_text(json.dumps(by_draw, indent=1) + '\n')

    print(f'SD verify: {len(complete)}/{len(recs)} complete, {len(passed)} all-rules PASS, '
          f'{out["n_bad_evidence"]} bad evidence, dup={len(dup)}')
    print(f'  by draw: {by_draw}')
    if iptm_low:
        print(f'  iPTM-floor failures among complete: {len(iptm_low)}')
    return 0 if not dup and out['n_bad_evidence'] == 0 else 4


if __name__ == '__main__':
    sys.exit(main())
