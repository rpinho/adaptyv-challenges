#!/usr/bin/env python3
"""Is c3_glp1r_ecd_12 an immunoglobulin fold? Sequence-alignment-guided CA superposition
of the design's AF2M model onto 6X18 Nanobody35, with a composition-matched shuffle null and
a TM-score-style normalized score. Fail-closed: refuses to report if no aligned CA pairs."""
import csv, json, random, statistics
from collections import OrderedDict
from pathlib import Path
from Bio.PDB.MMCIF2Dict import MMCIF2Dict
from Bio.PDB import PDBParser
from Bio import Align
from Bio.Align import substitution_matrices
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'results/c3_novelty_screen_20261025'
AA3 = dict(ALA='A',ARG='R',ASN='N',ASP='D',CYS='C',GLN='Q',GLU='E',GLY='G',HIS='H',
           ILE='I',LEU='L',LYS='K',MET='M',PHE='F',PRO='P',SER='S',THR='T',TRP='W',TYR='Y',VAL='V')
d = MMCIF2Dict(str(ROOT/'data/6x18.cif'))
lab, comp, seqid, alt = (d[k] for k in ('_atom_site.label_asym_id','_atom_site.label_comp_id',
                                        '_atom_site.label_seq_id','_atom_site.label_alt_id'))
xs,ys,zs = (np.array(d[k],float) for k in ('_atom_site.Cartn_x','_atom_site.Cartn_y','_atom_site.Cartn_z'))
isCA = [a=='CA' for a in d['_atom_site.label_atom_id']]
res, ca = OrderedDict(), {}
for i in range(len(lab)):
    if lab[i] != 'D' or alt[i] not in ('.','?','A') or seqid[i] in ('.','?',''): continue
    n = int(seqid[i])
    if n not in res:
        res[n] = comp[i]
    if isCA[i]: ca[n] = np.array([xs[i],ys[i],zs[i]])
nums = [n for n in sorted(res) if n in ca]
nbseq = ''.join(AA3.get(res[n],'X') for n in nums)
assert len(nbseq) == len(nums) == 126, (len(nbseq), len(nums))

def design_ca(path, chain):
    m = PDBParser(QUIET=True).get_structure('d', str(path))[0]
    c = m[chain]
    seq, xyz = [], []
    for r in c:
        if r.id[0] != ' ' or r.resname not in AA3: continue
        if 'CA' not in r: continue
        seq.append(AA3[r.resname]); xyz.append(r['CA'].coord)
    return ''.join(seq), np.array(xyz)

def kabsch(P, Q):
    Pc, Qc = P - P.mean(0), Q - Q.mean(0)
    U,S,Vt = np.linalg.svd(Pc.T @ Qc)
    sgn = np.sign(np.linalg.det(Vt.T @ U.T))
    D = np.diag([1.0,1.0,sgn])
    R = Vt.T @ D @ U.T
    dev = np.linalg.norm(Pc @ R.T - Qc, axis=1)
    return R, float(np.sqrt((dev**2).mean())), dev

def tmscore(dev, L_target):
    dn = dev / 3.0
    return float(np.sum(1.0/(1.0 + dn**2)) / L_target)

al = Align.PairwiseAligner()
al.substitution_matrix = substitution_matrices.load('BLOSUM62')
al.open_gap_score, al.extend_gap_score = -11, -1

def aligned_pairs(qseq, tseq, tca):
    al.mode = 'local'
    a = al.align(qseq, tseq)[0]
    qi = ti = 0; pairs = []
    for qc, tc in zip(a[0], a[1]):
        if qc != '-':
            if tc != '-':
                pairs.append((qi, ti))
            qi += 1
        if tc != '-': ti += 1
    return pairs, a

