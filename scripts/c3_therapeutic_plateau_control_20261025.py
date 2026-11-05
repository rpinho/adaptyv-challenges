#!/usr/bin/env python3
"""Is the Lirentelimab heavy-chain hit (fident 0.642) SPECIFIC, or is ecd_12 merely inside the
therapeutic-antibody family plateau?

If ecd_12 hits 100+ unrelated therapeutic heavy chains at ~0.60-0.64, then "closest to Lirentelimab"
is an artifact of there being a large antibody family in the database, exactly like the nanobody
plateau already recorded (top1 0.642 / top5 0.632 / top20 0.620, gap top1-top2 0.007).

Method: parse therapeutic_hits.m8 (already computed, same run as the novelty screen). Report the
rank/fident curve for ecd_12 and for a NEGATIVE control: a design known NOT to be an antibody
(c3_bc_l70_7781fe, an Ig-fold-free design) and the other four C3 candidates.
Fail-closed if the file lacks the expected 5-column mmseqs output.
"""
import json, sys, statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'results/c3_novelty_screen_20261025'
f = OUT/'therapeutic_hits.m8'
if not f.exists(): sys.exit('FAIL-CLOSED: therapeutic_hits.m8 missing')

rows = []
for line in f.open():
    p = line.rstrip('\n').split('\t')
    if len(p) < 6: continue
    rows.append(dict(q=p[0], target=p[1], fident=float(p[2]), aln=int(p[3]), qlen=int(p[4]), qcov=float(p[5])))
if not rows: sys.exit('FAIL-CLOSED: no parsed rows')

by_q = {}
for r in rows: by_q.setdefault(r['q'], []).append(r)

CANDS = ['c3_glp1r_ecd_12','c3_glp1r_ecd_29','c3_glp1r_ecd_14','c3_glp1r_ecd_192','c3_glp1r_ecd_5','c3_glp1r_ecd_198']
NEG = ['c3_bc_l70_7781fe','c3_bc_l78_3d63fd','c3_bc_l65_8f7b63']

def curve(q):
    h = sorted(by_q.get(q, []), key=lambda x: -x['fident'])
    if not h: return None
    top = h[0]
    name = top['target'].split(':')[:3]
    return dict(
      query=q, n_hits=len(h),
      top1=round(h[0]['fident'],3), top2=round(h[1]['fident'],3) if len(h)>1 else None,
      top5=round(h[4]['fident'],3) if len(h)>4 else None,
      top20=round(h[19]['fident'],3) if len(h)>19 else None,
      gap_top1_top2=round(h[0]['fident']-h[1]['fident'],3) if len(h)>1 else None,
      top_hit=':'.join(name) if len(name)>1 else top['target'],
      top_hit_qcov=round(top['qcov'],3),
      n_at_or_above_0p60=sum(1 for x in h if x['fident'] >= 0.60),
      n_at_or_above_0p55=sum(1 for x in h if x['fident'] >= 0.55))

out = dict(
  question='Is the Lirentelimab heavy-chain match (0.642) specific to ecd_12, or a family plateau?',
  method='rank/fident curve from therapeutic_hits.m8 (same run as the novelty screen); '
         'duplicate therapeutic entries for the same antibody are NOT collapsed, so n_hits '
         'counts database entries, not distinct antibodies',
  candidates={q: curve(q) for q in CANDS if curve(q)},
  negative_controls={q: curve(q) for q in NEG if curve(q)},
)
if not out['candidates']: sys.exit('FAIL-CLOSED: no candidate curves')


print(f"{'query':24s}{'n':>5s}{'top1':>7s}{'top2':>7s}{'top5':>7s}{'top20':>7s}{'gap':>7s}{'>=.60':>7s}{'>=.55':>7s}  top hit")
for q, c in out['candidates'].items():
    print(f"{q:24s}{c['n_hits']:>5d}{c['top1']:7.3f}{(c['top2'] or 0):7.3f}{(c['top5'] or 0):7.3f}"
          f"{(c['top20'] or 0):7.3f}{(c['gap_top1_top2'] or 0):7.3f}{c['n_at_or_above_0p60']:>7d}{c['n_at_or_above_0p55']:>7d}  {c['top_hit']}")
print()
print('designs present in the therapeutic screen at all:', sorted(by_q))
absent = [q for q in CANDS+NEG if q not in by_q]
print('designs with NO therapeutic hit (identity below search floor):', absent)
out['absent_from_screen'] = absent
MD = out['candidates'].get('c3_glp1r_ecd_12')
if MD:
    print()
    print(f"VERDICT: ecd_12 top1={MD['top1']} vs top20={MD['top20']}, gap top1-top2={MD['gap_top1_top2']}, "
          f"{MD['n_at_or_above_0p60']} distinct therapeutic entries at >=0.60")

(OUT/'therapeutic_plateau_control.json').write_text(json.dumps(out, indent=1))
