#!/usr/bin/env python3
"""CORRECTED design baseline. The v1 file (germline_design_baseline.json) has the SAME defect Astra
found in the withdrawn germline_control.json, and I repeated it:

  * it searched ALL of Swiss-Prot with NO coverage floor, so "best hit" could be any protein;
  * its IGV_ACC set was a hand-typed accession list, not a definition, so it was incomplete;
  * concretely, ecd_29's 0.438 "germline" hit A0A0B4J1Y8 is LV949_HUMAN -- a LAMBDA LIGHT-CHAIN
    VARIABLE germline, not an IGHV. That is not a heavy-chain germline comparison.

So v1's headline "no other design hits a germline VH at all" was partly a scoring artifact: ecd_29
DID hit a germline V-region, just a light one, and only relative to an all-Swiss-Prot best-hit.

v2 fixes it exactly as germline_vh_control_20261025.py did:
  * reference = human IGHV germline only, by UniProt entry name HV*_HUMAN (not a typed list);
  * minimum query coverage 0.60 so fragments cannot win;
  * queries = all 44 designs (not 36 -- v1 silently used only designs that produced a hit).
Reports both the IGHV-restricted result and, for transparency, each design's best hit to any
light-chain (LV*_HUMAN/LK*_HUMAN) germline, so the earlier claim is corrected rather than buried.
"""
import csv, json, re, subprocess, sys, tempfile, statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'results/c3_novelty_screen_20261025'
MMSEQS = '/opt/homebrew/bin/mmseqs'
SW = Path.home()/'.cache/adaptyv-c4/novelty/swissprot.fasta'
MIN_QCOV = 0.60
for p in (MMSEQS, SW):
    if not Path(p).exists(): sys.exit(f'FAIL-CLOSED: missing {p}')

def load(pattern, minlen=90):
    cur = None; desc = None; buf = []; recs = []
    for line in open(SW):
        if line.startswith('>'):
            if cur and desc and re.match(pattern, desc) and len(''.join(buf)) >= minlen:
                recs.append((cur, ''.join(buf)))
            m = re.search(r'\|([A-Z0-9]+)\|(\S+)', line)
            cur = m.group(1) if m else None; desc = m.group(2) if m else None; buf = []
        else:
            buf.append(line.strip())
    if cur and desc and re.match(pattern, desc) and len(''.join(buf)) >= minlen:
        recs.append((cur, ''.join(buf)))
    return recs

VH = load(r'HV\d+[A-Z]?_HUMAN$')
VL = load(r'(LV|LK)\d+[A-Z]*_HUMAN$', minlen=80)
if len(VH) < 20: sys.exit(f'FAIL-CLOSED: only {len(VH)} IGHV entries')
if len(VL) < 10: sys.exit(f'FAIL-CLOSED: only {len(VL)} light-chain entries')
print(f"# refs: {len(VH)} human IGHV, {len(VL)} human light-chain V", file=sys.stderr)

designs = [(r['name'], r['sequence']) for r in csv.DictReader(open(OUT/'inputs.csv'))]
if not designs: sys.exit('FAIL-CLOSED: no designs')
print(f"# queries: {len(designs)} designs", file=sys.stderr)

def search(refs, tag):
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        (td/'r.fasta').write_text(''.join(f'>{a}\n{s}\n' for a, s in refs))
        subprocess.run([MMSEQS,'createdb',str(td/'r.fasta'),str(td/'rdb'),'-v','0'],check=True)
        (td/'q.fasta').write_text(''.join(f'>{n}\n{s}\n' for n, s in designs))
        subprocess.run([MMSEQS,'createdb',str(td/'q.fasta'),str(td/'qdb'),'-v','0'],check=True)
        p = subprocess.run([MMSEQS,'search',str(td/'qdb'),str(td/'rdb'),str(td/'res'),str(td/'tmp'),
                            '-v','0','-s','7.5','--max-seq-id','1.0','--max-seqs','200'],
                           capture_output=True,text=True)
        if p.returncode != 0: sys.exit(f'FAIL-CLOSED: {tag} search failed {p.stderr[:300]}')
        subprocess.run([MMSEQS,'convertalis',str(td/'qdb'),str(td/'rdb'),str(td/'res'),str(td/'r.tsv'),
                        '--format-output','query,target,fident,qcov,alnlen,evalue','-v','0'],check=True)
        best = {}
        for l in open(td/'r.tsv'):
            q,t,fid,qcov,aln,ev = l.rstrip('\n').split('\t')
            qc = float(qcov)
            if qc < MIN_QCOV: continue
            d = dict(target=t, fident=float(fid), qcov=qc, alnlen=int(aln), evalue=float(ev))
            if q not in best or d['fident'] > best[q]['fident']: best[q] = d
        return best

