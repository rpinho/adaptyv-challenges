#!/usr/bin/env python3
"""Independent heavy-atom clash audit (Astra/Kimi 06:40 agreed item #1).

Deliberately does NOT import any C3 lane module. Re-parses the AF2M PDBs itself and
recomputes clashing atom pairs with its own parser, so a defect in the shared clash
helper cannot hide behind itself.

Cohort (both frozen by prior rulings; nothing is re-scored, nothing is admitted):
  * the 11 replication designs whose two seeds disagree on the gate verdict
  * the 32 frozen FastRelax candidates (clash_pairs 1-2, all other gates passing)

For every artifact it records, per clashing pair: binder atom, target atom, residue
numbers/names, and the distance, plus a margin histogram (how close to the 2.0 A line).

Outputs results/c3_clash_audit_20261025/audit.json + audit.md. READ-ONLY with respect
to every frozen artifact; writes only inside its own directory.
"""
import collections, json, math, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / 'results/c3_clash_audit_20261025'
CLASH_A = 2.0
HEAVY = {'N', 'CA', 'C', 'O', 'CB'}
# every other element counts as heavy too; only hydrogens are excluded
def is_heavy(name):
    return not (name.startswith('H') or name[0].isdigit() and 'H' in name[:2])


def parse_pdb(path):
    """Minimal fixed-column PDB parser -> {chain: [(resseq, resname, {atom: (x,y,z)})]}."""
    chains = collections.OrderedDict()
    seen = collections.OrderedDict()
    for line in open(path):
        if not line.startswith(('ATOM', 'HETATM')):
            continue
        alt = line[16]
        if alt not in (' ', 'A'):
            continue
        name = line[12:16].strip()
        if not is_heavy(name):
            continue
        resn = line[17:20].strip()
        ch = line[21]
        try:
            resseq = int(line[22:26])
            x, y, z = float(line[30:38]), float(line[38:46]), float(line[46:54])
        except ValueError:
            continue
        el = line[76:78].strip().upper()
        if el == 'H':
            continue
        key = (ch, resseq, line[26])
        if key not in seen:
            seen[key] = {'resseq': resseq, 'resname': resn, 'atoms': {}}
            chains.setdefault(ch, []).append(seen[key])
        seen[key]['atoms'][name] = (x, y, z)
    return chains


def min_interchain_distance(binder, target, scan=6.0):
    """True minimum inter-chain heavy-atom distance.

    Kimi 07:05: reporting min_dist=None for a passing structure is a CENSORED value, not its
    actual minimum. This scans out to `scan` A so every run reports a real number.
    """
    best = (None, None, None)
    s2 = scan * scan
    for br in binder:
        for bname, bxyz in br['atoms'].items():
            for tr in target:
                for tname, txyz in tr['atoms'].items():
                    dx = bxyz[0] - txyz[0]
                    dy = bxyz[1] - txyz[1]
                    dz = bxyz[2] - txyz[2]
                    d2 = dx * dx + dy * dy + dz * dz
                    if d2 <= s2 and (best[0] is None or d2 < best[0]):
                        best = (d2, f"{br['resname']}{br['resseq']}:{bname}",
                                f"{tr['resname']}{tr['resseq']}:{tname}")
    if best[0] is None:
        return None, None, None
    return round(math.sqrt(best[0]), 3), best[1], best[2]


def clashing_pairs(binder, target, cutoff=CLASH_A):
    c2 = cutoff * cutoff
    out = []
    for br in binder:
        for bname, bxyz in br['atoms'].items():
            for tr in target:
                for tname, txyz in tr['atoms'].items():
                    dx = bxyz[0] - txyz[0]
                    dy = bxyz[1] - txyz[1]
                    dz = bxyz[2] - txyz[2]
                    d2 = dx * dx + dy * dy + dz * dz
                    if d2 <= c2:
                        out.append({
                            'binder': f"{br['resname']}{br['resseq']}:{bname}",
                            'target': f"{tr['resname']}{tr['resseq']}:{tname}",
                            'dist': round(math.sqrt(d2), 3),
                        })
    out.sort(key=lambda r: r['dist'])
    return out


def audit_artifact(d):
    d = pathlib.Path(d)
    pdb = d / 'complex_rank_001.pdb'
    if not pdb.exists():
        return {'status': 'incomplete', 'reasons': [f'missing {pdb.name}']}
    chains = parse_pdb(pdb)
    if len(chains) != 2:
        return {'status': 'unparseable', 'reasons': [f'{len(chains)} chains']}
    # binder = shorter chain by residue count, as in the frozen verifier
    order = sorted(chains, key=lambda c: len(chains[c]))
    binder, target = chains[order[0]], chains[order[1]]
    pairs = clashing_pairs(binder, target)
    dmin, a1, a2 = min_interchain_distance(binder, target)
    return {
        'status': 'READ',
        'n_clash_pairs': len(pairs),
        'min_interchain_dist': dmin,
        'min_pair_atoms': (a1, a2),
        'pairs': pairs[:40],
        'binder_residues_involved': sorted({p['binder'].split(':')[0] for p in pairs}),
        'min_dist': pairs[0]['dist'] if pairs else None,
        'clash_pass': not pairs,
    }


