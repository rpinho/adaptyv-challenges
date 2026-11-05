#!/usr/bin/env python3
"""Population-wide clash scan for all 343 C4 designs + anti-correlation test vs acid-ON direction.

Caches one row per design so downstream analyses never rescan 343 PDBs. READ-ONLY; writes only
results/c4_ranked_20261025/.
"""
import json, pathlib, sys
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from c3_clash_audit_independent_20261025 import parse_pdb, clashing_pairs, min_interchain_distance

OUT = ROOT / 'results/c4_ranked_20261025/clash_population.json'
PDB_DIR = ROOT / 'results/c4_rebuild_20261024/remote_pdbs'
AUDIT = ROOT / 'results/c4_selection_audit_20261025/audit.json'


def rankdata(xs):
    order = sorted(range(len(xs)), key=lambda i: xs[i])
    ranks = [0.0] * len(xs)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and xs[order[j + 1]] == xs[order[i]]:
            j += 1
        avg = (i + j) / 2 + 1
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    return ranks


def spearman(x, y):
    n = len(x)
    if n < 3:
        return None, None
    rx, ry = rankdata(x), rankdata(y)
    mx, my = sum(rx) / n, sum(ry) / n
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    dx = sum((a - mx) ** 2 for a in rx) ** 0.5
    dy = sum((b - my) ** 2 for b in ry) ** 0.5
    if dx == 0 or dy == 0:
        return None, None
    rho = num / (dx * dy)
    # two-sided t approximation
    import math
    t = rho * math.sqrt((n - 2) / max(1e-12, 1 - rho * rho))
    # normal approximation for p (adequate at these n)
    p = 2 * (1 - 0.5 * (1 + math.erf(abs(t) / math.sqrt(2))))
    return round(rho, 4), round(p, 5)


def main():
    aud = {r['name']: r for r in json.load(open(AUDIT))['records']}
    rows, missing = [], []
    for n, r in sorted(aud.items()):
        p = PDB_DIR / f'{n}_complex.pdb'
        if not p.exists():
            missing.append(n)
            continue
        ch = parse_pdb(str(p))
        if len(ch) != 2:
            missing.append(f'{n}:{len(ch)}ch')
            continue
        o = sorted(ch, key=lambda c: len(ch[c]))
        mind, _, _ = min_interchain_distance(ch[o[0]], ch[o[1]], 6.0)
        ncl = len(clashing_pairs(ch[o[0]], ch[o[1]], 2.0))
        rows.append({'name': n, 'min_dist': round(mind, 4), 'n_clash_pairs': ncl,
                     'clash_clean': ncl == 0, 'L6': r.get('L6'), 'iptm': r.get('iptm'),
                     'avg_complex_his_pka': r.get('avg_complex_his_pka')})
    clean = [r for r in rows if r['clash_clean']]
    scored = [r for r in rows if r.get('L6') is not None and r.get('iptm') is not None]
    elig = [r for r in scored if r['iptm'] >= 0.6]
    tests = {}
    for label, sub in (('all_scored', scored), ('eligible_iptm60', elig),
                       ('clash_clean_all', clean)):
        xs = [r['L6'] for r in sub]
        ys = [r['min_dist'] for r in sub]
        rho, p = spearman(xs, ys)
        tests[label] = {'n': len(sub), 'spearman_L6_vs_minDist': rho, 'p': p}
    by_band = {}
    for lo, hi in ((2.0, 2.2), (2.2, 2.5), (2.5, 3.0), (3.0, 99)):
        band = [r for r in clean if lo <= r['min_dist'] < hi]
        pos = sum(1 for r in band if (r['L6'] or 0) > 0)
        by_band[f'{lo}-{hi}'] = {'n_clean': len(band), 'acid_on': pos,
                                 'max_L6': round(max((r['L6'] for r in band), default=0), 3)}
    payload = {'designs_scored': len(aud), 'rows_measured': len(rows), 'missing': missing,
               'clash_clean': len(clean), 'clash_flagged': len(rows) - len(clean),
               'cleanest_min_dist': round(max((r['min_dist'] for r in clean), default=0), 4),
               'spearman_tests': tests, 'clean_by_margin_band': by_band, 'rows': rows,
               'note': ('one cached scan so the anti-correlation question can be answered without '
                        'rescanning 343 PDBs; same parser and 2.0 A rule as C3')}
    OUT.write_text(json.dumps(payload, indent=1) + '\n')
    print(json.dumps({k: v for k, v in payload.items() if k != 'rows'}, indent=1))


if __name__ == '__main__':
    main()
