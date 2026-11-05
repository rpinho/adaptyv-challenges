#!/usr/bin/env python3
"""Diversity inventory appendix for R3 (Astra 2026-10-25 02:41, item 3).

Definition fixed by Astra, implemented verbatim:
  under-represented relative to v8 = a measured, crosswalked component containing ZERO v8 members,
  split into (a) components with a prior R1/R2 member and (b) components with no prior member.
Raw occupancy is reported by UNIQUE BACKBONE and separately by sequence count; no "crowded"
cutoff is introduced, and zero occupancy is explicitly NOT functional novelty.
Any design whose component is unknown is reported UNKNOWN, never guessed.

Read-only. Writes results/c3_r3_diversity_20261025.md.
"""
import collections, csv, hashlib, json, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
R3 = ROOT / 'results/c3_r3_20261025'
OUT = ROOT / 'results/c3_r3_diversity_20261025.md'
V8 = ROOT / 'results/c3_submission_v8_20261025.csv'


def main():
    for p in (R3 / 'cross_tm_20261025.json', R3 / 'report_20261025.json', V8):
        if not p.exists():
            print('DIVERSITY FAIL missing', p, file=sys.stderr)
            return 4
    cross = json.loads((R3 / 'cross_tm_20261025.json').read_text())
    rep = json.loads((R3 / 'report_20261025.json').read_text())
    v8 = list(csv.DictReader(open(V8)))

    r3_bb = cross['round3_clusters']                     # R3 backbone -> X label
    prior_labels = set(cross['round1_clusters'].values()) | \
        set(cross['round2_clusters'].values())
    for members in cross.get('merged_prior_labels', {}).values():
        prior_labels |= set(members)

    v8_labels = {}
    unknown = []
    for r in v8:
        n = r['name']
        lab = cross['round1_clusters'].get(n) or cross['round2_clusters'].get(n)
        v8_labels[n] = lab
        if lab is None:
            unknown.append(n)
    v8_comp = {l for l in v8_labels.values() if l}

    bbs = collections.defaultdict(set)
    for bb, lab in r3_bb.items():
        bbs[lab].add(bb)
    seqs = collections.Counter()
    for n in rep['overall']['eligible_designs']:
        bb = n.rsplit('_s', 1)[0]
        lab = r3_bb.get(bb)
        if lab:
            seqs[lab] += 1
    zero_v8 = sorted((l for l in bbs if l not in v8_comp),
                     key=lambda l: (-len(bbs[l]), l))
    withprior = [l for l in zero_v8 if l in prior_labels]
    noprior = [l for l in zero_v8 if l not in prior_labels]

    L = []
    A = L.append
    A('# R3 diversity inventory (appendix to the promotion-readiness dossier)')
    A('')
    A('Read-only. Definitions fixed by Astra 2026-10-25 02:41; no threshold is invented here.')
    A('')
    A('> "Under-represented relative to v8" = a measured, crosswalked component containing **zero** '
      'v8 members. Raw occupancy is reported by **unique backbone** and separately by **sequence '
      'count**. Zero occupancy is **not** functional novelty; no "crowded" cutoff is used.')
    A('')
    A('## Crosswalk coverage')
    A('')
    A(f'- R3 backbones measured: **{len(r3_bb)}/{cross["round3_backbones"]}** '
      f'(complete={cross["complete"]}); near-identical edges {cross["near_identical_edges"]}.')
    A(f'- R3 distinct components: **{len(bbs)}**.')
    A(f'- v8 rows: {len(v8)}; **{len(unknown)} have no crosswalk label** → component **UNKNOWN**: '
      f'{", ".join("`"+u+"`" for u in unknown) if unknown else "none"}')
    A(f'- v8 occupies **{len(v8_comp)}** components: ' +
      ', '.join(f'`{c}`×{n}' for c, n in sorted(collections.Counter(
          l for l in v8_labels.values() if l).items(), key=lambda kv: (-kv[1], kv[0]))))
    A('')
    A('## Components with zero v8 members')
    A('')
    A(f'- **{len(zero_v8)}** of {len(bbs)} R3 components contain no v8 member.')
    A(f'- **{len(withprior)}** of those already contain a prior R1/R2 member (not new territory).')
    A(f'- **{len(noprior)}** contain no prior R1/R2 member either (the only genuinely unrepresented '
      'territory under this rule).')
    A('')
    A('### (a) zero v8 members, but a prior R1/R2 member exists')
    A('')
    if withprior:
        A('| component | unique backbones | R3 PASS sequences |')
        A('|---|---|---|')
        for l in withprior:
            A(f'| `{l}` | {len(bbs[l])} | {seqs.get(l, 0)} |')
    else:
        A('_None._')
    A('')
    A('### (b) zero v8 members AND no prior R1/R2 member')
    A('')
    A('| component | unique backbones | R3 PASS sequences |')
    A('|---|---|---|')
    for l in noprior:
        A(f'| `{l}` | {len(bbs[l])} | {seqs.get(l, 0)} |')
    A('')
    A('## Occupancy distribution (unique backbones per component, all R3 components)')
    A('')
    hist = collections.Counter(len(v) for v in bbs.values())
    A('| backbones in component | components |')
    A('|---|---|')
    for k in sorted(hist):
        A(f'| {k} | {hist[k]} |')
    A('')
    A(f'Largest single component holds **{max(len(v) for v in bbs.values())} of '
      f'{len(r3_bb)}** R3 backbones — i.e. backbone variety is concentrated, which is the '
      'reason a per-design novelty claim cannot substitute for a component-level one.')
    A('')
    A('## Limits of this inventory')
    A('')
    A('- Zero occupancy is **absence of a design**, not evidence of a good one. Nothing here is a '
      'prediction of binding, agonism, or developability.')
    A('- The independence-universe conflict (direct / v7cc / global) applies to these counts exactly '
      'as it does in the dossier; component labels come from the shared X### crosswalk, and '
      'v8\'s unlabelled row keeps that baseline UNKNOWN rather than understated.')
    A('- No C5 work and no new candidates follow from this; it is an allocation map for a future '
      'round that Ricardo would have to authorise.')

    OUT.write_text('\n'.join(L) + '\n')
    print(f'DIVERSITY WROTE {OUT.relative_to(ROOT)} sha={hashlib.sha256(OUT.read_bytes()).hexdigest()[:12]}')
    print(f'  components={len(bbs)} zero_v8={len(zero_v8)} with_prior={len(withprior)} '
          f'no_prior={len(noprior)} v8_comp={len(v8_comp)} v8_unknown={unknown}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
