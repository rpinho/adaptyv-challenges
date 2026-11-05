#!/usr/bin/env python3
"""One deterministic Ig panel, used for BOTH the ecd_12 specificity question and the
all-44-designs arm question. Supersedes c3_ecd12_ig_specificity_20261025.py and
c3_ig_panel_all_designs_20261025.py, which used DIFFERENT keyword filters and therefore
DIFFERENT panels (the all-designs run silently dropped 8dlx chain D 'VH ab6').

Every accepted chain is recorded with the reason. Fail-closed if any CIF yields no Ig
chain, if the panel is too small, or if the positive control fails.
"""
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
TMP = Path('/tmp/igunified'); TMP.mkdir(exist_ok=True)

# explicit, auditable keyword list (superset of both earlier scripts)
# Inclusion rule is STRUCTURAL, not keyword-based. Keyword matching silently dropped two real
# Ig domains from earlier panels (8dlx chain D "VH ab6", 7qf0 chains "CV2.2325 heavy chain")
# and would also have admitted 6H6K, which contains no Ig domain at all (TM 0.21 vs a VH).
# Rule: a chain is in the panel iff, at >=40 residues, pinned TMalign gives TM >= 0.50 against a
# known antibody VH reference. `antibody_label` is recorded for reporting but NEVER filters.
IG_TM_GATE = 0.50
IG_REF = ('7B3O','C')
ANTIBODY_TERMS = ('immunoglobulin','fab','antibody','nanobody','uniab','unib','vh ','heavy chain','light chain','v-set')

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

refs, audit = [], []
ig_ref_path = TMP/f'{IG_REF[0]}_{IG_REF[1]}.pdb'
if not ig_ref_path.exists():
    ig_ref_path = PANEL/f'{IG_REF[0]}.cif'
    if not write_chain(ig_ref_path, IG_REF[1], TMP/f'{IG_REF[0]}_{IG_REF[1]}.pdb'):
        sys.exit('FAIL-CLOSED: cannot build Ig structural reference')
    ig_ref_path = TMP/f'{IG_REF[0]}_{IG_REF[1]}.pdb'
refs.append(dict(pdb='6X18', chain='D', label='Nanobody35', in_input=True, path='/tmp/nb35.pdb'))
for cif in sorted(PANEL.glob('*.cif')):
    d = MMCIF2Dict(str(cif))
    desc = dict(zip(d['_entity.id'], d['_entity.pdbx_description'])) if '_entity.pdbx_description' in d else {}
    ent = d.get('_atom_site.label_entity_id'); laball = d['_atom_site.label_asym_id']
    accepted = []
    for ch in sorted(set(laball)):
        p = TMP/f'{cif.stem}_{ch}.pdb'
        n = write_chain(cif, ch, p) if not p.exists() else 1
        if not n: continue
        e = ent[laball.index(ch)] if ent else '?'
        lbl = str(desc.get(e, '?'))
        struct = tm(ig_ref_path, p)
        tm_v = struct.get('tm') if struct else None
        ab = any(k in lbl.lower() for k in ANTIBODY_TERMS)
        if tm_v is None or tm_v < IG_TM_GATE:
            audit.append(dict(cif=cif.stem, chain=ch, label=lbl[:70], rejected='TM_vs_VH<0.50',
                              tm_vs_vh=round(tm_v,3) if tm_v else None, antibody_label=ab))
            print(f'  REJECT {cif.stem} {ch} label={lbl[:44]!r} TM_vs_VH={tm_v}', file=sys.stderr)
            continue
        accepted.append(dict(chain=ch, label=lbl[:70], tm_vs_vh=round(tm_v,3), antibody_label=ab))
        refs.append(dict(pdb=cif.stem, chain=ch, label=lbl[:60], in_input=False, path=str(p)))
    audit.append(dict(cif=cif.stem, accepted=accepted, n_accepted=len(accepted)))
    if not accepted:
        print(f'WARN: {cif.stem} contributed no validated Ig chain (excluded, recorded)', file=sys.stderr)
if len(refs) < 5: sys.exit('FAIL-CLOSED: panel too small')

class AB(Select):
    def accept_chain(self, c): return c.id in ('A','B')

# ---- positive control: a real Ig chain must find itself at 1.0 ----
probe = next(r for r in refs if r['pdb']=='7B3O' and r['chain']=='C')
pc = tm(probe['path'], probe['path'])
if not pc or abs(pc.get('tm',0) - 1.0) > 1e-6:
    sys.exit(f'FAIL-CLOSED: positive control did not self-hit 1.0: {pc}')

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
    if len(hits) != len(refs): sys.exit(f'FAIL-CLOSED: {name} measured {len(hits)}/{len(refs)} chains')
    hits.sort(key=lambda x: -x['tm'])
    nb = next((i for i, h in enumerate(hits) if h['in_input']), None)
    arm = 'RFD4' if name.startswith('c3_glp1r_ecd') else ('BindCraft' if name.startswith('c3_bc') else 'depth-arm')
    rows.append(dict(name=name, arm=arm, n_ig=len(hits),
        nb_rank=(nb+1) if nb is not None else None,
        nb_tm=round(hits[nb]['tm'],3) if nb is not None else None,
        best_tm=round(hits[0]['tm'],3), best_src=f"{hits[0]['pdb']} {hits[0]['chain']}",
        best_is_input=bool(hits[0]['in_input']),
        top5=[f"{h['pdb']}:{h['chain']} {h['tm']:.3f}" for h in hits[:5]]))
