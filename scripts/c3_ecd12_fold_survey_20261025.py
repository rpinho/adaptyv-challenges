#!/usr/bin/env python3
"""Survey c3_glp1r_ecd_12's AF2M model against every protein chain in the local
reference structures, using the pinned TMalign binary. Purpose: decide whether the
6X18 Nanobody35 Ig-domain match (TM 0.813) is a specific scaffold relationship or
generic immunoglobulin-fold convergence. Fail-closed on missing binary/reference."""
import json, subprocess, sys
from pathlib import Path
import numpy as np
from Bio.PDB import Structure, Model, Chain as BChain, Residue, Atom, PDBIO, PDBParser
from Bio.PDB.MMCIF2Dict import MMCIF2Dict

ROOT = Path(__file__).resolve().parents[1]
TM = Path.home()/'.cache/adaptyv-c4/USalign_cpu/TMalign'
if not TM.exists(): sys.exit(f'FAIL: missing {TM}')
DESIGN = ROOT/'results/c3_pod_artifacts_20261025/c3_glp1r_ecd_12_complex.pdb'
AA3 = set('ALA ARG ASN ASP CYS GLN GLU GLY HIS ILE LEU LYS MET PHE PRO SER THR TRP TYR VAL'.split())

def write_chain(cif, label_chain, out):
    d = MMCIF2Dict(str(cif))
    lab, comp, seqid = d['_atom_site.label_asym_id'], d['_atom_site.label_comp_id'], d['_atom_site.label_seq_id']
    alt, atom = d['_atom_site.label_alt_id'], d['_atom_site.label_atom_id']
    el = d['_atom_site.type_symbol']
    xs,ys,zs = (np.array(d[k],float) for k in ('_atom_site.Cartn_x','_atom_site.Cartn_y','_atom_site.Cartn_z'))
    s = Structure.Structure('r'); m = Model.Model(0); s.add(m); c = BChain.Chain('A'); m.add(c)
    ri = {}
    for i in range(len(lab)):
        if lab[i] != label_chain or alt[i] not in ('.','?','A') or seqid[i] in ('.','?',''): continue
        if comp[i] not in AA3: continue
        n = int(seqid[i])
        if n not in ri:
            ri[n] = Residue.Residue((' ',n,' '), comp[i], ''); c.add(ri[n])
        ri[n].add(Atom.Atom(atom[i], np.array([xs[i],ys[i],zs[i]]), 1.0, 0.0, ' ', atom[i], len(ri[n])+1, el[i]))
    if len(ri) < 20: return None
    io = PDBIO(); io.set_structure(s); io.save(str(out))
    return ''.join(r.resname for r in c)

def tmalign(p1, p2):
    r = subprocess.run([str(TM), str(p1), str(p2)], capture_output=True, text=True)
    if r.returncode != 0: return None
    out = {'raw': r.stdout}
    for line in r.stdout.splitlines():
        if 'Aligned length=' in line:
            out['aligned_length'] = int(line.split('Aligned length=')[1].split(',')[0])
            out['rmsd'] = float(line.split('RMSD=')[1].split(',')[0])
            out['seq_id'] = float(line.split('=')[-1])
        elif line.startswith('TM-score=') and 'normalized by length of Structure_2' in line:
            out['tm_norm_by_query'] = float(line.split()[1])
        elif line.startswith('TM-score=') and 'normalized by length of Structure_1' in line:
            out['tm_norm_by_ref'] = float(line.split()[1])
    return out

# design chain A
tmp = Path('/tmp/foldsurvey'); tmp.mkdir(exist_ok=True)
m = PDBParser(QUIET=True).get_structure('d', str(DESIGN))[0]
io = PDBIO(); io.set_structure(m)
from Bio.PDB import Select
class Sel(Select):
    def accept_chain(self, c): return c.id == 'A'
io.save(str(tmp/'design_A.pdb'), Sel())

rows = []
for cif in sorted((ROOT/'data').glob('*.cif')):
    try: d = MMCIF2Dict(str(cif))
    except Exception: continue
    desc = {}
    if '_entity.id' in d and '_entity.pdbx_description' in d:
        desc = dict(zip(d['_entity.id'], d['_entity.pdbx_description']))
    ent = d.get('_atom_site.label_entity_id')
    for ch in sorted(set(d['_atom_site.label_asym_id'])):
        p = tmp/f'{cif.stem}_{ch}.pdb'
        try: seq = write_chain(cif, ch, p)
        except Exception as exc:
            print(f'WARN {cif.name} {ch}: {exc}', file=sys.stderr); continue
        if not seq: continue
        r = tmalign(p, tmp/'design_A.pdb')
        if not r or 'tm_norm_by_ref' not in r: continue
        e = ent[d['_atom_site.label_asym_id'].index(ch)] if ent else '?'
        rows.append(dict(pdb=cif.stem, chain=ch, entity=desc.get(e,'?'), n_res=len(seq),
                         aligned=r['aligned_length'], rmsd=r['rmsd'], seq_id=r['seq_id'],
                         tm_ref=r['tm_norm_by_ref'], tm_query=r.get('tm_norm_by_query')))
rows.sort(key=lambda x: -x['tm_ref'])
if not rows: sys.exit('FAIL-CLOSED: zero chains measured; refusing to report')
payload = dict(question='Is the c3_glp1r_ecd_12 <-> 6X18 Nanobody35 match specific or generic Ig-fold convergence?',
               method='pinned TMalign over every protein chain of every local reference CIF',
               binary=str(TM), design=str(DESIGN), results=rows)
(ROOT/'results/c3_novelty_screen_20261025/ecd12_fold_survey.json').write_text(json.dumps(payload, indent=1))
print(f"{'pdb':7s}{'ch':3s}{'n':>5s}{'aln':>5s}{'rmsd':>7s}{'seqID':>7s}{'TMref':>7s}  entity")
for r in rows[:15]:
    print(f"{r['pdb']:7s}{r['chain']:3s}{r['n_res']:5d}{r['aligned']:5d}{r['rmsd']:7.2f}{r['seq_id']:7.3f}{r['tm_ref']:7.3f}  {str(r['entity'])[:44]}")
print(f"\n{len(rows)} chains surveyed; best TM {rows[0]['tm_ref']:.3f} ({rows[0]['pdb']} {rows[0]['chain']})")
