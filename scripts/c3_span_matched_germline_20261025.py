#!/usr/bin/env python3
"""Is ecd_12's below-background germline score a LENGTH artifact, or real?

The confound (self-caught at 12:15 ET): ecd_12 is 83 residues; every comparison heavy chain is
118-220 residues. A short query gets less signal and the qcov>=0.60 floor admits weaker local
alignments for it. So "percentile 0.0" could be about query length, not about ecd_12.

Decisive test, $0: take each real heavy chain and TRUNCATE it to 83 aa (an N-terminal VH-sized
fragment, the same length as ecd_12), then re-search against the SAME 54-entry IGHV germline set
with the SAME settings and coverage floor. Also try a middle 83-aa window and a C-terminal 83-aa
window, since where the VH domain sits in a Fab chain varies.

  If truncated real VH domains still score ~0.80  -> length does NOT explain it; ecd_12 is genuinely low.
  If truncated real VH domains drop to ~0.63      -> it was largely a length/span artifact.

Reports every condition; no cherry-picking of the flattering one.
"""
import json, re, subprocess, sys, tempfile, statistics, csv
from pathlib import Path
from collections import OrderedDict
from Bio.PDB.MMCIF2Dict import MMCIF2Dict

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'results/c3_novelty_screen_20261025'
PANEL = OUT/'igpanel'
MMSEQS = '/opt/homebrew/bin/mmseqs'
SW = Path.home()/'.cache/adaptyv-c4/novelty/swissprot.fasta'
MIN_QCOV = 0.60
ECD_LEN = 83
AA3 = {'ALA':'A','ARG':'R','ASN':'N','ASP':'D','CYS':'C','GLN':'Q','GLU':'E','GLY':'G','HIS':'H',
       'ILE':'I','LEU':'L','LYS':'K','MET':'M','PHE':'F','PRO':'P','SER':'S','THR':'T','TRP':'W',
       'TYR':'Y','VAL':'V'}

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

def load_sw(pattern, minlen=90):
    cur=desc=None; buf=[]; recs=[]
    def flush():
        if cur and desc and re.match(pattern, desc) and len(''.join(buf))>=minlen:
            recs.append((cur, ''.join(buf)))
    for line in open(SW):
        if line.startswith('>'):
            flush(); m=re.search(r'\|([A-Z0-9]+)\|(\S+)', line)
            cur=m.group(1) if m else None; desc=m.group(2) if m else None; buf=[]
        else: buf.append(line.strip())
    flush(); return recs
VH={a:s for a,s in load_sw(r'HV\d+[A-Z]?_HUMAN$')}
if len(VH)<40: sys.exit('FAIL-CLOSED: germline set too small')

LIGHT={('4lmq','E'),('4lmq','F'),('5XJM','C'),('7B3O','B'),('7qf0','C'),('8r38','B')}
NON_AB={('5IMK','B')}
uni=json.load(open(OUT/'ig_panel_unified.json'))
accepted={a['cif']:[c['chain'] for c in a['accepted']] for a in uni['panel_audit'] if 'accepted' in a}
inputs={r['name']:r['sequence'] for r in csv.DictReader(open(OUT/'inputs.csv'))}

controls=[]
for cif,chains in sorted(accepted.items()):
    if cif=='6X18': continue
    for ch in chains:
        if (cif,ch) in LIGHT or (cif,ch) in NON_AB: continue
        s=seq_of(cif,ch)
        if len(s)<ECD_LEN: continue
        controls.append((f'{cif}_{ch}', s))
seen=set(); ctl=[]
for n,s in controls:
    if s in seen: continue
    seen.add(s); ctl.append((n,s))
if len(ctl)<5: sys.exit(f'FAIL-CLOSED: only {len(ctl)} controls')

def windows(seq, L=ECD_LEN):
    out={'full': seq}
    out['nterm']=seq[:L]
    out['cterm']=seq[-L:]
    mid=(len(seq)-L)//2
    out['middle']=seq[mid:mid+L]
    return out