vh = search(VH, 'IGHV')
vl = search(VL, 'light-chain')

ecd_name = 'c3_glp1r_ecd_12'
if ecd_name not in vh: sys.exit('FAIL-CLOSED: ecd_12 has no IGHV hit at qcov>=0.60')
if max(d['fident'] for d in vh.values()) < 0.35: sys.exit('FAIL-CLOSED: positive control weak')

def row(name):
    r = vh.get(name)
    l = vl.get(name)
    return dict(name=name,
                vh_target=(r['target'] if r else None),
                vh_fident=(round(r['fident'],3) if r else None),
                vh_qcov=(round(r['qcov'],3) if r else None),
                vl_target=(l['target'] if l else None),
                vl_fident=(round(l['fident'],3) if l else None))

per = sorted((row(n) for n, _ in designs),
             key=lambda x: (x['vh_fident'] if x['vh_fident'] is not None else -1), reverse=True)
vh_vals = [x['vh_fident'] for x in per if x['vh_fident'] is not None]
ecd = next(x for x in per if x['name'] == ecd_name)

payload = dict(
  question='Is ecd_12 unusual among MY OWN designs in IGHV-germline identity? (v2, corrected)',
  supersedes='germline_design_baseline.json (v1)',
  why_v1_wrong=('v1 searched all Swiss-Prot with no coverage floor and used a typed accession list. '
    'ecd_29\'s "germline" hit A0A0B4J1Y8 is LV949_HUMAN, a lambda LIGHT-chain germline, not IGHV. '
    'v1 also restricted queries to the 36 designs that produced any hit, not all 44.'),
  method=f'queries = all {len(designs)} designs; reference = {len(VH)} human IGHV germline entries '
         f'(UniProt name HV*_HUMAN); minimum query coverage {MIN_QCOV}; light-chain germline '
         f'({len(VL)} LV/LK entries) reported separately for transparency',
  n_designs=len(designs), n_vh_refs=len(VH), n_vl_refs=len(VL), min_qcov=MIN_QCOV,
  positive_control=dict(max_design_vh_fident=max(vh_vals), pass_=True),
  ecd12_vh=dict(target=ecd['vh_target'], fident=ecd['vh_fident'], qcov=ecd['vh_qcov'],
                rank_among_designs=sum(1 for v in vh_vals if v > ecd['vh_fident']) + 1,
                n_with_vh_hit=len(vh_vals), n_designs=len(designs)),
  design_vh_fident=dict(n=len(vh_vals), min=round(min(vh_vals),3),
                        median=round(statistics.median(vh_vals),3), max=round(max(vh_vals),3)),
  designs_with_ighv_hit=[x['name'] for x in per if x['vh_fident'] is not None],
  designs_with_lightchain_germline_hit=[dict(name=x['name'], target=x['vl_target'],
                                             fident=x['vl_fident']) for x in per if x['vl_fident'] is not None],
  per_design=per,
)
(OUT/'germline_design_baseline_v2.json').write_text(json.dumps(payload, indent=1))

print(f"{'design':26s}{'VH target':>11s}{'VH id':>8s}{'qcov':>7s}{'VL target':>11s}{'VL id':>8s}")
for x in per[:15]:
    print(f"{x['name']:26s}{str(x['vh_target']):>11s}{('%.3f'%x['vh_fident']) if x['vh_fident'] else '      -':>8s}"
          f"{('%.3f'%x['vh_qcov']) if x['vh_qcov'] else '      -':>7s}{str(x['vl_target']):>11s}"
          f"{('%.3f'%x['vl_fident']) if x['vl_fident'] else '      -':>8s}")
print()
print(f"IGHV hits at qcov>={MIN_QCOV}: {len(vh_vals)}/{len(designs)} designs")
print(f"ecd_12 IGHV: {ecd['vh_fident']:.3f} ({ecd['vh_target']}) rank "
      f"{payload['ecd12_vh']['rank_among_designs']}/{len(vh_vals)} among designs with an IGHV hit")
print(f"light-chain germline hits: {len(payload['designs_with_lightchain_germline_hit'])} designs")
