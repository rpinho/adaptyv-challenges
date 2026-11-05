#!/usr/bin/env python3
"""Build the frozen R3 downstream queue (Astra ruling 2026-10-25, option D).

The generation allocation is Kimi's and is NOT changed here. This script only orders
already-generated sequences for MPNN -> ESMFold/refold -> AF2M.

Ordering, frozen before any score is observed:
  * one sequence per eligible backbone in pass 1: s1 if it passes soluble+refold,
    otherwise s2; pass 2 carries every remaining passing sequence;
  * within a pass, ascending backbone seed; on p4/p5 the three length bins are
    round-robined, ascending seed within each bin;
  * every pod gets a disjoint slice; pod workloads are balanced by count.

This script is pure: it reads manifests and writes queue files. It never injects new
seeds, retries, thresholds, or submissions.
"""
import argparse, collections, csv, hashlib, json, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from c3_soluble_filters_20261025 import failures as soluble_failures  # noqa: E402

BINS = ['52_64', '65_80', '81_100']
ALLOC = {
    'p1': [('H8', '52_64', range(910000, 910024))],
    'p2': [('H8', '65_80', range(910100, 910124))],
    'p3': [('H8', '81_100', range(910200, 910224))],
    'p4': [('H8', '52_64', range(910024, 910032)),
           ('H8', '65_80', range(910124, 910132)),
           ('H8', '81_100', range(910224, 910232))],
    'p5': [('H4', '52_64', range(910300, 910308)),
           ('H4', '65_80', range(910400, 910408)),
           ('H4', '81_100', range(910500, 910508))],
}


def sha(p):
    return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()


def bin_of_name(name):
    """Return the length bin from a backbone or design name.

    Generation names look like ``p1_H8_52_64_910000``; MPNN names append ``_s1``.
    The r2-config legacy names look like ``p1_H8_52_64_910000`` too, so this is
    deliberately independent of the config key.
    """
    import re
    m = re.search(r'_(52_64|65_80|81_100)_(\d+)(?:_s\d+)?$', name)
    if not m:
        raise ValueError(f'cannot determine length bin from {name!r}')
    return m.group(1), int(m.group(2))


