#!/usr/bin/env python3
"""CORRECTED germline control. Astra rejected the first version, correctly:

  "It selects maximum identity against ALL Swiss-Prot, without matching coverage or restricting
   hits to germline VH. Its controls include light chains, a non-antibody domain and constant-region
   matches. For example 4lmq:D scores 0.937 against P01857 at qcov 0.455."

Indeed P01834 is IGKC (kappa CONSTANT) and P01857 is IGHG1 (IgG1 CH1) -- my "real antibodies score
0.94 vs germline" finding was mostly antibodies matching their own CONSTANT region. That is not a
germline comparison and it is withdrawn.

This version fixes both defects:
  * reference set = human IGHV germline entries only (Swiss-Prot `HV*_HUMAN`, ~117 aa, V-gene),
    determined by UniProt entry name, not by sequence similarity;
  * minimum query coverage 0.60 so a constant-region fragment cannot win;
  * like-for-like queries = deduplicated heavy/VHH domains only.
It is a SEQUENCE comparison against a fixed germline panel, which is what "is this VH similar to a
germline" actually means. It still cannot establish historical derivation (Astra: that is a
provenance question) and is not presented as if it did.
"""
import csv, json, re, subprocess, sys, tempfile
from pathlib import Path
from collections import OrderedDict
from Bio.PDB.MMCIF2Dict import MMCIF2Dict

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'results/c3_novelty_screen_20261025'
PANEL = OUT/'igpanel'
MM = OUT/'mm'
MMSEQS = '/opt/homebrew/bin/mmseqs'
SW = Path.home()/'.cache/adaptyv-c4/novelty/swissprot.fasta'
MIN_QCOV = 0.60
AA3 = {'ALA':'A','ARG':'R','ASN':'N','ASP':'D','CYS':'C','GLN':'Q','GLU':'E','GLY':'G','HIS':'H',
       'ILE':'I','LEU':'L','LYS':'K','MET':'M','PHE':'F','PRO':'P','SER':'S','THR':'T','TRP':'W',
       'TYR':'Y','VAL':'V'}
for p in (MMSEQS, SW):
    if not Path(p).exists(): sys.exit(f'FAIL-CLOSED: missing {p}')

# ---- build a germline-VH-only reference FASTA from Swiss-Prot entry names ----
cur=None; desc=None; buf=[]; recs=[]
for line in open(SW):
    if line.startswith('>'):
        if cur and desc and re.match(r'HV\d+[A-Z]?_HUMAN$', desc) and len(''.join(buf))>=100:
            recs.append((cur, ''.join(buf)))
        m=re.search(r'\|([A-Z0-9]+)\|(\S+)', line)
        cur=m.group(1) if m else None; desc=m.group(2) if m else None; buf=[]
    else: buf.append(line.strip())
if cur and desc and re.match(r'HV\d+[A-Z]?_HUMAN$', desc) and len(''.join(buf))>=100:
    recs.append((cur, ''.join(buf)))
if len(recs) < 20: sys.exit(f'FAIL-CLOSED: only {len(recs)} germline VH entries found')
print(f"# germline VH reference set: {len(recs)} human IGHV entries", file=sys.stderr)

def seq_of(cif, ch):
    d = MMCIF2Dict(str(PANEL/f'{cif}.cif'))
    lab, comp = d['_atom_site.label_asym_id'], d['_atom_site.label_comp_id']
    sq, alt = d['_atom_site.label_seq_id'], d['_atom_site.label_alt_id']
    r = OrderedDict()
    for i in range(len(lab)):
        if lab[i] != ch or sq[i] in ('.','?','') or alt[i] not in ('.','?','A'): continue
        r.setdefault(int(sq[i]), comp[i])
    return ''.join(AA3.get(r[n],'X') for n in sorted(r))

LIGHT = {('4lmq','E'),('4lmq','F'),('5XJM','C'),('7B3O','B'),('7qf0','C'),('8r38','B')}
NON_AB = {('5IMK','B')}
uni = json.load(open(OUT/'ig_panel_unified.json'))
accepted = {a['cif']: [c['chain'] for c in a['accepted']] for a in uni['panel_audit'] if 'accepted' in a}

queries=[]
inputs={x['name']:x['sequence'] for x in csv.DictReader(open(OUT/'inputs.csv'))}
queries.append(('c3_glp1r_ecd_12', inputs['c3_glp1r_ecd_12'], 'design'))
queries.append(('6X18_D_Nanobody35', seq_of('6X18','D') if (PANEL/'6X18.cif').exists() else
                None, 'input_antibody'))
if queries[1][1] is None:
    d = MMCIF2Dict(str(ROOT/'data/6x18.cif')); lab,comp=d['_atom_site.label_asym_id'],d['_atom_site.label_comp_id']
    sq,alt=d['_atom_site.label_seq_id'],d['_atom_site.label_alt_id']; r=OrderedDict()
    for i in range(len(lab)):
        if lab[i]!='D' or sq[i] in ('.','?','') or alt[i] not in ('.','?','A'): continue
        r.setdefault(int(sq[i]),comp[i])
    queries[1]=('6X18_D_Nanobody35',''.join(AA3.get(r[n],'X') for n in sorted(r)),'input_antibody')

