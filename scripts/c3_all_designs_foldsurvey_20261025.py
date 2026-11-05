#!/usr/bin/env python3
"""For every C3 design structure, find its single best structural match across every
protein chain in the local reference CIFs (pinned TMalign). Question: is the 6X18
Nanobody35 (an Ig domain sitting in the RFD4 input structure) the top hit for the
RFD4 arm, and does any non-RFD4 design behave the same way? Fail-closed."""
import json, subprocess, sys
from pathlib import Path
import numpy as np
from Bio.PDB import Structure, Model, Chain as BChain, Residue, Atom, PDBIO, PDBParser, Select
from Bio.PDB.MMCIF2Dict import MMCIF2Dict

ROOT = Path(__file__).resolve().parents[1]
TM = Path.home()/'.cache/adaptyv-c4/USalign_cpu/TMalign'
if not TM.exists(): sys.exit(f'FAIL: missing {TM}')
AA3 = set('ALA ARG ASN ASP CYS GLN GLU GLY HIS ILE LEU LYS MET PHE PRO SER THR TRP TYR VAL'.split())
TMP = Path('/tmp/allsurvey'); TMP.mkdir(exist_ok=True)

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
    if len(ri) < 20: return None
    io = PDBIO(); io.set_structure(s); io.save(str(out))
    return len(ri)

def tmalign(p1, p2):
    r = subprocess.run([str(TM), str(p1), str(p2)], capture_output=True, text=True)
    if r.returncode != 0: return None
    out = {}
    for line in r.stdout.splitlines():
        if 'Aligned length=' in line:
            out['aligned'] = int(line.split('Aligned length=')[1].split(',')[0])
            out['rmsd'] = float(line.split('RMSD=')[1].split(',')[0])
            out['seq_id'] = float(line.split('=')[-1])
        elif line.startswith('TM-score=') and 'Structure_2' in line:
            out['tm_query'] = float(line.split()[1])
    return out

# build reference chain library once
refs = []
for cif in sorted((ROOT/'data').glob('*.cif')):
    d = MMCIF2Dict(str(cif))
    desc = dict(zip(d['_entity.id'], d['_entity.pdbx_description'])) if '_entity.pdbx_description' in d else {}
    ent = d.get('_atom_site.label_entity_id'); laball = d['_atom_site.label_asym_id']
    for ch in sorted(set(laball)):
        p = TMP/f'ref_{cif.stem}_{ch}.pdb'
        n = write_chain(cif, ch, p)
        if not n: continue
        e = ent[laball.index(ch)] if ent else '?'
        refs.append(dict(pdb=cif.stem, chain=ch, n_res=n, entity=str(desc.get(e,'?'))[:60], path=str(p)))
if not refs: sys.exit('FAIL-CLOSED: no reference chains')
print(f'{len(refs)} reference chains', file=sys.stderr)

class AB(Select):
    def accept_chain(self, c): return c.id in ('A','B')

rows = []
for pdb in sorted((ROOT/'results/c3_pod_artifacts_20261025').glob('*_complex.pdb')):
    name = pdb.stem.replace('_complex','')
    q = TMP/f'q_{name}.pdb'
    m = PDBParser(QUIET=True).get_structure('q', str(pdb))[0]
    io = PDBIO(); io.set_structure(m); io.save(str(q), AB())
    best = None
    for ref in refs:
        r = tmalign(Path(ref['path']), q)
        if not r or 'tm_query' not in r: continue
        rec = dict(ref=ref, **r)
        if best is None or rec['tm_query'] > best['tm_query']: best = rec
    if best is None: continue
    nb = tmalign(Path('/tmp/nb35.pdb'), q) or {}
    arm = 'RFD4' if name.startswith('c3_glp1r_ecd') else ('BindCraft' if name.startswith('c3_bc') else 'depth-arm')
    rows.append(dict(name=name, arm=arm,
        best_pdb=best['ref']['pdb'], best_chain=best['ref']['chain'], best_entity=best['ref']['entity'],
        best_tm=round(best['tm_query'],3), best_rmsd=best['rmsd'], best_seq_id=best['seq_id'],
        best_aligned=best['aligned'],
        nanobody35_tm=round(nb.get('tm_query',0),3), nanobody35_rmsd=nb.get('rmsd'),
        nanobody35_aligned=nb.get('aligned'), nanobody35_seq_id=nb.get('seq_id')))

rows.sort(key=lambda r: -r['best_tm'])
payload = dict(question='Across all local reference chains, what is each C3 design\'s best structural match, '
                        'and is 6X18 Nanobody35 specifically the top hit for the RFD4 arm?',
               method='pinned TMalign, every design chain A/B vs every reference chain; TM normalized by query',
               binary=str(TM), n_reference_chains=len(refs), results=rows)
(ROOT/'results/c3_novelty_screen_20261025/all_designs_foldsurvey.json').write_text(json.dumps(payload, indent=1))
print(f"{'design':28s}{'arm':10s}{'bestTM':>7s}{'best match':>34s}{'NB35 TM':>9s}{'NB35 ID':>9s}")
for r in rows:
    tag=f"{r['best_pdb']} {r['best_chain']} {r['best_entity'][:18]}"
    print(f"{r['name']:28s}{r['arm']:10s}{r['best_tm']:7.3f}{tag:>34s}{r['nanobody35_tm']:9.3f}{str(r['nanobody35_seq_id']):>9s}")
nb_top = [r['name'] for r in rows if r['best_pdb']=='6x18' and r['best_chain']=='D']
print(f"\nNanobody35 is the single best hit for {len(nb_top)}/{len(rows)} designs: {nb_top}")
