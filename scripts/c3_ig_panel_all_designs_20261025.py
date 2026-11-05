#!/usr/bin/env python3
"""Re-do the arm-level 'does the RFD4 arm land on its own input Ig domain?' question using a
BALANCED Ig panel instead of whatever Ig happened to be in the local 63-chain library.

The earlier survey's 63 chains contained essentially ONE immunoglobulin V-domain (6X18 chain D).
Kimi's objection: best-among-63 is not the same as specifically-closest-to-Nanobody35 among Ig
domains generally. This script fixes that: reference = 6X18 D, plus 16 non-input Ig chains from
10 freshly downloaded RCSB structures. Reports, per design, Nanobody35's RANK among Ig chains.

Fail-closed if the panel is empty."""
import json, subprocess, sys
from pathlib import Path
import numpy as np
from Bio.PDB import Structure, Model, Chain as BChain, Residue, Atom, PDBIO, PDBParser, Select
from Bio.PDB.MMCIF2Dict import MMCIF2Dict

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'results/c3_novelty_screen_20261025'
PANEL = OUT/'igpanel'
TM = Path.home()/'.cache/adaptyv-c4/USalign_cpu/TMalign'
if not TM.exists(): sys.exit('FAIL: no TMalign')
AA3 = set('ALA ARG ASN ASP CYS GLN GLU GLY HIS ILE LEU LYS MET PHE PRO SER THR TRP TYR VAL'.split())
TMP = Path('/tmp/igpanelall'); TMP.mkdir(exist_ok=True)

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
            o['tm'] = float(line.split()[1])
    return o

# build the Ig reference set once
refs = []
nbpath = Path('/tmp/nb35.pdb')
if not nbpath.exists(): sys.exit('FAIL: /tmp/nb35.pdb missing — rerun c3_ecd12_fold_survey_20261025.py')
refs.append(dict(pdb='6X18', chain='D', label='Nanobody35', in_input=True, path=str(nbpath)))
for cif in sorted(PANEL.glob('*.cif')):
    d = MMCIF2Dict(str(cif))
    desc = dict(zip(d['_entity.id'], d['_entity.pdbx_description'])) if '_entity.pdbx_description' in d else {}
    ent = d.get('_atom_site.label_entity_id'); laball = d['_atom_site.label_asym_id']
    for ch in sorted(set(laball)):
        p = TMP/f'{cif.stem}_{ch}.pdb'
        if not p.exists():
            n = write_chain(cif, ch, p)
            if not n: continue
        else:
            n = 1
        e = ent[laball.index(ch)] if ent else '?'
        lbl = str(desc.get(e, '?'))
        if not any(k in lbl.lower() for k in ('immunoglobulin','fab','antibody','nanobody','unib','heavy chain','light chain')):
            continue
        refs.append(dict(pdb=cif.stem, chain=ch, label=lbl[:60], in_input=False, path=str(p)))
print(f'{len(refs)} Ig reference chains ({sum(1 for r in refs if not r["in_input"])} non-input)', file=sys.stderr)
if len(refs) < 4: sys.exit('FAIL-CLOSED: Ig panel too small')

class AB(Select):
    def accept_chain(self, c): return c.id in ('A','B')

rows = []
for pdb in sorted((ROOT/'results/c3_pod_artifacts_20261025').glob('*_complex.pdb')):
    name = pdb.stem.replace('_complex','')
    q = TMP/f'q_{name}.pdb'
    if not q.exists():
        m = PDBParser(QUIET=True).get_structure('q', str(pdb))[0]
        io = PDBIO(); io.set_structure(m); io.save(str(q), AB())
    hits = []
    for ref in refs:
        r = tm(Path(ref['path']), q)
        if not r or 'tm' not in r: continue
        hits.append(dict(**ref, **r))
    if not hits: continue
    hits.sort(key=lambda x: -x['tm'])
    nb = next((i for i, h in enumerate(hits) if h['in_input']), None)
    arm = 'RFD4' if name.startswith('c3_glp1r_ecd') else ('BindCraft' if name.startswith('c3_bc') else 'depth-arm')
    rows.append(dict(name=name, arm=arm, n_ig_chains=len(hits),
        nb_rank=(nb+1) if nb is not None else None,
        nb_tm=round(hits[nb]['tm'],3) if nb is not None else None,
        best_tm=round(hits[0]['tm'],3), best_src=f"{hits[0]['pdb']} {hits[0]['chain']}",
        best_is_input=bool(hits[0]['in_input']),
        top3=[f"{h['pdb']}:{h['chain']} {h['tm']:.3f}" for h in hits[:3]]))

if not rows: sys.exit('FAIL-CLOSED: no designs measured')
payload = dict(
  question='Using a balanced Ig panel, is 6X18 Nanobody35 (the RFD4 input Ig domain) a privileged match '
           'for any design — in particular for the RFD4 arm?',
  why='The earlier 63-chain local survey contained essentially ONE Ig V-domain, so "best among 63" '
      'could not distinguish an input pull from generic Ig-fold output. Kimi raised exactly this.',
  method='pinned TMalign, TM normalized by query, design chain A/B vs 17 Ig reference chains',
  n_ig_chains=len(refs), n_non_input=sum(1 for r in refs if not r['in_input']),
  panel=sorted({r['pdb'] for r in refs if not r['in_input']}),
  results=rows)
(OUT/'ig_panel_all_designs.json').write_text(json.dumps(payload, indent=1))

print(f"\n{'design':28s}{'arm':10s}{'NB rank':>8s}{'NB TM':>7s}{'bestTM':>7s}  best")
for r in sorted(rows, key=lambda x: (x['nb_rank'] or 99)):
    print(f"{r['name']:28s}{r['arm']:10s}{str(r['nb_rank']):>8s}{r['nb_tm']:7.3f}{r['best_tm']:7.3f}  {r['best_src']}")
n1 = [r['name'] for r in rows if r['nb_rank'] == 1]
print(f"\nNanobody35 is the TOP Ig match for {len(n1)}/{len(rows)} designs: {n1}")
for arm in ('RFD4','BindCraft','depth-arm'):
    sub = [r for r in rows if r['arm'] == arm]
    if sub:
        print(f"  {arm:10s} n={len(sub):2d}  median NB rank {sorted(x['nb_rank'] for x in sub)[len(sub)//2]}")
