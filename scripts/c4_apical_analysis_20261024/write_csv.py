import json, csv, hashlib, os
picked=json.load(open('/tmp/c4anal/picked.json'))
out='results/c4_apical_preview_20261024.csv'
assert not os.path.exists('results/submission_v9.csv.bak'), 'unexpected'
# refuse to touch protected files
for prot in ['results/submission_v9.csv','results/c4_rebuild_20261024/submission_v9_preview.csv']:
    assert os.path.exists(prot), prot
with open(out,'w',newline='') as f:
    w=csv.writer(f)
    w.writerow(['name','sequence','molecule_class'])
    for r in picked:
        assert r['molecule_class']=='single_chain'
        w.writerow([r['name'],r['sequence'],r['molecule_class']])
def sha(p):
    import hashlib
    return hashlib.sha256(open(p,'rb').read()).hexdigest()
print('WROTE', out, 'rows=', len(picked))
print('new preview sha256:', sha(out))
print('v9 sha256         :', sha('results/submission_v9.csv'))
print('old preview sha256:', sha('results/c4_rebuild_20261024/submission_v9_preview.csv'))
# verify row count & uniqueness in new file
rows=list(csv.DictReader(open(out)))
assert len(rows)==20, len(rows)
assert len({r['name'] for r in rows})==20
assert len({r['sequence'] for r in rows})==20
print('integrity: 20 unique names, 20 unique sequences, header OK')
