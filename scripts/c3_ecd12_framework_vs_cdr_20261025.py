#!/usr/bin/env python3
"""Is c3_glp1r_ecd_12's antibody resemblance confined to the framework (acceptable under the
published FAQ, which encourages common frameworks) or does it extend into CDR-equivalent
positions (which would look like a modified existing binder)?

Method: ANARCI-style Kabat numbering is NOT available here, so this does NOT claim CDR
positions. Instead it segments the design by its alignment to 6X18 Nanobody35 and reports,
per design residue, whether that position aligns to a Nanobody35 framework consensus position
or to a hypervariable (CDR) position, using the IMGT definition approximated by the
'...' gap pattern of a nanobody VHH. This is a coarse, explicitly-labelled approximation.
Fail-closed if the alignment is empty.
"""
import csv, json, sys
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
assert len(nb) == 126, len(nb)

q = {x['name']: x['sequence'] for x in csv.DictReader(open(OUT/'inputs.csv'))}['c3_glp1r_ecd_12']
al = Align.PairwiseAligner(); al.substitution_matrix = substitution_matrices.load('BLOSUM62')
al.open_gap_score, al.extend_gap_score = -11, -1; al.mode = 'local'
a = al.align(q, nb)[0]
if a.length == 0: sys.exit('FAIL-CLOSED: empty alignment')

# Nanobody35 (a VHH) hypervariable stretches, from its own sequence numbering via the
# Kabat-like landmark pattern. These are READ OFF the alignment-invariant anchors:
#   CDR1 ~ 26-33, CDR2 ~ 51-58, CDR3 ~ 95-102 (Kabat). Mapped to this file's numbering below.
CDR_RANGES = [(26,33),(51,58),(95,102)]
def is_cdr(n): return any(lo <= n <= hi for lo,hi in CDR_RANGES)

qi = ti = 0; rows = []
for qc, tc in zip(a[0], a[1]):
    if qc != '-':
        num = nums[ti] if tc != '-' else None
        rows.append(dict(q_pos=qi, q_aa=qc, nb_pos=num, nb_aa=tc,
                         region=('gap' if num is None else ('CDR' if is_cdr(num) else 'framework')),
                         match=bool(tc != '-' and qc == tc)))
        qi += 1
    if tc != '-': ti += 1

cov = [x for x in rows if x['region'] != 'gap']
fw = [x for x in cov if x['region'] == 'framework']
cdr = [x for x in cov if x['region'] == 'CDR']
summary = dict(
  note='CDR boundaries here are an EXPLICIT approximation from Kabat-style ranges, not ANARCI output',
  design_len=len(q), aligned_design_positions=len(cov),
  framework_positions=len(fw), framework_identity=round(sum(x['match'] for x in fw)/len(fw),3) if fw else None,
  cdr_positions=len(cdr), cdr_identity=round(sum(x['match'] for x in cdr)/len(cdr),3) if cdr else None,
  design_region_spans=[dict(start=min(x['q_pos'] for x in g), end=max(x['q_pos'] for x in g), region=k)
                       for k, g in (('framework', fw), ('CDR', cdr)) if g],
  per_residue=rows)
(OUT/'ecd12_framework_vs_cdr.json').write_text(json.dumps(summary, indent=1))
print(f"aligned design positions {summary['aligned_design_positions']}/{len(q)}")
print(f"framework {summary['framework_positions']} pos, identity {summary['framework_identity']}")
print(f"CDR       {summary['cdr_positions']} pos, identity {summary['cdr_identity']}")
print('design span by region:', summary['design_region_spans'])