seen=set()
for cif,chains in sorted(accepted.items()):
    if cif=='6X18': continue
    for ch in chains:
        if (cif,ch) in LIGHT or (cif,ch) in NON_AB: continue
        s=seq_of(cif,ch)
        if len(s)<40 or s in seen: continue   # dedup by sequence
        seen.add(s)
        queries.append((f'{cif}_{ch}', s, 'real_heavy'))
if len([q for q in queries if q[2]=='real_heavy'])<5: sys.exit('FAIL-CLOSED: too few heavy controls')

with tempfile.TemporaryDirectory() as td:
    td=Path(td)
    ref=td/'vh.fasta'
    ref.write_text(''.join(f'>{a}\n{s}\n' for a,s in recs))
    rdb=td/'vhdb'
    subprocess.run([MMSEQS,'createdb',str(ref),str(rdb),'-v','0'],check=True)
    qf=td/'q.fasta'; qf.write_text(''.join(f'>{n}\n{s}\n' for n,s,_ in queries))
    qdb=td/'qdb'; subprocess.run([MMSEQS,'createdb',str(qf),str(qdb),'-v','0'],check=True)
    res=td/'r'
    p=subprocess.run([MMSEQS,'search',str(qdb),str(rdb),str(res),str(td/'tmp'),'-v','0','-s','7.5',
                      '--max-seq-id','1.0','--max-seqs','200'],capture_output=True,text=True)
    if p.returncode!=0: sys.exit(f'FAIL-CLOSED: search failed {p.stderr[:300]}')
    subprocess.run([MMSEQS,'convertalis',str(qdb),str(rdb),str(res),str(td/'r.tsv'),
                    '--format-output','query,target,fident,qcov,alnlen,evalue','-v','0'],check=True)
    lines=[l.rstrip().split('\t') for l in open(td/'r.tsv') if l.strip()]

best={}
for q,t,fid,qcov,aln,ev in lines:
    qc=float(qcov)
    if qc < MIN_QCOV: continue      # Astra's coverage requirement
    d=dict(target=t, fident=float(fid), qcov=qc, alnlen=int(aln), evalue=float(ev))
    if q not in best or d['fident']>best[q]['fident']: best[q]=d

kind={n:k for n,_,k in queries}
real=[best[q] for q in best if kind[q]=='real_heavy']
if not real: sys.exit('FAIL-CLOSED: no real-heavy hits at the coverage floor')
import statistics
real_f=sorted(r['fident'] for r in real)
ecd=best.get('c3_glp1r_ecd_12'); nb=best.get('6X18_D_Nanobody35')
if not ecd: sys.exit('FAIL-CLOSED: ecd_12 has no germline hit at qcov>=0.60')

payload=dict(
  question='Corrected germline-VH comparison for ecd_12 (Astra rejected the first version).',
  withdrawn_previous='The earlier "real antibodies median 0.939 vs ecd_12 0.629" claim is WITHDRAWN: '
    'its hits were to CONSTANT regions (P01834=IGKC, P01857=IGHG1) at qcov~0.45, not germline VH.',
  method=f'mmseqs vs a HUMAN IGHV-GERMLINE-ONLY reference set ({len(recs)} entries, selected by '
         f'UniProt entry name HV*_HUMAN), minimum query coverage {MIN_QCOV}, queries deduplicated',
  n_germline_entries=len(recs), min_qcov=MIN_QCOV,
  ecd12=dict(**{k:(round(v,3) if isinstance(v,float) else v) for k,v in ecd.items()}),
  input_nanobody=(dict(**{k:(round(v,3) if isinstance(v,float) else v) for k,v in nb.items()}) if nb else None),
  real_heavy=dict(n=len(real_f), min=round(real_f[0],3), median=round(statistics.median(real_f),3),
                  max=round(real_f[-1],3), n_ge_ecd=sum(1 for v in real_f if v>=ecd['fident']),
                  percentile_of_ecd=round(100*sum(1 for v in real_f if v<ecd['fident'])/len(real_f),1)),
  per_query=[dict(query=q, kind=kind[q], **{k:(round(v,3) if isinstance(v,float) else v) for k,v in b.items()})
             for q,b in sorted(best.items(), key=lambda kv:-kv[1]['fident'])])
(OUT/'germline_vh_control.json').write_text(json.dumps(payload,indent=1))

print(f"{'query':24s}{'kind':14s}{'target':10s}{'fident':>7s}{'qcov':>7s}")
for r in payload['per_query']:
    print(f"{r['query']:24s}{r['kind']:14s}{r['target']:10s}{r['fident']:7.3f}{r['qcov']:7.3f}")
ra=payload['real_heavy']
print()
print(f"real heavy chains vs germline VH (n={ra['n']}): min {ra['min']} median {ra['median']} max {ra['max']}")
print(f"ecd_12: {ecd['fident']:.3f} qcov {ecd['qcov']:.3f}  -> percentile {ra['percentile_of_ecd']}; "
      f"{ra['n_ge_ecd']}/{ra['n']} real heavy chains score >= ecd_12")