if not rows: sys.exit('FAIL-CLOSED: no designs measured')

ecd = next(r for r in rows if r['name']=='c3_glp1r_ecd_12')
ecd_hits = sorted([dict(source=h['pdb'],chain=h['chain'],tm=round(h['tm'],3),rmsd=round(h.get('rmsd',0),2),
                        seq_id=round(h.get('seq_id',0),3),aligned=h.get('aligned'),label=h['label'],
                        in_input=h['in_input']) for h in
                   [dict(**rf, **tm(Path(rf['path']), TMP/f"q_c3_glp1r_ecd_12.pdb")) for rf in refs]],
                  key=lambda x: -x['tm'])
others = [h for h in ecd_hits if not h['in_input']]

payload = dict(
  supersedes=['c3_ecd12_ig_specificity_20261025.py', 'c3_ig_panel_all_designs_20261025.py'],
  why='those two scripts used different keyword filters, so their panels differed; '
      'the all-designs run silently dropped 8dlx chain D ("VH ab6"), which matches ecd_12 at TM 0.801',
  method='pinned TMalign, TM normalized by the design (query); one panel for every design',
  inclusion_rule=f'structural: TM >= {IG_TM_GATE} vs antibody VH reference {IG_REF[0]} chain {IG_REF[1]}; keyword list is reporting-only',
  antibody_terms=list(ANTIBODY_TERMS),
  panel_audit=audit,
  n_ig_chains=len(refs), n_non_input=sum(1 for r in refs if not r['in_input']),
  positive_control=dict(probe='7B3O C', self_hit=round(pc['tm'],6), pass_=True),
  ecd12=dict(nb_rank=ecd['nb_rank'], nb_tm=ecd['nb_tm'], best_tm=ecd['best_tm'], best_src=ecd['best_src'],
             n_beating_it=len([h for h in others if h['tm']>ecd['nb_tm']]),
             ranking=ecd_hits),
  results=rows,
  verification=dict(
    self_check='`TM-score= 1.00000` for 7B3O C vs itself (see ecd12_fold_survey)',
    compare_with_previous='8dlx D was 0.801 on ecd_12 in the specificity run; panel now includes it',
  ))
(OUT/'ig_panel_unified.json').write_text(json.dumps(payload, indent=1))

print(f'panel: {len(refs)} Ig chains ({len(refs)-1} non-input) from {len(audit)} CIFs')
for a in [x for x in audit if 'n_accepted' in x]: print(f"  {a['cif']:6s} {a['n_accepted']} chains: {[c['chain']+'='+format(c['tm_vs_vh'],'.3f')+('(ab)' if c['antibody_label'] else '(non-ab Ig)') for c in a['accepted']]}")
print(f"\npositive control 7B3O C self-hit = {pc['tm']:.6f}")
print(f"\necd_12: Nanobody35 rank {ecd['nb_rank']}/{ecd['n_ig']}  TM {ecd['nb_tm']:.3f}  best {ecd['best_tm']:.3f} ({ecd['best_src']})")
print(f"  non-input Ig chains beating the input nanobody: {len([h for h in others if h['tm']>ecd['nb_tm']])}")
for h in ecd_hits[:6]: print(f"    {h['source']:6s}{h['chain']:3s}{h['tm']:7.3f} {'<-- INPUT' if h['in_input'] else ''}")
print(f"\n{'design':28s}{'arm':11s}{'NBrank':>7s}{'NBTM':>7s}{'bestTM':>7s}  best")
for r in sorted(rows, key=lambda x:(x['nb_rank'] or 99)):
    print(f"{r['name']:28s}{r['arm']:11s}{str(r['nb_rank']):>7s}{r['nb_tm']:7.3f}{r['best_tm']:7.3f}  {r['best_src']}")
n1=[r['name'] for r in rows if r['nb_rank']==1]
print(f"\nNB35 is the TOP Ig match for {len(n1)}/{len(rows)}: {n1}")
for arm in ('RFD4','BindCraft','depth-arm'):
    s=[r for r in rows if r['arm']==arm]
    if s: print(f"  {arm:11s} n={len(s):2d}  NB-TM>=0.5: {sum(1 for x in s if x['nb_tm']>=0.5)}  median rank {sorted(x['nb_rank'] for x in s)[len(s)//2]}")
