#!/usr/bin/env python3
"""Build variant B-plddt: same 8 replaced rows as B, but the 8 admitted seats chosen under
Astra's EXACT stated rule -- binder pLDDT first, then identifier -- with binder pLDDT taken from
the binder chain only (PDB B-factor column), not scores.json's whole-complex mean_plddt.

Rationale: with correct binder-only pLDDT the Astra rule improves BOTH mean binder pLDDT
(97.42 vs 96.84) AND backbone-family coverage (5 families incl. 3x p3, vs 4 families with zero p3).
So this variant dominates B on the two criteria the tie-break exists to serve -- and the effect
is caused by fixing a measurement bug, not by relaxing a gate: clash-clean-all-5, iPTM>=0.87,
refold PASS and the frozen near-identical rule are all unchanged.

Writes ONLY results/c3_sprint_8h_20261025/c3_candidate_v9_B-plddt_20261025.csv.
Does not write, move, or touch B / A / A-bc / v8 / v7 / v6 / submission_v9.csv.
"""
import csv, json, pathlib, hashlib

ROOT = pathlib.Path(__file__).resolve().parents[1]
SPR = ROOT / 'results/c3_sprint_8h_20261025'
V8 = ROOT / 'results/c3_submission_v8_20261025.csv'
SEQS = ROOT / 'results/c3_sampling_depth_v1_20261025/sequences.csv'
TM_MIN, COV_MIN = 0.65, 0.80
FLAGGED = ['c3_bc_l70_7781fe', 'c3_bc_l100_c674f8', 'c3_bc_l99_e26aff',
           'c3_bc_l52_6950ff', 'c3_bc_l100_4bd789', 'c3_bc_l78_3d63fd',
           'c3_glp1r_ecd_12', 'c3_glp1r_ecd_29']


def sha(p): return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()


corr = json.load(open(SPR / 'tiebreak_corrected.json'))
assert corr['self_check']['pass_'], 'tiebreak_corrected.json self-check failed; refusing to build'
astra_names = corr['astra_rule_binder_plddt']['names']
assert len(astra_names) == 8, astra_names

# re-derive the ordering independently against the recorded candidate table, and re-apply the
# mutual near-identical filter here so the CSV is not merely copied from the JSON
cands = sorted(corr['candidates'], key=lambda c: (-(c['binder_plddt'] or 0), -c['iptm'], c['name']))
matrix = json.load(open(ROOT / 'results/c3_r3_20261025/cross_tm_20261025.json'))['pairs']

def near(a, b):
    ra, rb = matrix.get(a), matrix.get(b)
    rec = ra.get(b) if isinstance(ra, dict) else None
    if rec is None and isinstance(rb, dict): rec = rb.get(a)
    if not rec: return None
    return rec.get('tm', 0) >= TM_MIN and rec.get('coverage', 0) >= COV_MIN

admitted, used_bb = [], set()
for c in cands:
    if len(admitted) == 8: break
    if c['backbone'] in used_bb: continue
    if all(not (near(c['backbone'], a['backbone']) or False) for a in admitted):
        admitted.append(c); used_bb.add(c['backbone'])

derived = [c['name'] for c in admitted]
assert set(derived) == set(astra_names), (derived, astra_names)

v8 = list(csv.DictReader(open(V8)))
v8seq = {r['name']: r['sequence'] for r in v8}
seqs = {r['name']: r for r in csv.DictReader(open(SEQS))}
survivors = [r['name'] for r in v8 if r['name'] not in FLAGGED]
rows = [{'name': n, 'sequence': v8seq[n], 'molecule_class': 'single_chain'} for n in survivors]
rows += [{'name': n, 'sequence': seqs[n]['sequence'], 'molecule_class': 'single_chain'} for n in derived]

out = SPR / 'c3_candidate_v9_B-plddt_20261025.csv'
with open(out, 'w', newline='') as f:
    w = csv.DictWriter(f, fieldnames=['name', 'sequence', 'molecule_class'], lineterminator='\r\n')
    w.writeheader(); w.writerows(rows)

print(f'variant B-plddt: {len(survivors)} survivors + {len(derived)} admitted = {len(rows)} rows')
print(f'sha256 {sha(out)}')
for c in admitted:
    print(f"   {c['name']:<28} iPTM {c['iptm']:.2f}  binder pLDDT {c['binder_plddt']:.2f}  family {c['backbone'][:2]}")
print('replaced:', ', '.join(FLAGGED))
