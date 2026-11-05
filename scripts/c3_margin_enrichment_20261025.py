#!/usr/bin/env python3
"""Geometry-aware enrichment: does continuous clearance margin separate PASS from FAIL?

Astra + Kimi 06:40, step 2 of the agreed triage order. Retrospective and EXPLORATORY by
their instruction. Nothing is re-scored: PASS/FAIL labels are read from the frozen
verifier output, and this script only asks whether margin predicts them.

Cohort: the 172 frozen sampling-depth designs (both draws pooled), because that is the only
set on disk with a balanced PASS/FAIL mix and complete artifacts.

Metric: minimum inter-chain heavy-atom distance (uncensored), computed by this script's own
parser. Reported by gate class, with AUC (rank separation) — 0.5 = no signal, 1.0 = perfect.

Writes results/c3_margin_enrichment_20261025/{enrichment.json,enrichment.md}. Read-only
elsewhere; never writes a submission CSV and never edits a frozen artifact.
"""
import collections, json, math, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
SD = ROOT / 'results/c3_sampling_depth_v1_20261025'
OUT = ROOT / 'results/c3_margin_enrichment_20261025'
SCAN = 6.0
HEAVY_OK = lambda n: not (n.startswith('H') or (n[:1].isdigit() and 'H' in n[:2]))


def parse(path):
    chains, seen = collections.OrderedDict(), collections.OrderedDict()
    for line in open(path):
        if not line.startswith(('ATOM', 'HETATM')):
            continue
        if line[16] not in (' ', 'A'):
            continue
        name = line[12:16].strip()
        if not HEAVY_OK(name):
            continue
        ch, resseq = line[21], int(line[22:26])
        el = line[76:78].strip().upper()
        if el == 'H':
            continue
        key = (ch, resseq, line[26])
        if key not in seen:
            seen[key] = {'atoms': {}}
            chains.setdefault(ch, []).append(seen[key])
        try:
            seen[key]['atoms'][name] = (float(line[30:38]), float(line[38:46]), float(line[46:54]))
        except ValueError:
            continue
    return chains


def min_dist(path):
    ch = parse(path)
    if len(ch) != 2:
        return None
    order = sorted(ch, key=lambda c: len(ch[c]))
    a, b = ch[order[0]], ch[order[1]]
    best, s2 = None, SCAN * SCAN
    for ra in a:
        for pa in ra['atoms'].values():
            for rb in b:
                for pb in rb['atoms'].values():
                    dx, dy, dz = pa[0] - pb[0], pa[1] - pb[1], pa[2] - pb[2]
                    d2 = dx * dx + dy * dy + dz * dz
                    if d2 <= s2 and (best is None or d2 < best):
                        best = d2
    return round(math.sqrt(best), 3) if best is not None else None


def auc(pos, neg):
    """Probability a random PASS has a larger margin than a random FAIL (Mann-Whitney)."""
    if not pos or not neg:
        return None
    wins = 0.0
    for p in pos:
        for n in neg:
            wins += 1.0 if p > n else (0.5 if p == n else 0.0)
    return wins / (len(pos) * len(neg))


def main():
    ver = json.loads((SD / 'verify.json').read_text())
    recs = ver['records']
    rows = []
    for r in recs:
        status = r.get('status')
        if status not in ('PASS', 'fail'):
            continue
        pdb = pathlib.Path(r['artifact_dir']) / 'complex_rank_001.pdb'
        if not pdb.exists():
            continue
        rows.append({'name': r['name'], 'status': status,
                     'backbone': r.get('backbone'), 'iptm': r.get('iptm'),
                     'min_dist': min_dist(pdb), 'clashes': r.get('clashes_lt2A')})
    pos = [x['min_dist'] for x in rows if x['status'] == 'PASS' and x['min_dist']]
    neg = [x['min_dist'] for x in rows if x['status'] == 'fail' and x['min_dist']]

    def med(v):
        v = sorted(v)
        n = len(v)
        return (v[n // 2] if n % 2 else (v[n // 2 - 1] + v[n // 2]) / 2) if v else None

    # enrichment table: PASS rate by margin band
    bands = [(0, 1.5), (1.5, 1.9), (1.9, 2.0), (2.0, 2.1), (2.1, 6.0)]
    tab = []
    for lo, hi in bands:
        sub = [x for x in rows if x['min_dist'] is not None and lo <= x['min_dist'] < hi]
        p = sum(1 for x in sub if x['status'] == 'PASS')
        tab.append({'band': f'{lo}-{hi} A', 'n': len(sub), 'pass': p,
                    'pass_rate': round(p / len(sub), 3) if sub else None})
    # iPTM AUC for contrast (the surrogate we have been optimising)
    ipos = [x['iptm'] for x in rows if x['status'] == 'PASS' and x['iptm'] is not None]
    ineg = [x['iptm'] for x in rows if x['status'] == 'fail' and x['iptm'] is not None]

    res = {
        'generated': __import__('datetime').datetime.now().astimezone().isoformat(timespec='seconds'),
        'cohort': 'c3_sampling_depth_v1_20261025 (172 frozen designs)',
        'n_scored': len(rows), 'n_pass': len(pos), 'n_fail': len(neg),
        'median_margin_pass': med(pos), 'median_margin_fail': med(neg),
        'auc_margin': round(auc(pos, neg), 3) if auc(pos, neg) is not None else None,
        'auc_iptm': round(auc(ipos, ineg), 3) if auc(ipos, ineg) is not None else None,
        'enrichment_by_band': tab,
        'label': 'EXPLORATORY retrospective; not a gate change, not a ranking score',
        'rows': rows,
    }
    OUT.mkdir(exist_ok=True)
    (OUT / 'enrichment.json').write_text(json.dumps(res, indent=1) + '\n')
    L = ['# Clearance margin vs gate outcome (exploratory, CPU, $0)', '',
         f"- cohort: **{res['cohort']}**; scored **{res['n_scored']}** "
         f"(PASS {res['n_pass']} / FAIL {res['n_fail']})",
         f"- median minimum inter-chain distance: **PASS {res['median_margin_pass']} A** vs "
         f"**FAIL {res['median_margin_fail']} A**",
         f"- **AUC (margin) = {res['auc_margin']}** vs **AUC (iPTM) = {res['auc_iptm']}** "
         f"(0.5 = no signal)",
         '', '| margin band | n | PASS | PASS rate |', '|---|---|---|---|']
    for b in tab:
        L.append(f"| {b['band']} | {b['n']} | {b['pass']} | {b['pass_rate']} |")
    L += ['', 'EXPLORATORY. Retrospective on one frozen arm; not a validated ranking score,',
          'not a gate change, and not evidence that any FAIL would pass in an assay.', '']
    (OUT / 'enrichment.md').write_text('\n'.join(L) + '\n')
    print(f"ENRICHMENT n={res['n_scored']} PASS={res['n_pass']} FAIL={res['n_fail']} "
          f"medianPASS={res['median_margin_pass']} medianFAIL={res['median_margin_fail']} "
          f"AUC_margin={res['auc_margin']} AUC_iptm={res['auc_iptm']}")
    for b in tab:
        print('  ', b['band'], b['n'], b['pass'], b['pass_rate'])
    return 0


if __name__ == '__main__':
    sys.exit(main())