def measure(design_seq, design_xyz, tseq, tca_list, tca):
    pairs, a = aligned_pairs(design_seq, tseq, tca)
    if len(pairs) < 15:
        return dict(n_pairs=len(pairs), status='TOO_FEW_PAIRS', rmsd=None, tm=None)
    P = np.array([design_xyz[i] for i,_ in pairs]); Q = np.array([tca_list[j] for _,j in pairs])
    R, rmsd, dev = kabsch(P, Q)
    ident = sum(1 for q,t in zip(a[0],a[1]) if q==t and q!='-')
    return dict(n_pairs=len(pairs), status='OK', alnlen=int(a.length), score=float(a.score),
                ident=int(ident), ident_frac=round(ident/a.length,4),
                rmsd=round(rmsd,3), tm=tmscore(dev,len(tca_list)),
                frac_under_2A=round(float((dev<2.0).mean()),3),
                frac_under_4A=round(float((dev<4.0).mean()),3),
                frac_under_6A=round(float((dev<6.0).mean()),3))

tca_list = [ca[n] for n in nums]
dseq, dxyz = design_ca(ROOT/'results/c3_pod_artifacts_20261025/c3_glp1r_ecd_12_complex.pdb', 'A')
res_real = measure(dseq, dxyz, nbseq, tca_list, nums)
assert res_real['status'] == 'OK' and res_real['n_pairs'] >= 15, res_real

random.seed(20261025)
null = []
for _ in range(200):
    sh = ''.join(random.sample(dseq, len(dseq)))
    r = measure(sh, dxyz, nbseq, tca_list, nums)
    null.append(r)
ok = [r for r in null if r['status'] == 'OK']
res_null = dict(n=len(null), n_ok=len(ok),
    tm_median=round(statistics.median(r['tm'] for r in ok),3),
    tm_max=round(max(r['tm'] for r in ok),3),
    tm_p99=round(sorted(r['tm'] for r in ok)[int(0.99*len(ok))-1],3),
    n_ge_real=int(sum(1 for r in ok if r['tm'] >= res_real['tm'])),
    rmsd_given_span_median=round(statistics.median(r['rmsd'] for r in ok),3))
res_null['empirical_p'] = round((res_null['n_ge_real']+1)/(len(ok)+1), 4)

# secondary control: same measurement vs GLP-1R chain F (same complex, not an Ig fold)
res, caF = OrderedDict(), {}
for i in range(len(lab)):
    if lab[i] != 'F' or alt[i] not in ('.','?','A') or seqid[i] in ('.','?',''): continue
    n = int(seqid[i])
    if n not in res:
        res[n] = comp[i]
    if isCA[i]: caF[n] = np.array([xs[i],ys[i],zs[i]])
numsF = [n for n in sorted(res) if n in caF]
fseq = ''.join(AA3.get(res[n],'X') for n in numsF)
res_F = measure(dseq, dxyz, fseq, [caF[n] for n in numsF], numsF)

payload = dict(
  question='Is c3_glp1r_ecd_12 an immunoglobulin-like fold resembling 6X18 Nanobody35?',
  method='sequence-alignment-guided Kabsch CA superposition; TM-score normalized by reference length; '
         'null = 200 composition-matched shuffles of the design sequence (same structure)',
  reference='PDB 6X18 label chain D (auth chain N), entity 4 "Nanobody35", 126 aa',
  reference_seq=nbseq, design_seq=dseq, design_len=len(dseq),
  real=res_real, null=res_null,
  negative_control_glp1r_chain_F=res_F,
  interpretation='Ig-fold resemblance is supported only if real TM exceeds the shuffle-null distribution '
                 'and clearly exceeds the non-Ig chain-F control.')
(OUT/'ecd12_fold_vs_nanobody35.json').write_text(json.dumps(payload, indent=1))

print(f"design len {len(dseq)}  pairs {res_real['n_pairs']}  alnlen {res_real['alnlen']}  "
      f"ident {res_real['ident']} ({res_real['ident_frac']:.3f})")
print(f"real   TM {res_real['tm']:.3f}  RMSD {res_real['rmsd']:.2f} A  "
      f"<2A {res_real['frac_under_2A']:.2f}  <4A {res_real['frac_under_4A']:.2f}")
print(f"null   TM median {res_null['tm_median']:.3f}  max {res_null['tm_max']:.3f}  p99 {res_null['tm_p99']:.3f}  "
      f"#>=real {res_null['n_ge_real']}/{res_null['n_ok']}  p={res_null['empirical_p']}")
print(f"ctrl F TM {res_F.get('tm')}  pairs {res_F.get('n_pairs')}")
