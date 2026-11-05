#!/usr/bin/env python3
"""The control that decides whether ecd_12's germline resemblance is DISTINCTIVE AMONG MY DESIGNS.

The 'real antibody' control showed ecd_12 (0.629) is the LOWEST of 18 real antibodies, i.e. it is not
a near-copy of a known germline VH. But that does not answer the competition-relevant question: is
ecd_12 unusual COMPARED TO THE OTHER DESIGNS? A de novo 83-aa protein scoring 0.63 to IGHV is high;
if all 43 other designs score ~0.2-0.3, ecd_12 is genuinely an outlier among my own output.

Method: same mmseqs DB/params. Queries = all 44 designs (the 5 candidates + the rest of the pod
artifacts' sequences) plus the 18 real antibodies as the reference distribution. Reports each design's
best swissprot fident, and specifically its best hit to an IGHV/IGKV germline family entry.
Fail-closed if the design set is empty or the positive control fails.
"""
import json, subprocess, sys, tempfile, csv, re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT/'results/c3_novelty_screen_20261025'
MM = OUT/'mm'
MMSEQS = '/opt/homebrew/bin/mmseqs'
if not (MM/'sp').exists(): sys.exit('FAIL-CLOSED: swissprot DB missing')

rows = list(csv.DictReader(open(OUT/'inputs.csv')))
designs = [(r['name'], r['sequence']) for r in rows]
if not designs: sys.exit('FAIL-CLOSED: no designs')

germ = json.load(open(OUT/'germline_control.json'))
real = [(q['query'], None) for q in germ['per_query'] if q['kind'] == 'real_antibody']

with tempfile.TemporaryDirectory() as td:
    td = Path(td)
    fa = td/'d.fasta'
    fa.write_text(''.join(f'>{n}\n{s}\n' for n, s in designs))
    qdb = td/'qdb'
    subprocess.run([MMSEQS, 'createdb', str(fa), str(qdb), '-v', '0'], check=True)
    res = td/'r.m8'
    p = subprocess.run([MMSEQS, 'search', str(qdb), str(MM/'sp'), str(res), str(td/'tmp'), '-v', '0',
                        '-s', '7.5', '--max-seq-id', '1.0'], capture_output=True, text=True)
    if p.returncode != 0: sys.exit(f'FAIL-CLOSED: search failed {p.stderr[:300]}')
    subprocess.run([MMSEQS, 'convertalis', str(qdb), str(MM/'sp'), str(res), str(td/'r.tsv'),
                    '--format-output', 'query,target,fident,qcov,tcov,evalue,bits', '-v', '0'], check=True)
    lines = [l.rstrip('\n').split('\t') for l in open(td/'r.tsv') if l.strip()]

best, best_ig = {}, {}
# IGHV/IGKV/IGLV germline families in swissprot are named P0xxxx; use the accession set observed
# in the ecd_12 screen plus the canonical human IGHV set recorded in FINDING.md.
IGV_ACC = {'P01767','P01821','P01763','P01764','P01772','P01768','P01825','P01824','P01822','P01820',
           'P01819','P01823','P01817','P01814','P01780','P01782','P01781','P06331','P0DP04','P0DP02',
           'P0DP06','P0DP08','A0A0C4DH41','A0A0C4DH42','A0A0B4J1X8','A0A0B4J1X5','A0A075B6R2'}
for q, t, fid, qcov, tcov, ev, bits in lines:
    f = float(fid)
    d = dict(target=t, fident=f, qcov=float(qcov), evalue=float(ev))
    if q not in best or f > best[q]['fident']: best[q] = d
    if t in IGV_ACC and (q not in best_ig or f > best_ig[q]['fident']): best_ig[q] = d

if not best: sys.exit('FAIL-CLOSED: no hits')
# A design with NO hit at all is a real, informative outcome (identity below the search floor).
# Record it explicitly instead of letting a KeyError look like a bug.
missing = [n for n, _ in designs if n not in best]
for n in missing:
    best[n] = dict(target=None, fident=0.0, qcov=0.0, evalue=None, no_hit=True)
pos = max(b['fident'] for b in best.values())
if pos < 0.35: sys.exit(f'FAIL-CLOSED: positive control weak (max design fident {pos:.3f})')

vals = sorted((best[n]['fident'], n) for n, _ in designs)
import statistics
ecd = best.get('c3_glp1r_ecd_12')
payload = dict(
  question='Is ecd_12 unusual among MY OWN 44 designs in germline-VH identity, as well as among real antibodies?',
  method='same mmseqs DB/params as the novelty screen; queries = 44 designs; reference = 18 real antibodies',
  positive_control=dict(max_design_fident=round(pos,3), pass_=True),
  design_fident=dict(n=len(vals), min=round(vals[0][0],3), median=round(statistics.median(v for v,_ in vals),3),
                     max=round(vals[-1][0],3), max_design=vals[-1][1]),
  ecd12=dict(fident=round(ecd['fident'],3), target=ecd['target'], qcov=round(ecd['qcov'],3),
             rank_among_designs=sum(1 for v,_ in vals if v > ecd['fident'])+1,
             n_designs=len(vals),
             percentile=round(100*sum(1 for v,_ in vals if v < ecd['fident'])/len(vals),1)),
  real_antibody_reference=germ['real_antibodies'],
  designs_with_no_hit=missing,
  per_design=[dict(name=n, fident=round(best[n]['fident'],3), target=best[n]['target'],
                   qcov=round(best[n]['qcov'],3),
                   igv_target=(best_ig[n]['target'] if n in best_ig else None),
                   no_hit=bool(best[n].get('no_hit')),
                   igv_fident=(round(best_ig[n]['fident'],3) if n in best_ig else None))
              for n, _ in sorted(designs, key=lambda x: -best[x[0]]['fident'])])
(OUT/'germline_design_baseline.json').write_text(json.dumps(payload, indent=1))

print(f"{'design':26s}{'best':>7s}{'qcov':>6s}{'target':>10s}{'IGV':>6s}{'igv_t':>10s}")
for r in payload['per_design'][:15]:
    print(f"{r['name']:26s}{r['fident']:7.3f}{r['qcov']:6.3f}{str(r['target']):>10s}{str(r['igv_fident']):>6s}{str(r['igv_target']):>10s}")
print()
print('design fident distribution: min %.3f median %.3f max %.3f (%s)' % (
    payload['design_fident']['min'], payload['design_fident']['median'],
    payload['design_fident']['max'], payload['design_fident']['max_design']))
print('ecd_12: %.3f -> rank %d/%d, percentile %.1f' % (
    ecd['fident'], payload['ecd12']['rank_among_designs'], len(vals), payload['ecd12']['percentile']))
print('real antibody median for comparison: %.3f' % germ['real_antibodies']['median'])