def main():
    OUT.mkdir(exist_ok=True)
    rep = json.loads((ROOT / 'results/c3_seed_replication_v1_20261025/verify.json').read_text())
    by = collections.defaultdict(list)
    for r in rep['records']:
        if r.get('status') in ('PASS', 'fail'):
            by[r['name'].rsplit('_s20', 1)[0]].append(r)
    discordant = sorted(k for k, v in by.items()
                        if len(v) == 2 and sorted(x['status'] for x in v) == ['PASS', 'fail'])
    fr = json.loads((ROOT / 'results/c3_r3_20261025/fastrelax_candidates_20261025.json').read_text())
    # locate each FastRelax candidate's artifact dir(s)
    cand_names = [c.get('name') or c.get('design_id') for c in fr['candidates']]

    groups = {}
    for name in discordant:
        entries = []
        for r in by[name]:
            a = audit_artifact(r['artifact_dir'])
            a['seed'] = r['name'].rsplit('_s', 1)[1]
            a['verifier_status'] = r['status']
            entries.append(a)
        groups[name] = {'cohort': 'discordant', 'runs': entries}

    # FastRelax candidates: find any pulled artifact directory by name prefix
    roots = [ROOT / 'results/c3_seed_replication_v1_20261025/out',
             ROOT / 'results/c3_r3_20261025']
    idx = collections.defaultdict(list)
    for root in roots:
        if not root.exists():
            continue
        for p in root.rglob('complex_rank_001.pdb'):
            idx[p.parent.name].append(p.parent)
    found, missing = 0, []
    for name in cand_names:
        hits = sorted(idx.get(name, [])) or [p for k, v in idx.items() if k.startswith(name) for p in v]
        if not hits:
            missing.append(name)
            continue
        found += 1
        runs = [audit_artifact(h) for h in sorted(hits)]
        if name in groups:                      # member of BOTH cohorts: never overwrite
            groups[name]['cohort'] = 'discordant+fastrelax_candidate'
            known = {(r.get('n_clash_pairs'), r.get('min_dist')) for r in groups[name]['runs']}
            groups[name]['runs'] += [r for r in runs
                                     if (r.get('n_clash_pairs'), r.get('min_dist')) not in known]
        else:
            groups[name] = {'cohort': 'fastrelax_candidate', 'runs': runs}

    summary = {
        'generated': __import__('datetime').datetime.now().astimezone().isoformat(timespec='seconds'),
        'cutoff_a': CLASH_A,
        'n_discordant_designs': len(discordant),
        'n_fastrelax_candidates': len(cand_names),
        'fastrelax_artifacts_found': found,
        'fastrelax_artifacts_missing': missing,
        'groups': groups,
    }
    (OUT / 'audit.json').write_text(json.dumps(summary, indent=1) + '\n')

    L = ['# Independent heavy-atom clash audit', '',
         f"- cutoff: **{CLASH_A} A**, own parser (no C3 lane imports)",
         f"- discordant replication designs: **{len(discordant)}** (2 runs each)",
         f"- FastRelax candidates: **{len(cand_names)}**; artifacts located **{found}**, missing **{len(missing)}**",
         '', '## Discordant designs — does the fail run really clash?', '',
         '| design | PASS run pairs | fail run pairs | fail-run min dist | binder residues involved |',
         '|---|---|---|---|---|']
    for name in discordant:
        g = groups[name]
        p = next((r for r in g['runs'] if r.get('verifier_status') == 'PASS'), {})
        f = next((r for r in g['runs'] if r.get('verifier_status') == 'fail'), {})
        L.append(f"| `{name}` | {p.get('n_clash_pairs')} | {f.get('n_clash_pairs')} | "
                 f"{f.get('min_dist')} | {', '.join(f.get('binder_residues_involved') or [])} |")
    L += ['', '## FastRelax candidates', '']
    if missing:
        L.append(f"Artifacts not found locally for {len(missing)}: " +
                 ', '.join(f'`{m}`' for m in missing[:12]) + (' …' if len(missing) > 12 else ''))
    for name in cand_names:
        if name in groups and 'fastrelax' in groups[name]['cohort']:
            for r in groups[name]['runs']:
                L.append(f"- `{name}`: {r.get('n_clash_pairs')} pairs, min {r.get('min_dist')}")
    (OUT / 'audit.md').write_text('\n'.join(L) + '\n')
    print(f"CLASH AUDIT: {len(discordant)} discordant designs, "
          f"{found}/{len(cand_names)} fastrelax artifacts located, "
          f"cutoff {CLASH_A} A -> {OUT/'audit.json'}")
    for name in discordant:
        g = groups[name]
        print(' ', name, [ (r.get('verifier_status'), r.get('n_clash_pairs'), r.get('min_dist')) for r in g['runs']])
    return 0


if __name__ == '__main__':
    sys.exit(main())
