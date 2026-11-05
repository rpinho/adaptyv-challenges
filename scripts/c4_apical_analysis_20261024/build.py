import json, csv
con=json.load(open('results/c4_apical_consolidated_results.json'))
valid={r['name']:r for r in con['results'] if 'error' not in r}
for r in valid.values(): r['_pka']=r.get('avg_complex_his_pka') or 0

def kmers(s,k=4): return {s[i:i+k] for i in range(len(s)-k+1)}
def jac(a,b):
    A,B=kmers(a),kmers(b); return len(A&B)/len(A|B) if A|B else 0

# Candidate pool: confident complex on corrected target, then acid-OFF switch priority.
cand=[r for r in valid.values() if r['iptm']>=0.6]
cand.sort(key=lambda r:(-r['_pka'], -r['iptm']))

# Greedy diversity: skip if >=0.6 kmer-Jaccard to an already-picked design.
picked=[]
for r in cand:
    if all(jac(r['sequence'],p['sequence'])<0.6 for p in picked):
        picked.append(r)
    if len(picked)>=20: break

print('Selected %d diverse designs (iptm>=0.6, ranked by His pKa, kmer-Jaccard<0.6):' % len(picked))
s1=sum('site1' in r['name'] for r in picked); s2=len(picked)-s1
print('  site1=%d site2=%d' % (s1,s2))
import statistics as st
print('  mean iptm=%.3f conf=%.3f pKa=%.2f ; pKa range %.2f-%.2f ; iptm range %.2f-%.2f' % (
    st.mean(r['iptm'] for r in picked), st.mean(r['confidence'] for r in picked),
    st.mean(r['_pka'] for r in picked),
    min(r['_pka'] for r in picked), max(r['_pka'] for r in picked),
    min(r['iptm'] for r in picked), max(r['iptm'] for r in picked)))
for i,r in enumerate(picked,1):
    print('  %2d %-28s pKa=%.2f iptm=%.3f conf=%.3f len=%d' % (i,r['name'],r['_pka'],r['iptm'],r['confidence'],len(r['sequence'])))

# overlap with historical portfolios
v9=[row['name'] for row in csv.DictReader(open('results/submission_v9.csv'))]
pv=[row['name'] for row in csv.DictReader(open('results/c4_rebuild_20261024/submission_v9_preview.csv'))]
names=[r['name'] for r in picked]
print('\n  retained from v9:', sorted(set(names)&set(v9)))
print('  retained from preview:', sorted(set(names)&set(pv)))

# write candidate list to json for the CSV writer (not the CSV itself yet)
json.dump([{'name':r['name'],'sequence':r['sequence'],'molecule_class':'single_chain',
            'iptm':r['iptm'],'confidence':r['confidence'],'avg_complex_his_pka':r['_pka']} for r in picked],
          open('/tmp/c4anal/picked.json','w'), indent=2)
