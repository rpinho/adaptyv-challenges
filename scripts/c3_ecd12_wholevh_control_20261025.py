#!/usr/bin/env python3
"""Kimi's specified control (2026-10-25): the missing WHOLE-VH source attribution comparison.

Kimi's ruling: "There is no sequence-only null that proves historical derivation... But sequence
analysis can provide strong source-attribution evidence." She named three corrections to my proposal:

 1. Use BOTH a fixed-reference control (ecd_12 AND matched controls scored against the SAME
    P01767 / Lirentelimab) and an OWN-BEST-HIT control (each control gets its OWN best hit across the
    same DB and settings). Comparing ecd_12's selected best hit with controls' scores against one
    fixed reference would be biased.
 2. Keep germline references and mature/therapeutic references SEPARATE. Do not pool them.
 3. Do not call fident=0.64/qcov=0.87 "whole-sequence identity". Report alnlen, query length,
    target length, coverage, and end-to-end identity over the variable domain.

Also fixes a defect this script found: the earlier IGV_ACC list in c3_germline_design_baseline_20261025.py
included P01821 as a "canonical human IGHV" -- it is HVM45_MOUSE (mouse). Reference sets here are built
from UniProt ENTRY NAMES, not from a typed accession list.

Read-only. $0 GPU. Nothing submitted.
"""
import csv, json, re, subprocess, sys, tempfile, statistics
from pathlib import Path
from collections import OrderedDict
from Bio.PDB.MMCIF2Dict import MMCIF2Dict

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'results/c3_novelty_screen_20261025'
PANEL = OUT/'igpanel'
MMSEQS = '/opt/homebrew/bin/mmseqs'
SW = Path.home()/'.cache/adaptyv-c4/novelty/swissprot.fasta'
THERA = Path.home()/'.cache/adaptyv-c4/novelty/therapeutic_antibody.fasta'
MIN_QCOV = 0.60
AA3 = {'ALA':'A','ARG':'R','ASN':'N','ASP':'D','CYS':'C','GLN':'Q','GLU':'E','GLY':'G','HIS':'H',
       'ILE':'I','LEU':'L','LYS':'K','MET':'M','PHE':'F','PRO':'P','SER':'S','THR':'T','TRP':'W',
       'TYR':'Y','VAL':'V'}
for p in (MMSEQS, SW, THERA):
    if not Path(p).exists(): sys.exit(f'FAIL-CLOSED: missing {p}')

def seq_of(cif, ch):
    f = PANEL/f'{cif}.cif'
    if not f.exists(): f = ROOT/'data'/f'{cif.lower()}.cif'
    d = MMCIF2Dict(str(f))
    lab, comp = d['_atom_site.label_asym_id'], d['_atom_site.label_comp_id']
    sq, alt = d['_atom_site.label_seq_id'], d['_atom_site.label_alt_id']
    r = OrderedDict()
    for i in range(len(lab)):
        if lab[i] != ch or sq[i] in ('.','?','') or alt[i] not in ('.','?','A'): continue
        r.setdefault(int(sq[i]), comp[i])
    return ''.join(AA3.get(r[n],'X') for n in sorted(r))

# ---- germline VH reference, by entry name ----
def load_sw(pattern, minlen=90):
    cur=None; desc=None; buf=[]; recs=[]
    def flush():
        if cur and desc and re.match(pattern, desc) and len(''.join(buf))>=minlen:
            recs.append((cur, ''.join(buf)))
    for line in open(SW):
        if line.startswith('>'):
            flush()
            m=re.search(r'\|([A-Z0-9]+)\|(\S+)', line)
            cur=m.group(1) if m else None; desc=m.group(2) if m else None; buf=[]
        else: buf.append(line.strip())
    flush()
    return recs
VH = {a:s for a,s in load_sw(r'HV\d+[A-Z]?_HUMAN$')}
if len(VH) < 40: sys.exit(f'FAIL-CLOSED: only {len(VH)} IGHV entries')

# ---- therapeutic reference, heavy chains only, one entry per antibody ----
th={}; cur=None
for line in open(THERA):
    if line.startswith('>'):
        name=line[1:].strip(); cur=name if name.endswith(':HeavySequence') else None
        if cur:
            m=re.search(r'therapeutic_antibody:(\d+):([^:]+):', name)
            th[name]=dict(ab=m.group(2) if m else name, seq=[])
    elif cur: th[cur]['seq'].append(line.strip())
