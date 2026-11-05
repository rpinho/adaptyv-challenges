#!/usr/bin/env python3
"""Is ecd_12 SPECIFICALLY closest to 6X18 Nanobody35 (the Ig domain inside the RFD4 input),
or equally close to Ig domains it never saw?

Both advisors asked for this. Panel = 10 non-input Ig V-domains downloaded fresh from RCSB
(8r38, 8dlx, 4lmq, 7qf0, 1ZVH, 5XJM, 6J7W, 7B3O, 6H6K, 5IMK). Reference = 6X18 label chain D.

Reports, per reference chain: TMalign TM (normalized by query), RMSD, seq-ID, aligned length.
Fail-closed if the panel yields no measurable chains."""
import json, subprocess, sys
from pathlib import Path
import numpy as np
from Bio.PDB import Structure, Model, Chain as BChain, Residue, Atom, PDBIO, PDBParser
from Bio.PDB.MMCIF2Dict import MMCIF2Dict

ROOT = Path(__file__).resolve().parents[1]
PANEL = ROOT/'results/c3_novelty_screen_20261025/igpanel'
TM = Path.home()/'.cache/adaptyv-c4/USalign_cpu/TMalign'
if not TM.exists(): sys.exit('FAIL: no TMalign')
AA3 = set('ALA ARG ASN ASP CYS GLN GLU GLY HIS ILE LEU LYS MET PHE PRO SER THR TRP TYR VAL'.split())
TMP = Path('/tmp/igspec'); TMP.mkdir(exist_ok=True)

def write_chain(cif, ch, out):
    d = MMCIF2Dict(str(cif))
    lab, comp, seqid = d['_atom_site.label_asym_id'], d['_atom_site.label_comp_id'], d['_atom_site.label_seq_id']
    alt, atom, el = d['_atom_site.label_alt_id'], d['_atom_site.label_atom_id'], d['_atom_site.type_symbol']
    xs,ys,zs = (np.array(d[k],float) for k in ('_atom_site.Cartn_x','_atom_site.Cartn_y','_atom_site.Cartn_z'))
    s = Structure.Structure('r'); m = Model.Model(0); s.add(m); c = BChain.Chain('A'); m.add(c)
    ri = {}
    for i in range(len(lab)):
        if lab[i] != ch or alt[i] not in ('.','?','A') or seqid[i] in ('.','?',''): continue
        if comp[i] not in AA3: continue
        n = int(seqid[i])
        if n not in ri:
            ri[n] = Residue.Residue((' ',n,' '), comp[i], ''); c.add(ri[n])
        ri[n].add(Atom.Atom(atom[i], np.array([xs[i],ys[i],zs[i]]), 1.0, 0.0, ' ', atom[i], len(ri[n])+1, el[i]))
    if len(ri) < 40: return None
    io = PDBIO(); io.set_structure(s); io.save(str(out))
    return len(ri)

def tm(p1, p2):
    r = subprocess.run([str(TM), str(p1), str(p2)], capture_output=True, text=True)
    if r.returncode != 0: return None
    o = {}
    for line in r.stdout.splitlines():
        if 'Aligned length=' in line:
            o['aligned'] = int(line.split('Aligned length=')[1].split(',')[0])
            o['rmsd'] = float(line.split('RMSD=')[1].split(',')[0])
            o['seq_id'] = float(line.split('=')[-1])
        elif line.startswith('TM-score=') and 'Structure_2' in line:
            o['tm_query'] = float(line.split()[1])
    return o

q = TMP/'design_A.pdb'
m = PDBParser(QUIET=True).get_structure('q', str(ROOT/'results/c3_pod_artifacts_20261025/c3_glp1r_ecd_12_complex.pdb'))[0]
io = PDBIO(); io.set_structure(m)
from Bio.PDB import Select
class Sel(Select):
    def accept_chain(self, c): return c.id == 'A'
io.save(str(q), Sel())

