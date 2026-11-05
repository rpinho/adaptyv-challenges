#!/usr/bin/env python3
"""Orchestrator $0 audit: rebuild the replacement-seat tie-break using Astra's EXACT stated
rule ("binder pLDDT, then identifier") instead of my (iPTM desc, name asc).

Why this file exists: results/c3_sprint_8h_20261025/tiebreak_sensitivity.json revealed that 3 of
the 8 admitted seats change if Astra's rule is applied, and the pLDDT it used was scores.json's
`mean_plddt` -- a WHOLE-COMPLEX number, not a binder-only number. Astra said "binder pLDDT".
So this recomputes pLDDT from the archived complex PDB B-factor column, restricted to the binder
chain only, and reports it next to the complex-wide value so the divergence is visible.

Read-only. Writes one JSON. Touches no candidate CSV and no frozen artifact.
"""
import json, csv
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPR = ROOT/'results/c3_sprint_8h_20261025'
OUT = SPR/'tiebreak_binder_plddt.json'

prov = json.load(open(SPR/'challenger_variants_provenance.json'))

def find_pdb(name):
    for pat in (f'results/c3_r3_20261025/screen/*/{name}/*rank_001*multimer*.pdb',
                f'results/c3_sampling_depth_v1_20261025/out/*/{name}/complex_rank_001.pdb',
                f'results/**/{name}/*rank_001*multimer*.pdb',
                f'results/**/{name}/complex_rank_001.pdb'):
        alt = sorted(ROOT.glob(pat))
        if alt: return alt[0]
    return None

def binder_plddt(pdb):
    """Identify binder as the shorter chain by atom count; mean B-factor over its atoms."""
    ch = {}
    for l in open(pdb):
        if l.startswith('ATOM') and l[21].strip():
            ch[l[21]] = ch.get(l[21], 0) + 1
    if len(ch) < 2: return None, None
    binder = sorted(ch.items(), key=lambda kv: kv[1])[0][0]
    allb, cab = [], []
    for l in open(pdb):
        if not l.startswith('ATOM') or l[21] != binder: continue
        b = float(l[60:66])
        allb.append(b)
        if l[12:16].strip() == 'CA': cab.append(b)
    if not allb: return None, None
    return sum(allb)/len(allb), (sum(cab)/len(cab) if cab else None)

# --- which designs are the admitted replacement candidates? read from provenance ---
rows = []
def walk(o):
    if isinstance(o, dict):
        if 'name' in o and isinstance(o.get('iptm'), (int,float)): rows.append(o)
        for v in o.values(): walk(v)
    elif isinstance(o, list):
        for v in o: walk(v)
walk(prov)

seen, cands = set(), []
for r in rows:
    n = r['name']
    if n in seen: continue
    seen.add(n); cands.append(r)

out = {'source': 'challenger_variants_provenance.json', 'n_candidates_found': len(cands), 'designs': []}
for r in cands:
    n = r['name']
    pdb = find_pdb(n)
    if pdb is None:
        out['designs'].append(dict(name=n, iptm=r.get('iptm'), pdb=None)); continue
    mean_all, mean_ca = binder_plddt(pdb)
    out['designs'].append(dict(name=n, iptm=r.get('iptm'),
        mean_plddt_from_scores=r.get('plddt') or r.get('mean_plddt'),
        binder_plddt_allatom=mean_all, binder_plddt_ca=mean_ca, pdb=str(pdb.relative_to(ROOT))))

OUT.write_text(json.dumps(out, indent=1))
print(f"candidates discovered: {len(cands)}; with PDB: {sum(1 for d in out['designs'] if d.get('pdb'))}")
print(f"{'name':32s} {'iPTM':>5s} {'scores_plddt':>12s} {'binder_all':>10s} {'binder_CA':>9s}")
for d in sorted(out['designs'], key=lambda d: (-(d.get('iptm') or 0), d['name'])):
    a = d.get('binder_plddt_allatom'); c = d.get('binder_plddt_ca'); s = d.get('mean_plddt_from_scores')
    print(f"{d['name']:32s} {d.get('iptm') or 0:5.2f} {('%.2f'%s) if s else '     -':>12s} {('%.2f'%a) if a else '    -':>10s} {('%.2f'%c) if c else '    -':>9s}")