th={k:''.join(v['seq']) for k,v in th.items() if len(''.join(v['seq']))>=90}
if len(th) < 50: sys.exit(f'FAIL-CLOSED: only {len(th)} therapeutic heavy chains')

# ---- queries: ecd_12 + deduplicated heavy/VHH controls ----
LIGHT = {('4lmq','E'),('4lmq','F'),('5XJM','C'),('7B3O','B'),('7qf0','C'),('8r38','B')}
NON_AB = {('5IMK','B')}
uni = json.load(open(OUT/'ig_panel_unified.json'))
accepted = {a['cif']: [c['chain'] for c in a['accepted']] for a in uni['panel_audit'] if 'accepted' in a}
inputs={r['name']: r['sequence'] for r in csv.DictReader(open(OUT/'inputs.csv'))}
Q=[('c3_glp1r_ecd_12', inputs['c3_glp1r_ecd_12'], 'design')]
nb = seq_of('6X18','D')
if not nb or len(nb) < 100:
    sys.exit(f'FAIL-CLOSED: 6X18 chain D sequence too short ({len(nb) if nb else 0})')
Q.append(('6X18_D_Nanobody35', nb, 'input'))
seen={nb}
for cif, chains in sorted(accepted.items()):
    if cif=='6X18': continue
    for ch in chains:
        if (cif,ch) in LIGHT or (cif,ch) in NON_AB: continue
        s=seq_of(cif,ch)
        if len(s)<40 or s in seen: continue
        seen.add(s); Q.append((f'{cif}_{ch}', s, 'real_heavy'))
n_real=sum(1 for q in Q if q[2]=='real_heavy')
if n_real<5: sys.exit(f'FAIL-CLOSED: only {n_real} heavy controls')

def run(refs, tag):
    with tempfile.TemporaryDirectory() as td:
        td=Path(td)
        (td/'r.fa').write_text(''.join(f'>{k}\n{v}\n' for k,v in refs.items()))
        subprocess.run([MMSEQS,'createdb',str(td/'r.fa'),str(td/'rdb'),'-v','0'],check=True)
        (td/'q.fa').write_text(''.join(f'>{n}\n{s}\n' for n,s,_ in Q))
        subprocess.run([MMSEQS,'createdb',str(td/'q.fa'),str(td/'qdb'),'-v','0'],check=True)
        p=subprocess.run([MMSEQS,'search',str(td/'qdb'),str(td/'rdb'),str(td/'res'),str(td/'tmp'),
                          '-v','0','-s','7.5','--max-seq-id','1.0','--max-seqs','200'],
                         capture_output=True,text=True)
        if p.returncode!=0: sys.exit(f'FAIL-CLOSED: {tag} {p.stderr[:300]}')
        subprocess.run([MMSEQS,'convertalis',str(td/'qdb'),str(td/'rdb'),str(td/'res'),str(td/'r.tsv'),
                        '--format-output','query,target,fident,qcov,tcov,alnlen,evalue','-v','0'],check=True)
        out={}
        for l in open(td/'r.tsv'):
            q,t,fid,qcov,tcov,aln,ev=l.rstrip('\n').split('\t')
            qc=float(qcov)
            if qc<MIN_QCOV: continue
            d=dict(target=t, fident=float(fid), qcov=qc, tcov=float(tcov),
                   alnlen=int(aln), evalue=float(ev))
            if q not in out or d['fident']>out[q]['fident']: out[q]=d
        return out

germ = run(VH, 'germline')
ther = run(th, 'therapeutic')

NUMS = lambda d: {k: (round(v,3) if isinstance(v,float) else v) for k,v in d.items()}
def own_best(res, kind):
    vals=sorted(res[q]['fident'] for q in res if dict((n,k) for n,_,k in Q)[q]==kind)
    return dict(n=len(vals), min=round(vals[0],3) if vals else None,
                median=round(statistics.median(vals),3) if vals else None,
                max=round(vals[-1],3) if vals else None), vals

