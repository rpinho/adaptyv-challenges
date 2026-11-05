#!/usr/bin/env python3
"""Is ecd_12's 0.61-0.63 whole-chain identity to human IGHV germline HIGH or LOW for an antibody?

A germline VH gene is ~the same length as ecd_12 (83 aa aligned). If real VH domains score 0.80-0.95
against their germline and ecd_12 scores 0.63, then ecd_12 is NOT a near-copy of any germline --
it is a *poorly* germline-like sequence, which argues AGAINST "modified existing binder" rather than
for it. Conversely if real VH also score ~0.63, the number is ordinary and carries no signal.

Method: same mmseqs DB the novelty screen used (results/c3_novelty_screen_20261025/mm/sp, built from
swissprot.fasta), same search parameters, same reporting. Queries = the 18 non-input Ig chains from
the unified panel (real antibodies, sequence only) + ecd_12 + Nanobody35 itself. Compare the BEST
swissprot hit's fident/qcov for each. Fail-closed if the DB is missing or the positive control fails.
"""
import json, subprocess, sys, tempfile, csv
from pathlib import Path
from collections import OrderedDict
from Bio.PDB.MMCIF2Dict import MMCIF2Dict

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'results/c3_novelty_screen_20261025'
PANEL = OUT/'igpanel'
MM = OUT/'mm'
AA3 = {'ALA':'A','ARG':'R','ASN':'N','ASP':'D','CYS':'C','GLN':'Q','GLU':'E','GLY':'G','HIS':'H',
       'ILE':'I','LEU':'L','LYS':'K','MET':'M','PHE':'F','PRO':'P','SER':'S','THR':'T','TRP':'W',
       'TYR':'Y','VAL':'V'}
if not (MM/'sp').exists(): sys.exit('FAIL-CLOSED: swissprot mmseqs DB missing')
MMSEQS = '/opt/homebrew/bin/mmseqs'
if not Path(MMSEQS).exists(): sys.exit('FAIL-CLOSED: mmseqs missing')

def seq_of(cif, ch):
    d = MMCIF2Dict(str(PANEL/f'{cif}.cif'))
    lab, comp = d['_atom_site.label_asym_id'], d['_atom_site.label_comp_id']
    sq, alt = d['_atom_site.label_seq_id'], d['_atom_site.label_alt_id']
    r = OrderedDict()
    for i in range(len(lab)):
        if lab[i] != ch or sq[i] in ('.','?','') or alt[i] not in ('.','?','A'): continue
        r.setdefault(int(sq[i]), comp[i])
    return ''.join(AA3.get(r[n],'X') for n in sorted(r))

uni = json.load(open(OUT/'ig_panel_unified.json'))
accepted = {a['cif']: [c['chain'] for c in a['accepted']] for a in uni['panel_audit'] if 'accepted' in a}
inputs = {x['name']: x['sequence'] for x in csv.DictReader(open(OUT/'inputs.csv'))}

queries = [('c3_glp1r_ecd_12', inputs['c3_glp1r_ecd_12'], 'design')]
nb_seq = seq_of('6X18', 'D') if (PANEL/'6X18.cif').exists() else None
if nb_seq is None:
    d = MMCIF2Dict(str(ROOT/'data/6x18.cif'))
    lab, comp = d['_atom_site.label_asym_id'], d['_atom_site.label_comp_id']
    sq, alt = d['_atom_site.label_seq_id'], d['_atom_site.label_alt_id']
    r = OrderedDict()
    for i in range(len(lab)):
        if lab[i] != 'D' or sq[i] in ('.','?','') or alt[i] not in ('.','?','A'): continue
        r.setdefault(int(sq[i]), comp[i])
    nb_seq = ''.join(AA3.get(r[n],'X') for n in sorted(r))
queries.append(('6X18_D_Nanobody35', nb_seq, 'input_antibody'))
for cif, chains in sorted(accepted.items()):
    if cif == '6X18': continue
    for ch in chains:
        s = seq_of(cif, ch)
        if len(s) >= 40: queries.append((f'{cif}_{ch}', s, 'real_antibody'))

