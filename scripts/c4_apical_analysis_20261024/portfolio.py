import json, csv
con=json.load(open('results/c4_apical_consolidated_results.json'))
valid={r['name']:r for r in con['results'] if 'error' not in r}
for r in valid.values(): r['_pka']=r.get('avg_complex_his_pka') or 0

# Acid-OFF needs BOTH: plausible complex (iptm) AND elevated binder-His pKa (pH switch).
# Show designs with elevated pKa, their iptm/conf.
elev=sorted([r for r in valid.values() if r['_pka']>6.5], key=lambda r:-r['_pka'])
print('=== %d designs with avg binder-His pKa > 6.5 (acid-OFF switch signal) ===' % len(elev))
print('  name / pKa / n_elev / iptm / conf / len')
for r in elev:
    print('  %-28s pKa=%.2f n=%d iptm=%.3f conf=%.3f len=%d' % (
        r['name'], r['_pka'], r.get('n_elevated_complex',0), r['iptm'], r['confidence'], len(r['sequence'])))

# Composite: require iptm>=0.6 (clearly-formed complex on corrected target) AND rank by pKa.
cand=[r for r in valid.values() if r['iptm']>=0.6]
cand.sort(key=lambda r:(-r['_pka'], -r['iptm']))
print('\n=== iptm>=0.6 AND highest pKa (functional acid-OFF + confident complex), top 25 ===')
for i,r in enumerate(cand[:25],1):
    site='site1' if 'site1' in r['name'] else 'site2'
    print('  %2d %-28s pKa=%.2f iptm=%.3f conf=%.3f %s' % (i,r['name'],r['_pka'],r['iptm'],r['confidence'],site))
print('\n  total with iptm>=0.6: %d ; of those pKa>6.0: %d ; pKa>6.5: %d' % (
    len(cand), sum(r['_pka']>6.0 for r in cand), sum(r['_pka']>6.5 for r in cand)))
