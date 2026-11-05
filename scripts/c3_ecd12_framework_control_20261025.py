#!/usr/bin/env python3
"""Does ecd_12's 0.633 framework identity DEPEND on Nanobody35 being the input?

The earlier framework_vs_cdr test compared ecd_12 to Nanobody35 only, against COMPOSITION
shuffles of ecd_12. That null answers "is this more identity than chance", NOT "is this more
identity than ecd_12 would show against any other VH". If every VH gives ~0.6 framework
identity to every other VH, then 0.633 carries no information about the input and Astra's
"modified existing binder" reading loses its only sequence-level support.

Method: identical alignment/segmentation code path as c3_ecd12_framework_vs_cdr_20261025.py,
applied to the 18 non-input Ig chains from the unified panel. Reports the SAME quantities, so the
comparison is like-for-like. Fail-closed on empty alignment.
"""
import csv, json, sys
from pathlib import Path
from collections import OrderedDict
from Bio.PDB.MMCIF2Dict import MMCIF2Dict
from Bio import Align
from Bio.Align import substitution_matrices

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'results/c3_novelty_screen_20261025'
PANEL = OUT/'igpanel'
AA3 = {'ALA':'A','ARG':'R','ASN':'N','ASP':'D','CYS':'C','GLN':'Q','GLU':'E','GLY':'G','HIS':'H',
       'ILE':'I','LEU':'L','LYS':'K','MET':'M','PHE':'F','PRO':'P','SER':'S','THR':'T','TRP':'W',
       'TYR':'Y','VAL':'V'}

uni = json.load(open(OUT/'ig_panel_unified.json'))
accepted = {}
for a in uni['panel_audit']:
    if 'accepted' in a:
        accepted[a['cif']] = [c['chain'] for c in a['accepted']]

def seq_of(cif, ch):
    d = MMCIF2Dict(str(PANEL/f'{cif}.cif'))
    lab, comp = d['_atom_site.label_asym_id'], d['_atom_site.label_comp_id']
    sq, alt = d['_atom_site.label_seq_id'], d['_atom_site.label_alt_id']
    r = OrderedDict()
    for i in range(len(lab)):
        if lab[i] != ch or sq[i] in ('.','?','') or alt[i] not in ('.','?','A'): continue
        r.setdefault(int(sq[i]), comp[i])
    return ''.join(AA3.get(r[n],'X') for n in sorted(r))

# reference sequence of the input nanobody (used only for the fixed CDR ranges)
def nb_ref():
    d = MMCIF2Dict(str(ROOT/'data/6x18.cif'))
    lab, comp = d['_atom_site.label_asym_id'], d['_atom_site.label_comp_id']
    sq, alt = d['_atom_site.label_seq_id'], d['_atom_site.label_alt_id']
    r = OrderedDict()
    for i in range(len(lab)):
        if lab[i] != 'D' or sq[i] in ('.','?','') or alt[i] not in ('.','?','A'): continue
        r.setdefault(int(sq[i]), comp[i])
    nums = sorted(r)
    return ''.join(AA3.get(r[n],'X') for n in nums), nums

nb, nums = nb_ref()
q = {x['name']: x['sequence'] for x in csv.DictReader(open(OUT/'inputs.csv'))}['c3_glp1r_ecd_12']

al = Align.PairwiseAligner(); al.substitution_matrix = substitution_matrices.load('BLOSUM62')
al.open_gap_score, al.extend_gap_score = -11, -1; al.mode = 'local'
CDR_RANGES = [(26,33),(51,58),(95,102)]
def is_cdr(n): return any(lo <= n <= hi for lo,hi in CDR_RANGES)

def score(target, target_nums, cdr_gate=True):
    a = al.align(q, target)[0]
    if a.length == 0: return None
    qi = ti = 0; rows = []
    for qc, tc in zip(a[0], a[1]):
        if qc != '-':
            num = target_nums[ti] if tc != '-' else None
            rows.append(dict(q_pos=qi, region=('gap' if num is None else ('CDR' if is_cdr(num) else 'framework')),
                             match=bool(tc != '-' and qc == tc)))
            qi += 1
        if tc != '-': ti += 1
    cov = [x for x in rows if x['region'] != 'gap']
    fw = [x for x in cov if x['region'] == 'framework']
    cd = [x for x in cov if x['region'] == 'CDR']
    return dict(fw_n=0, fw_id=round(sum(x['match'] for x in fw)/len(fw),3) if fw else None,
                cdr_n=len(cd), cdr_id=round(sum(x['match'] for x in cd)/len(cd),3) if cd else None,
                aln_len=a.length)