queries=[('c3_glp1r_ecd_12', inputs['c3_glp1r_ecd_12'], 'design', 'as_is')]
for n,s in ctl:
    for wname,w in windows(s).items():
        queries.append((f'{n}|{wname}', w, 'real_heavy', wname))

with tempfile.TemporaryDirectory() as td:
    td=Path(td)
    (td/'r.fa').write_text(''.join(f'>{a}\n{s}\n' for a,s in VH.items()))
    subprocess.run([MMSEQS,'createdb',str(td/'r.fa'),str(td/'rdb'),'-v','0'],check=True)
    (td/'q.fa').write_text(''.join(f'>{n}\n{s}\n' for n,s,_,_ in queries))
    subprocess.run([MMSEQS,'createdb',str(td/'q.fa'),str(td/'qdb'),'-v','0'],check=True)
    p=subprocess.run([MMSEQS,'search',str(td/'qdb'),str(td/'rdb'),str(td/'res'),str(td/'tmp'),'-v','0',
                      '-s','7.5','--max-seq-id','1.0','--max-seqs','200'],capture_output=True,text=True)
    if p.returncode!=0: sys.exit(f'FAIL-CLOSED: {p.stderr[:300]}')
    subprocess.run([MMSEQS,'convertalis',str(td/'qdb'),str(td/'rdb'),str(td/'res'),str(td/'r.tsv'),
                    '--format-output','query,target,fident,qcov,tcov,alnlen,evalue','-v','0'],check=True)
    best={}
    for l in open(td/'r.tsv'):
        q,t,fid,qcov,tcov,aln,ev=l.rstrip('\n').split('\t')
        qc=float(qcov)
        if qc<MIN_QCOV: continue
        d=dict(target=t,fident=float(fid),qcov=qc,tcov=float(tcov),alnlen=int(aln))
        if q not in best or d['fident']>best[q]['fident']: best[q]=d

kind={n:(k,w) for n,_,k,w in queries}
def agg(wname):
    vals=sorted(best[q]['fident'] for q in best if kind[q][0]=='real_heavy' and kind[q][1]==wname)
    return dict(n=len(vals), min=(round(vals[0],3) if vals else None),
                median=(round(statistics.median(vals),3) if vals else None),
                max=(round(vals[-1],3) if vals else None), values=[round(v,3) for v in vals])
ecd=best.get('c3_glp1r_ecd_12')
if not ecd: sys.exit('FAIL-CLOSED: ecd_12 no hit')

res={w:agg(w) for w in ('full','nterm','middle','cterm')}
payload=dict(
  question='Is ecd_12 below-background germline identity a LENGTH/SPAN artifact or a real difference?',
  method=f'each real heavy chain truncated to {ECD_LEN} aa (ecd_12 length) at N-term / middle / C-term, '
         f're-searched against the same {len(VH)} IGHV entries, qcov>={MIN_QCOV}',
  ecd12=dict(**{k:(round(v,3) if isinstance(v,float) else v) for k,v in ecd.items()}),
  ecd12_length=len(inputs['c3_glp1r_ecd_12']),
  controls=res,
  verdict={w:(('ecd_12 BELOW all controls' if res[w]['min'] and ecd['fident']<res[w]['min']
               else 'ecd_12 within/above control range')
              if res[w]['n'] else 'no controls') for w in res},
)
(OUT/'span_matched_germline.json').write_text(json.dumps(payload,indent=1))

print(f"ecd_12 ({len(inputs['c3_glp1r_ecd_12'])} aa): fident {ecd['fident']:.3f} (qcov {ecd['qcov']:.3f}, alnlen {ecd['alnlen']})")
print(f"{'window':10s}{'n':>4s}{'min':>8s}{'median':>8s}{'max':>8s}   verdict")
for w,r in res.items():
    print(f"{w:10s}{r['n']:4d}{(r['min'] if r['min'] is not None else 0):8.3f}"
          f"{(r['median'] if r['median'] is not None else 0):8.3f}"
          f"{(r['max'] if r['max'] is not None else 0):8.3f}   {payload['verdict'][w]}")