def allocation_map():
    out = {}
    for pod, jobs in ALLOC.items():
        for tag, b, seeds in jobs:
            for s in seeds:
                out[f'{pod}_{tag}_{b}_{s}'] = {'pod': pod, 'arm': tag, 'bin': b, 'seed': s}
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--seqs', required=True, help='CSV name,sequence from MPNN')
    ap.add_argument('--refold', required=True, help='refold_checks json')
    ap.add_argument('--out', required=True)
    ap.add_argument('--pod-file', default='/tmp/pods.txt')
    a = ap.parse_args()

    sequences = {r['name']: r['sequence'].strip()
                 for r in csv.DictReader(open(a.seqs))}
    refold = json.loads(pathlib.Path(a.refold).read_text())
    alloc = allocation_map()

    by_bb = collections.defaultdict(dict)
    bad_names = []
    for name in sequences:
        m = None
        import re
        m = re.match(r'^(.*)_s(\d+)$', name)
        if not m:
            bad_names.append(name)
            continue
        bb, sample = m.group(1), int(m.group(2))
        by_bb[bb][sample] = name
    if bad_names:
        print(f'ERROR unrecognised sequence names: {bad_names[:10]}', file=sys.stderr)
        return 4

    missing_bb = sorted(set(alloc) - set(by_bb))
    unexpected_bb = sorted(set(by_bb) - set(alloc))
    if missing_bb or unexpected_bb:
        print(f'ERROR allocation mismatch missing={missing_bb[:10]} '
              f'unexpected={unexpected_bb[:10]}', file=sys.stderr)
        return 4

    recs, excluded = [], collections.Counter()
    for bb in sorted(by_bb):
        meta = alloc[bb]
        samples = by_bb[bb]
        if not samples:
            print(f'ERROR backbone {bb} has no MPNN sequence', file=sys.stderr)
            return 4
        for sample in sorted(samples):
            name = samples[sample]
            seq = sequences[name]
            reasons = []
            try:
                reasons.extend(f'soluble:{x}' for x in soluble_failures(seq))
            except Exception as ex:
                reasons.append(f'soluble:unscoreable:{ex}')
            rr = refold.get(name)
            if not rr or not rr.get('pass'):
                reasons.append('refold_fail')
            rec = {'backbone': bb, 'sample': sample, 'name': name,
                   'sequence_sha256': hashlib.sha256(seq.encode()).hexdigest(),
                   'pod': meta['pod'], 'bin': meta['bin'], 'arm': meta['arm'],
                   'seed': meta['seed'], 'eligible': not reasons, 'reasons': reasons}
            recs.append(rec)
            for r in reasons:
                excluded[r] += 1

    # Pass 1: exactly one eligible sequence per backbone, s1 before s2.
    pass1, remaining = [], []
    for bb in sorted(by_bb):
        group = sorted([r for r in recs if r['backbone'] == bb],
                       key=lambda x: x['sample'])
        elig = [r for r in group if r['eligible']]
        if elig:
            pass1.append(elig[0])
            remaining.extend(elig[1:])
    for r in pass1:
        r['pass_no'] = 1
    for r in remaining:
        r['pass_no'] = 2

    pods = [line.split()[0] for line in open(a.pod_file) if line.strip()]
    if set(pods) != set(ALLOC):
        print(f'ERROR pod file {a.pod_file!r} does not match allocation pods {sorted(ALLOC)}',
              file=sys.stderr)
        return 4

    queues = {p: [] for p in pods}
    for r in pass1 + remaining:
        queues[r['pod']].append(r)

    # Within each pod, all pass-1 rows precede all pass-2 rows. p1-p3 are
    # single-bin and sorted by seed. p4/p5 round-robin their three bins, with
    # ascending seed inside each bin.
    for p in pods:
        q = queues[p]
        ordered = []
        for pass_no in (1, 2):
            rows = [r for r in q if r['pass_no'] == pass_no]
            if p in ('p4', 'p5'):
                buckets = {b: sorted([r for r in rows if r['bin'] == b],
                                     key=lambda x: x['seed']) for b in BINS}
                i = 0
                while any(i < len(v) for v in buckets.values()):
                    for b in BINS:
                        if i < len(buckets[b]):
                            ordered.append(buckets[b][i])
                    i += 1
            else:
                ordered.extend(sorted(rows, key=lambda x: (x['bin'], x['seed'])))
        queues[p] = ordered

    queued = {r['name'] for q in queues.values() for r in q}
    out = {'rule': 'Astra option D: pass1 one eligible sequence/backbone, pass2 remainder',
           'seqs_sha256': sha(a.seqs), 'refold_sha256': sha(a.refold),
           'n_backbones': len(by_bb), 'n_designs': len(recs),
           'n_eligible': sum(r['eligible'] for r in recs),
           'n_pass1': len(pass1), 'n_pass2': len(remaining),
           'excluded_reasons': dict(excluded),
           'allocation': alloc,
           'per_pod': {p: {'pass1': sum(r['pass_no'] == 1 for r in q),
                           'pass2': sum(r['pass_no'] == 2 for r in q),
                           'total': len(q)} for p, q in queues.items()},
           'queues': queues,
           'not_queued': [r for r in recs if r['name'] not in queued]}
    pathlib.Path(a.out).write_text(json.dumps(out, indent=1) + '\n')
    print(f"{len(recs)} designs, {out['n_eligible']} eligible, "
          f"pass1={len(pass1)} pass2={len(remaining)}")
    for p in pods:
        c = out['per_pod'][p]
        print(f"  {p}: pass1={c['pass1']} pass2={c['pass2']} total={c['total']}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
