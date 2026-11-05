import json, csv, statistics as st

con = json.load(open('results/c4_apical_consolidated_results.json'))
res = con['results']
by = {r['name']: r for r in res}
valid = {n:r for n,r in by.items() if 'error' not in r}
errored = {n:r for n,r in by.items() if 'error' in r}

def names(path):
    with open(path) as f:
        return [row['name'] for row in csv.DictReader(f)]

v9 = names('results/submission_v9.csv')
pv = names('results/c4_rebuild_20261024/submission_v9_preview.csv')

def summ(label, nmlist):
    present=[n for n in nmlist if n in valid]
    missing=[n for n in nmlist if n not in valid]
    rows=[valid[n] for n in present]
    def mean(k): 
        xs=[r[k] for r in rows if isinstance(r.get(k),(int,float))]
        return round(st.mean(xs),4) if xs else None
    iptm_gt5=sum(1 for r in rows if r.get('iptm',0)>0.5)
    pka_gt65=sum(1 for r in rows if (r.get('avg_complex_his_pka') or 0)>6.5)
    print(f'\n== {label} (n={len(nmlist)}) ==')
    print(f'  present in valid pool: {len(present)}; missing/errored: {missing}')
    print(f'  mean iptm={mean("iptm")} ptm={mean("ptm")} confidence={mean("confidence")} complex_plddt={mean("complex_plddt")} avg_his_pka={mean("avg_complex_his_pka")}')
    print(f'  iptm>0.5: {iptm_gt5}/{len(present)}   avg_his_pka>6.5: {pka_gt65}/{len(present)}')
    return present

p9=summ('ORIGINAL submission_v9.csv', v9)
pp=summ('HISTORICAL submission_v9_preview.csv', pv)

inter=set(v9)&set(pv)
print(f'\noverlap v9 ∩ preview: {len(inter)} designs')
print('  shared:', sorted(inter))

# Pool-wide ranking on corrected-apical metrics.
# Composite for acid-OFF: needs real complex (iptm) AND elevated binder-His pKa.
rk=[r for r in valid.values()]
for r in rk:
    r['_pka']=r.get('avg_complex_his_pka') or 0
# Rank separately so we don't over-engineer a single opaque score.
by_iptm=sorted(rk, key=lambda r:-r['iptm'])
by_conf=sorted(rk, key=lambda r:-r['confidence'])
print('\n== POOL (n valid = %d) corrected-apical distribution ==' % len(rk))
ips=sorted(r['iptm'] for r in rk)
print('  iptm   min/med/max: %.3f / %.3f / %.3f ; count>0.5=%d ; count>0.6=%d' % (
    ips[0], ips[len(ips)//2], ips[-1], sum(x>0.5 for x in ips), sum(x>0.6 for x in ips)))
cfs=sorted(r['confidence'] for r in rk)
print('  conf   min/med/max: %.3f / %.3f / %.3f' % (cfs[0], cfs[len(cfs)//2], cfs[-1]))
pks=sorted(r['_pka'] for r in rk)
print('  his_pKa min/med/max: %.2f / %.2f / %.2f ; count>6.5=%d' % (
    pks[0], pks[len(pks)//2], pks[-1], sum(x>6.5 for x in pks)))

# ranks of portfolio members within pool (by iptm)
rankmap={r['name']:i+1 for i,r in enumerate(by_iptm)}
def ranks(nmlist): return sorted(rankmap[n] for n in nmlist if n in rankmap)
print('\nv9 member iptm-ranks within %d pool:' % len(rk), ranks(v9))
print('preview member iptm-ranks within pool:', ranks(pv))

print('\nTop 20 pool by corrected-apical iptm:')
for i,r in enumerate(by_iptm[:20],1):
    tag=[]
    if r['name'] in v9: tag.append('v9')
    if r['name'] in pv: tag.append('prev')
    print(f'  {i:2d} {r["name"]:28s} iptm={r["iptm"]:.3f} conf={r["confidence"]:.3f} pKa={r["_pka"]:.2f} {",".join(tag)}')