# Problem: non-input chains have their OWN numbering, so the CDR ranges (defined on Nanobody35)
# do not transfer. Correct control: map each non-input chain ONTO Nanobody35 first (structure of
# the question), i.e. score identity only over the positions that align to the SAME Nanobody35
# region, using the Nanobody35-based position set. Do that by aligning target->nb.
def score_via_nb(target):
    """Score ecd_12 vs `target`, labelling each position by Nanobody35's region.

    DEFECT FIXED (found by Astra, 2026-10-25): the earlier version walked string indices
    from 0, but a LOCAL alignment may start partway through either sequence. That assigned
    residues to the wrong regions whenever the alignment did not start at index 0. This
    version uses Biopython's alignment coordinates, which carry the true offsets.
    """
    at = al.align(target, nb)[0]        # target -> Nanobody35 (gives target idx -> nb idx)
    if at.length == 0: return None
    mp = {int(i): int(j) for i, j in zip(*at.indices) if i >= 0 and j >= 0}
    a2 = al.align(q, target)[0]         # ecd_12 -> target
    if a2.length == 0: return None
    reg = {'framework': [], 'CDR': []}
    for i, j in zip(*a2.indices):
        if i < 0 or j < 0 or int(j) not in mp: continue
        k = mp[int(j)]
        r = 'CDR' if is_cdr(nums[k]) else 'framework'
        reg[r].append(bool(q[i] == target[j]))
    fw, cd = reg['framework'], reg['CDR']
    return dict(fw_n=len(fw), fw_id=round(sum(fw)/len(fw),3) if fw else None,
                cdr_n=len(cd), cdr_id=round(sum(cd)/len(cd),3) if cd else None,
                aln_len=a2.length)

input_score = score_via_nb(nb)
if not input_score: sys.exit('FAIL-CLOSED: input self-alignment empty')

others = []
for cif, chains in sorted(accepted.items()):
    for ch in chains:
        try: s = seq_of(cif, ch)
        except Exception as e:
            print('WARN', cif, ch, e, file=sys.stderr); continue
        if not s or len(s) < 40: continue
        sc = score_via_nb(s)
        if not sc: continue
        others.append(dict(source=cif, chain=ch, length=len(s), seq=s, **sc))
if len(others) < 5: sys.exit('FAIL-CLOSED: too few non-input comparisons')

# DEDUPLICATE BY SEQUENCE (Astra, 2026-10-25): 4lmq E==F and 6J7W A==C are byte-identical chains,
# so counting both inflates n and double-weights one structure. Keep the first of each identical set.
_seen = {}
for o in others:
    _seen.setdefault(o['seq'], []).append(o)
for grp in _seen.values():
    if len(grp) > 1:
        _names = ["%s:%s" % (g["source"], g["chain"]) for g in grp]
        print("# duplicate-sequence group collapsed: %s" % _names, file=sys.stderr)
others = [grp[0] for grp in _seen.values()]
for o in others: o.pop('seq', None)
print(f"# after dedup: n={len(others)} unique sequences", file=sys.stderr)

# LIKE-FOR-LIKE subset: a VHH must be compared to heavy/VHH domains, not to light chains.
LIGHT = {('4lmq','E'),('4lmq','F'),('5XJM','C'),('7B3O','B'),('7qf0','C'),('8r38','B')}
NON_AB = {('5IMK','B')}
heavy = [o for o in others if (o['source'],o['chain']) not in LIGHT and (o['source'],o['chain']) not in NON_AB]
if len(heavy) < 5: sys.exit('FAIL-CLOSED: too few heavy/VHH comparisons')
fw_vals = sorted(o['fw_id'] for o in others if o['fw_id'] is not None)
cd_vals = sorted(o['cdr_id'] for o in others if o['cdr_id'] is not None)
import statistics
payload = dict(
  question='Is ecd_12 framework identity 0.633 SPECIFIC to the input Nanobody35, or is it what any VH gives?',
  why='The earlier finding compared ecd_12 to Nanobody35 only, against composition shuffles of ecd_12. '
      'That does not test specificity. Astra\'s "modified existing binder" reading rests on this number.',
  method='identical BLOSUM62/local alignment and identical Kabat-approx CDR ranges; each non-input chain '
         'is first mapped onto Nanobody35 so the SAME region positions are scored',
  input=dict(source='6X18', chain='D', **input_score),
  n_non_input=len(others),
  non_input=others,
  summary=dict(
    framework=dict(n=len(fw_vals), min=fw_vals[0], median=round(statistics.median(fw_vals),3), max=fw_vals[-1],
                   input=input_score['fw_id'],
                   n_ge_input=sum(1 for v in fw_vals if v >= input_score['fw_id']),
                   percentile_of_input=round(100*sum(1 for v in fw_vals if v < input_score['fw_id'])/len(fw_vals),1)),
    cdr=dict(n=len(cd_vals), min=cd_vals[0], median=round(statistics.median(cd_vals),3), max=cd_vals[-1],
             input=input_score['cdr_id'],
             n_ge_input=sum(1 for v in cd_vals if v >= input_score['cdr_id']),
             percentile_of_input=round(100*sum(1 for v in cd_vals if v < input_score['cdr_id'])/len(cd_vals),1)),
    heavy_only=None))