rows = []
# reference: the input Ig domain
ref = tm(Path('/tmp/nb35.pdb'), q)
rows.append(dict(source='6X18 (RF4 INPUT)', chain='D', label='Nanobody35', in_input=True, **(ref or {})))

for cif in sorted(PANEL.glob('*.cif')):
    try: d = MMCIF2Dict(str(cif))
    except Exception as e:
        print('WARN', cif.name, e, file=sys.stderr); continue
    desc = dict(zip(d['_entity.id'], d['_entity.pdbx_description'])) if '_entity.pdbx_description' in d else {}
    ent = d.get('_atom_site.label_entity_id'); laball = d['_atom_site.label_asym_id']
    for ch in sorted(set(laball)):
        p = TMP/f'{cif.stem}_{ch}.pdb'
        try: n = write_chain(cif, ch, p)
        except Exception as e:
            print('WARN', cif.name, ch, e, file=sys.stderr); continue
        if not n: continue
        e_ = ent[laball.index(ch)] if ent else '?'
        lbl = str(desc.get(e_, '?'))
        r = tm(p, q)
        if not r or 'tm_query' not in r: continue
        is_ig = any(k in lbl.lower() for k in ('immunoglobulin','fab','antibody','nanobody','unib','vh ','heavy chain','light chain'))
        rows.append(dict(source=cif.stem, chain=ch, label=lbl[:70], n_res=n, in_input=False, ig_like=is_ig, **r))

ig = [r for r in rows if r.get('in_input') or r.get('ig_like')]
if not ig: sys.exit('FAIL-CLOSED: no Ig chains measured')

def stat(subset):
    tms = sorted((r['tm_query'] for r in subset), reverse=True)
    sids = [r['seq_id'] for r in subset]
    return dict(n=len(subset), tm_max=round(tms[0],3), tm_median=round(float(np.median(tms)),3),
                seqid_max=round(max(sids),3), seqid_median=round(float(np.median(sids)),3))

nb = [r for r in ig if r.get('in_input')]
others = [r for r in ig if not r.get('in_input')]
payload = dict(
  question='Is ecd_12 specifically closer to the input Ig domain than to Ig domains it never saw?',
  method='pinned TMalign; TM normalized by the design (query); Ig panel = 10 RCSB structures '
         'downloaded today, none of which is an RFD4 input',
  reference='6X18 label chain D Nanobody35 (present in the RFD4 input structure)',
  panel=[r['source'] for r in sorted({x['source']: x for x in others}.values(), key=lambda x: x['source'])],
  nanobody35=nb[0] if nb else None,
  other_ig=stat(others), nanobody35_stat=stat(nb),
  ranking=[dict(source=r['source'], chain=r['chain'], tm=r['tm_query'], rmsd=r.get('rmsd'),
                seq_id=r['seq_id'], aligned=r.get('aligned'), label=r.get('label',''),
                in_input=r.get('in_input',False))
           for r in sorted(ig, key=lambda x: -x['tm_query'])],
  verdict=('SPECIFIC' if nb and nb[0]['tm_query'] > max(x['tm_query'] for x in others)
           else 'NOT SPECIFIC — other non-input Ig domains match as well or better'),
)
(ROOT/'results/c3_novelty_screen_20261025/ecd12_ig_specificity.json').write_text(json.dumps(payload, indent=1))

print(f"{'source':18s}{'ch':3s}{'TM(query)':>10s}{'rmsd':>7s}{'seqID':>7s}{'aln':>5s}  label")
for r in payload['ranking'][:14]:
    tag = '  <-- INPUT' if r['in_input'] else ''
    print(f"{r['source']:18s}{r['chain']:3s}{r['tm']:10.3f}{r.get('rmsd',0):7.2f}{r['seq_id']:7.3f}{r.get('aligned',0):5d}  {r.get('label','')[:40]}{tag}")
print()
print('Nanobody35 (input) :', payload['nanobody35_stat'])
print('other Ig (n=%d)    :'%payload['other_ig']['n'], payload['other_ig'])
print('VERDICT:', payload['verdict'])
