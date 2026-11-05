#!/usr/bin/env python3
"""Is ecd_12's CDR-region identity (0.50) above what an arbitrary sequence gives at the same
aligned positions? Composition-matched shuffle null, 500 draws, using the SAME alignment walk
so the region assignment is identical. Also tests a set of unrelated short helical designs.
Fail-closed if no null draws land in the CDR set."""
import csv, json, random, statistics, sys
from pathlib import Path
from collections import OrderedDict
from Bio.PDB.MMCIF2Dict import MMCIF2Dict
from Bio import Align
from Bio.Align import substitution_matrices

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'results/c3_novelty_screen_20261025'
AA3 = {'ALA':'A','ARG':'R','ASN':'N','ASP':'D','CYS':'C','GLN':'Q','GLU':'E','GLY':'G','HIS':'H',
       'ILE':'I','LEU':'L','LYS':'K','MET':'M','PHE':'F','PRO':'P','SER':'S','THR':'T','TRP':'W',
       'TYR':'Y','VAL':'V'}
d = MMCIF2Dict(str(ROOT/'data/6x18.cif'))
lab = d['_atom_site.label_asym_id']; comp = d['_atom_site.label_comp_id']
sq = d['_atom_site.label_seq_id']; alt = d['_atom_site.label_alt_id']
r = OrderedDict()
for i in range(len(lab)):
    if lab[i] != 'D' or sq[i] in ('.','?','') or alt[i] not in ('.','?','A'): continue
    r.setdefault(int(sq[i]), comp[i])
nums = sorted(r); nb = ''.join(AA3.get(r[n],'X') for n in nums)
CDR_RANGES = [(26,33),(51,58),(95,102)]
def is_cdr(n): return any(lo <= n <= hi for lo,hi in CDR_RANGES)

al = Align.PairwiseAligner(); al.substitution_matrix = substitution_matrices.load('BLOSUM62')
al.open_gap_score, al.extend_gap_score = -11, -1; al.mode = 'local'

def regions(seq):
    a = al.align(seq, nb)[0]
    if a.length == 0: return None
    qi = ti = 0; fw = []; cdr = []
    for qc, tc in zip(a[0], a[1]):
        if qc != '-':
            if tc != '-':
                (cdr if is_cdr(nums[ti]) else fw).append((qi, tc))
            qi += 1
        if tc != '-': ti += 1
    return fw, cdr

seqs = {x['name']: x['sequence'] for x in csv.DictReader(open(OUT/'inputs.csv'))}
target = 'c3_glp1r_ecd_12'
real_fw, real_cdr = regions(seqs[target])
if not real_cdr: sys.exit('FAIL-CLOSED: no CDR positions in real alignment')

def ident(seq, pairs):
    if not pairs: return None
    return sum(1 for i, t in pairs if seq[i] == t) / len(pairs)

random.seed(20261025)
null_fw = []; null_cdr = []
for _ in range(500):
    sh = ''.join(random.sample(seqs[target], len(seqs[target])))
    f, c = regions(sh)
    if not c: continue
    # keep the region assignment from the REAL alignment; only swap the residue identities
    null_fw.append(ident(sh, real_fw)); null_cdr.append(ident(sh, real_cdr))
if not null_cdr: sys.exit('FAIL-CLOSED: zero null CDR draws')

res = dict(
  question='Is ecd_12 CDR-region identity (0.50) distinguishable from an arbitrary sequence at the same positions?',
  real=dict(framework=round(ident(seqs[target], real_fw),3), cdr=round(ident(seqs[target], real_cdr),3),
            n_framework=len(real_fw), n_cdr=len(real_cdr)),
  null=dict(n=len(null_cdr),
            framework_mean=round(statistics.mean(null_fw),3), framework_p95=round(sorted(null_fw)[int(.95*len(null_fw))],3),
            framework_p99=round(sorted(null_fw)[int(.99*len(null_fw))],3),
            framework_max=round(max(null_fw),3),
            cdr_mean=round(statistics.mean(null_cdr),3), cdr_p95=round(sorted(null_cdr)[int(.95*len(null_cdr))],3),
            cdr_p99=round(sorted(null_cdr)[int(.99*len(null_cdr))],3), cdr_max=round(max(null_cdr),3)),
  n_null_ge_real_cdr=int(sum(1 for x in null_cdr if x >= ident(seqs[target], real_cdr))),
  n_null_ge_real_framework=int(sum(1 for x in null_fw if x >= ident(seqs[target], real_fw))))

# control: unrelated designs, same measurement
ctrl = {}
for n in ['c3_bc_l65_8f7b63', 'p1_H8_52_64_910011_sd1', 'c3_glp1r_ecd_14', 'c3_glp1r_ecd_26']:
    f, c = regions(seqs[n])
    if f and c:
        ctrl[n] = dict(framework=round(ident(seqs[n], f),3), cdr=round(ident(seqs[n], c),3),
                       n_framework=len(f), n_cdr=len(c))
res['controls_own_alignment'] = ctrl
res['empirical_p_cdr'] = round((res['n_null_ge_real_cdr']+1)/(len(null_cdr)+1), 4)
res['empirical_p_framework'] = round((res['n_null_ge_real_framework']+1)/(len(null_fw)+1), 4)
(OUT/'ecd12_cdr_null.json').write_text(json.dumps(res, indent=1))

print(json.dumps({k: v for k, v in res.items() if k != 'controls_own_alignment'}, indent=1))
print('\ncontrols (their own best alignment to Nanobody35):')
for k, v in ctrl.items(): print(f'  {k:26s} fw {v["framework"]:.3f} ({v["n_framework"]})  cdr {v["cdr"]:.3f} ({v["n_cdr"]})')