hf=[o['fw_id'] for o in heavy if o['fw_id'] is not None]
hc=[o['cdr_id'] for o in heavy if o['cdr_id'] is not None]
payload['heavy_only']=dict(
  rule='excludes light chains and non-antibody Ig domains; a VHH must be compared to heavy/VHH domains',
  chains=[f"{o['source']}:{o['chain']}" for o in heavy],
  framework=dict(n=len(hf), min=min(hf), median=round(statistics.median(hf),3), max=max(hf),
                 input=input_score['fw_id'], n_ge_input=sum(1 for v in hf if v>=input_score['fw_id']),
                 percentile=round(100*sum(1 for v in hf if v<input_score['fw_id'])/len(hf),1)),
  cdr=dict(n=len(hc), min=min(hc), median=round(statistics.median(hc),3), max=max(hc),
           input=input_score['cdr_id'], n_ge_input=sum(1 for v in hc if v>=input_score['cdr_id']),
           percentile=round(100*sum(1 for v in hc if v<input_score['cdr_id'])/len(hc),1)))
(OUT/'ecd12_framework_control.json').write_text(json.dumps(payload, indent=1))

print(f"{'source':8s}{'ch':3s}{'len':>5s}{'fw_n':>6s}{'fw_id':>7s}{'cdr_n':>7s}{'cdr_id':>7s}")
print(f"{'6X18':8s}{'D':3s}{len(nb):>5d}{input_score['fw_n']:>6d}{input_score['fw_id']:>7.3f}{input_score['cdr_n']:>7d}{input_score['cdr_id']:>7.3f}  <-- INPUT")
for o in others:
    print(f"{o['source']:8s}{o['chain']:3s}{o['length']:>5d}{o['fw_n']:>6d}{str(o['fw_id']):>7s}{o['cdr_n']:>7d}{str(o['cdr_id']):>7s}")
s = payload['summary']
print()
print('framework identity: input', s['framework']['input'], '| non-input min/median/max',
      s['framework']['min'], s['framework']['median'], s['framework']['max'])
print('  non-input chains >= input:', s['framework']['n_ge_input'], '/', s['framework']['n'])
print('  input percentile among non-input:', s['framework']['percentile_of_input'])
print('CDR identity: input', s['cdr']['input'], '| non-input min/median/max',
      s['cdr']['min'], s['cdr']['median'], s['cdr']['max'])
print('  non-input chains >= input:', s['cdr']['n_ge_input'], '/', s['cdr']['n'])
print('  input percentile among non-input:', s['cdr']['percentile_of_input'])
h = payload['heavy_only']; print()
print('=== LIKE-FOR-LIKE (heavy/VHH only, n=%d) ===' % h['framework']['n'])
print('  framework: input %s | min %s median %s max %s | chains >= input: %d/%d | percentile %.1f' % (
    h['framework']['input'], h['framework']['min'], h['framework']['median'], h['framework']['max'],
    h['framework']['n_ge_input'], h['framework']['n'], h['framework']['percentile']))
print('  CDR      : input %s | min %s median %s max %s | chains >= input: %d/%d | percentile %.1f' % (
    h['cdr']['input'], h['cdr']['min'], h['cdr']['median'], h['cdr']['max'],
    h['cdr']['n_ge_input'], h['cdr']['n'], h['cdr']['percentile']))
