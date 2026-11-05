#!/usr/bin/env python3
"""Orchestrator $0 audit: redo the replacement-seat selection with a CORRECT binder-only pLDDT.

Bug being fixed: results/c3_sprint_8h_20261025/tiebreak_sensitivity.py called
`scores.json['mean_plddt']` "binder pLDDT". It is not. It is a whole-complex mean (~91-94 here),
while the binder chain alone scores ~95-98. Astra's ruling said "binder pLDDT, then stable design
identifier", so the sensitivity analysis compared the wrong quantity.

This version takes pLDDT from the archived rank-001 complex PDB B-factor column, binder chain only
(binder = shorter chain by atom count), and re-runs selection at the FULL 83-design pool level so
the tie-break can actually admit designs outside the current 8.

Self-check: under my original rule (iPTM desc, name asc) it must reproduce the 8 designs actually
shipped in variant B. If not, this script exits 1 and its output is not to be used.
Read-only. Writes one JSON.
"""
import csv, json, pathlib, statistics

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPR = ROOT / 'results/c3_sprint_8h_20261025'
POOL5 = ROOT / 'results/c3_pool_five_model_20261025/per_design.json'
SEQS = ROOT / 'results/c3_sampling_depth_v1_20261025/sequences.csv'
REFOLD = ROOT / 'results/c3_sampling_depth_v1_20261025/refold_checks.json'
INDEP = ROOT / 'results/c3_replacement_independence_20261025/summary.json'
MATRIX = ROOT / 'results/c3_r3_20261025/cross_tm_20261025.json'
SCORES = ROOT / 'results/c3_sampling_depth_v1_20261025/out'
OUT = SPR / 'tiebreak_corrected.json'
TM_MIN, COV_MIN, IPTM_MIN, N_SEATS = 0.65, 0.80, 0.87, 8


def pdb_for(name):
    cand = SCORES / name.split('_')[0] / name
    if not cand.is_dir(): return None
    p = cand / 'complex_rank_001.pdb'
    if p.exists(): return p
    alt = sorted(cand.glob('*rank_001*multimer*.pdb'))
    return alt[0] if alt else None


def binder_plddt(name):
    """Binder-chain-only mean pLDDT from the PDB B-factor column."""
    p = pdb_for(name)
    if p is None: return None
    ch = {}
    for l in open(p):
        if l.startswith('ATOM') and l[21].strip(): ch[l[21]] = ch.get(l[21], 0) + 1
    if len(ch) < 2: return None
    binder = sorted(ch.items(), key=lambda kv: kv[1])[0][0]
    vals = [float(l[60:66]) for l in open(p) if l.startswith('ATOM') and l[21] == binder]
    return (sum(vals) / len(vals)) if vals else None


def select(cands, n, near):
    admitted = []
    for c in cands:
        if len(admitted) == n: break
        if any(a['backbone'] == c['backbone'] for a in admitted): continue
        if all(not (near(c['backbone'], a['backbone']) or False) for a in admitted):
            admitted.append(c)
    return admitted


pool = {r['name']: r for r in json.load(open(POOL5))}
seqs = {r['name']: r for r in csv.DictReader(open(SEQS))}
refold = json.load(open(REFOLD))
per_bb = json.load(open(INDEP))['pools']['depth_pass']['per_backbone']
matrix = json.load(open(MATRIX))['pairs']


def near(a, b):
    ra, rb = matrix.get(a), matrix.get(b)
    rec = ra.get(b) if isinstance(ra, dict) else None
    if rec is None and isinstance(rb, dict): rec = rb.get(a)
    if not rec: return None
    return rec.get('tm', 0) >= TM_MIN and rec.get('coverage', 0) >= COV_MIN


base = []
for n, r in pool.items():
    bb = seqs[n]['backbone']; rf = refold.get(n) or {}
    if not r.get('all_models_clash_clean'): continue
    if (r.get('rank1_iptm') or 0) < IPTM_MIN: continue
    if not rf.get('pass'): continue
    if per_bb.get(bb, {}).get('near_identical_surviving'): continue
    base.append({'name': n, 'backbone': bb, 'iptm': r['rank1_iptm'], 'binder_plddt': binder_plddt(n)})

missing = [c['name'] for c in base if c['binder_plddt'] is None]
mine = select(sorted(base, key=lambda c: (-c['iptm'], c['name'])), N_SEATS, near)
astra = select(sorted(base, key=lambda c: (-(c['binder_plddt'] or 0), -c['iptm'], c['name'])), N_SEATS, near)
shipped = [r['name'] for r in csv.DictReader(open(SPR / 'c3_candidate_v9_B_20261025.csv'))]
shipped_admits = [n for n in shipped if n in {c['name'] for c in base}]

mn, an = [c['name'] for c in mine], [c['name'] for c in astra]
self_ok = set(mn) == set(shipped_admits)

def summarize(sel, tag):
    fam = [c['backbone'][:2] for c in sel]
    return dict(rule=tag, names=[c['name'] for c in sel],
                mean_binder_plddt=round(statistics.mean(c['binder_plddt'] or 0 for c in sel), 3),
                mean_iptm=round(statistics.mean(c['iptm'] for c in sel), 4),
                families={f: fam.count(f) for f in sorted(set(fam))})

out = dict(n_pool_candidates=len(base), missing_plddt=missing,
           self_check=dict(pass_=self_ok, shipped=shipped_admits, rederived=mn),
           my_rule=summarize(mine, 'iptm desc, name asc'),
           astra_rule_binder_plddt=summarize(astra, 'binder pLDDT desc, iptm desc, name asc'),
           differing_seats=sorted(set(mn) ^ set(an)),
           public_numbers=dict(
             v8_disposition='frozen, untouched',
             note='binder-only pLDDT replaces scores.json mean_plddt (whole-complex)'),
           candidates=[{k: (round(v, 4) if isinstance(v, float) else v) for k, v in c.items()} for c in sorted(base, key=lambda c: (-(c['binder_plddt'] or 0), c['name']))])
OUT.write_text(json.dumps(out, indent=1))

print(f'pool candidates: {len(base)}   missing binder pLDDT: {missing}')
print(f'SELF-CHECK my rule reproduces shipped 8: {"PASS" if self_ok else "FAIL"}')
if not self_ok:
    print(' shipped :', shipped_admits); print(' derived :', mn)
for lab, s in (('my rule', out['my_rule']), ('astra rule', out['astra_rule_binder_plddt'])):
    print(f"\n{lab}: mean binder pLDDT {s['mean_binder_plddt']}  mean iPTM {s['mean_iptm']}  families {s['families']}")
print('\ndiffering seats:', out['differing_seats'])
print('\ntop 14 by binder pLDDT:')
for c in out['candidates'][:14]:
    mark = ' <-astra' if c['name'] in an else ''
    mark2 = ' <-mine' if c['name'] in mn else ''
    print(f"  {c['name']:32s} iPTM {c['iptm']:.2f}  binder pLDDT {c['binder_plddt']:.2f}{mark}{mark2}")
if not self_ok: raise SystemExit(1)