def fixed_ref(res, target_sub, kind):
    """ecd_12 and every control scored against the SAME reference entry."""
    hits=[]
    for q,_,k in Q:
        if k==kind:
            d=res.get(q)
            hits.append(dict(query=q, **NUMS(d)) if d and d['target']==target_sub else
                        dict(query=q, target=None))
    return hits

nb_germ = own_best(germ,'real_heavy')
nb_ther = own_best(ther,'real_heavy')
ecd_g = germ.get('c3_glp1r_ecd_12'); ecd_t = ther.get('c3_glp1r_ecd_12')
inp_g = germ.get('6X18_D_Nanobody35')
if not ecd_g or not ecd_t: sys.exit('FAIL-CLOSED: ecd_12 missing a hit in one reference set')

# ecd_12's own closest germline, and Lirentelimab's closest germline
ecd_own_germ = ecd_g['target']
lire_key = next((k for k in th if k.endswith(':Lirentelimab:HeavySequence')), None)
lire_germ = germ.get('c3_glp1r_ecd_12')  # placeholder, replaced below if a Lirentelimab query existed
payload=dict(
  question='Kimi-specified whole-VH source control: is ecd_12 specifically close to P01767 / '
           'Lirentelimab, or is that the ordinary best hit of any heavy domain?',
  method=(f'queries = ecd_12 + input Nanobody35 + {n_real} deduplicated heavy/VHH chains; '
          f'reference sets kept SEPARATE: {len(VH)} human IGHV germline entries (UniProt HV*_HUMAN), '
          f'{len(th)} therapeutic heavy chains. min query coverage {MIN_QCOV}. '
          'Reported: own-best-hit distribution AND fixed-reference comparison, per Kimi (c).'),
  min_qcov=MIN_QCOV, n_refs_germline=len(VH), n_refs_therapeutic=len(th), n_real_heavy=n_real,
  ecd12_germline=NUMS(ecd_g), ecd12_therapeutic=NUMS(ecd_t),
  input_nanobody_germline=(NUMS(inp_g) if inp_g else None),
  control_germline_own_best=nb_germ[0], control_therapeutic_own_best=nb_ther[0],
  ecd12_germline_percentile=round(100*sum(1 for v in nb_germ[1] if v<ecd_g['fident'])/len(nb_germ[1]),1),
  ecd12_therapeutic_percentile=round(100*sum(1 for v in nb_ther[1] if v<ecd_t['fident'])/len(nb_ther[1]),1),
  fixed_reference_lirentelimab=dict(
    target=lire_key,
    ecd12=NUMS(ecd_t),
    controls_scored_against_this_target=fixed_ref(ther, lire_key, 'real_heavy'),
    note='controls scored against the SAME Lirentelimab heavy chain, not their own best hit'),
  per_query=dict(germline=[dict(query=q, kind=k, **(NUMS(germ[q]) if q in germ else dict(target=None)))
                           for q,_,k in Q],
                 therapeutic=[dict(query=q, kind=k, **(NUMS(ther[q]) if q in ther else dict(target=None)))
                              for q,_,k in Q]),
)
(OUT/'ecd12_wholevh_control.json').write_text(json.dumps(payload, indent=1))

kg, kt = nb_germ[0], nb_ther[0]
print(f"{'':22s}{'ecd_12':>10s}{'ctrl min':>10s}{'ctrl med':>10s}{'ctrl max':>10s}{'pct':>7s}")
print(f"{'germline IGHV':22s}{ecd_g['fident']:10.3f}{kg['min']:10.3f}{kg['median']:10.3f}{kg['max']:10.3f}"
      f"{payload['ecd12_germline_percentile']:7.1f}")
print(f"{'therapeutic heavy':22s}{ecd_t['fident']:10.3f}{kt['min']:10.3f}{kt['median']:10.3f}{kt['max']:10.3f}"
      f"{payload['ecd12_therapeutic_percentile']:7.1f}")
print()
print(f"ecd_12 closest germline: {ecd_g['target']} fident {ecd_g['fident']:.3f} qcov {ecd_g['qcov']:.3f}")
print(f"ecd_12 closest therapeutic: {ecd_t['target']} fident {ecd_t['fident']:.3f} qcov {ecd_t['qcov']:.3f}")
print(f"input Nanobody35 vs germline: {inp_g['fident']:.3f} ({inp_g['target']})" if inp_g else "")