with tempfile.TemporaryDirectory() as td:
    td = Path(td)
    fa = td/'q.fasta'
    fa.write_text(''.join(f'>{n}\n{s}\n' for n, s, _ in queries))
    res = td/'r.m8'
    qdb = td/'qdb'
    subprocess.run([MMSEQS, 'createdb', str(fa), str(qdb), '-v', '0'], check=True)
    cmd = [MMSEQS, 'search', str(qdb), str(MM/'sp'), str(res), str(td/'tmp'), '-v', '0',
           '-s', '7.5', '--max-seq-id', '1.0']
    p = subprocess.run(cmd, capture_output=True, text=True)
    if p.returncode != 0: sys.exit(f'FAIL-CLOSED: mmseqs search failed: {p.stderr[:400]}')
    subprocess.run([MMSEQS, 'convertalis', str(qdb), str(MM/'sp'), str(res), str(td/'r.tsv'),
                    '--format-output', 'query,target,fident,qcov,tcov,evalue,bits', '-v', '0'], check=True)
    lines = [l.rstrip('\n').split('\t') for l in open(td/'r.tsv') if l.strip()]

kind = {n: k for n, _, k in queries}
best = {}
for q, t, fid, qcov, tcov, ev, bits in lines:
    f = float(fid)
    if q not in best or f > best[q]['fident']:
        best[q] = dict(target=t, fident=f, qcov=float(qcov), tcov=float(tcov), evalue=float(ev), bits=float(bits))

# positive control: the real antibody queries must hit swissprot Ig entries at high identity
real = [best[q] for q in best if kind[q] == 'real_antibody']
if not real: sys.exit('FAIL-CLOSED: no real-antibody results')
if max(r['fident'] for r in real) < 0.85: sys.exit(f'FAIL-CLOSED: positive control weak, max real fident {max(r["fident"] for r in real):.3f}')

import statistics
real_f = sorted(r['fident'] for r in real)
ecd = best['c3_glp1r_ecd_12']; nb = best['6X18_D_Nanobody35']
payload = dict(
  question='Is ecd_12 whole-chain identity to human germline VH (0.61-0.63) high or low for an antibody?',
  why='If real VH score much higher against the same germline DB, then ecd_12 is NOT a near-copy of any '
      'germline and the "modified existing binder" reading is weakened, not strengthened.',
  method='mmseqs search against the SAME swissprot DB and parameters the novelty screen used; '
         'best hit per query by fident',
  db=str(MM/'sp'), parameters=dict(s=7.5, max_seq_id=1.0),
  positive_control=dict(rule='max real-antibody best fident must be >= 0.85',
                        max_real_fident=round(max(r['fident'] for r in real),3), pass_=True),
  ecd12=dict(target=ecd['target'], fident=round(ecd['fident'],3), qcov=round(ecd['qcov'],3), evalue=ecd['evalue']),
  input_nanobody=dict(target=nb['target'], fident=round(nb['fident'],3), qcov=round(nb['qcov'],3), evalue=nb['evalue']),
  real_antibodies=dict(n=len(real_f), min=round(real_f[0],3), q1=round(real_f[len(real_f)//4],3),
                       median=round(statistics.median(real_f),3), q3=round(real_f[3*len(real_f)//4],3),
                       max=round(real_f[-1],3),
                       n_below_ecd=sum(1 for v in real_f if v < ecd['fident']),
                       percentile_of_ecd=round(100*sum(1 for v in real_f if v < ecd['fident'])/len(real_f),1)),
  per_query=[dict(query=q, kind=kind[q], **{k: (round(v,3) if isinstance(v,float) else v) for k,v in b.items()})
             for q, b in sorted(best.items(), key=lambda kv: -kv[1]['fident'])])
(OUT/'germline_control.json').write_text(json.dumps(payload, indent=1))

print(f"{'query':26s}{'kind':16s}{'target':10s}{'fident':>7s}{'qcov':>7s}{'evalue':>10s}")
for r in payload['per_query']:
    print(f"{r['query']:26s}{r['kind']:16s}{r['target']:10s}{r['fident']:7.3f}{r['qcov']:7.3f}{r['evalue']:10.2g}")
ra = payload['real_antibodies']
print()
print(f"real antibodies (n={ra['n']}) vs germline: min {ra['min']} q1 {ra['q1']} median {ra['median']} q3 {ra['q3']} max {ra['max']}")
print(f"ecd_12: {ecd['fident']:.3f}  -> percentile among real antibodies: {ra['percentile_of_ecd']}")
print(f"real antibodies scoring BELOW ecd_12: {ra['n_below_ecd']}/{ra['n']}")
