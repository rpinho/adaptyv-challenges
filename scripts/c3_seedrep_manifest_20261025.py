#!/usr/bin/env python3
"""Outcome-blind cohort for c3_seed_replication_v1_20261025 (Astra 03:52 ruling).

Cohort rule, implemented verbatim:
  freeze the CURRENT 180 scored R3 designs; sort by ascending
  sha256("c3_seed_replication_v1_20261025|<design_id>"); take the first 80; no replacements.
  Ignores scores, PASS status, and live-arm results.

Seeds 20261030 and 20261031, one invocation each (`--num-seeds 1`), 160 invocations, no retries.

This script reads ONLY design IDs from the frozen R3 verifier and the R3 input CSV (sequences).
It never reads a PASS/FAIL field, an iPTM, or any arm outcome - that is enforced below, not assumed.

Writes results/c3_seed_replication_v1_20261025/{manifest.json,seedrep_input.csv,per_pod/}.
Exits 4 if the cohort cannot be built exactly.
"""
import csv, hashlib, json, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
R3 = ROOT / 'results/c3_r3_20261025'
OUT = ROOT / 'results/c3_seed_replication_v1_20261025'
ARM = 'c3_seed_replication_v1_20261025'
SEEDS = [20261030, 20261031]
N_COHORT = 80
PODS = ['p1', 'p2', 'p3', 'p4', 'p5']


def main():
    src = R3 / 'screen_input_20261025.csv'
    ver = R3 / 'screen_verify_20261025.json'
    for p in (src, ver):
        if not p.exists():
            print(f'SEEDREP FAIL missing {p}', file=sys.stderr)
            return 4
    rows = list(csv.DictReader(open(src)))
    v = json.loads(ver.read_text())

    # "scored" = has a complete artifact. This is a COVERAGE field, not an outcome field.
    scored = {r['name'] for r in v['records'] if r.get('status') in ('PASS', 'fail')}
    if len(scored) != 180:
        print(f'SEEDREP FAIL expected 180 scored R3 designs, found {len(scored)}', file=sys.stderr)
        return 4
    seq = {r['name']: (r['binder'].strip(), r['target'].strip()) for r in rows}
    missing = sorted(n for n in scored if n not in seq)
    if missing:
        print(f'SEEDREP FAIL scored designs without a sequence: {missing[:3]}', file=sys.stderr)
        return 4
    targets = {seq[n][1] for n in scored}
    if len(targets) != 1 or len(next(iter(targets))) != 111:
        print('SEEDREP FAIL target is not a single 111-mer', file=sys.stderr)
        return 4

    def key(n):
        return hashlib.sha256(f'{ARM}|{n}'.encode()).hexdigest()

    order = sorted(scored, key=key)
    cohort = order[:N_COHORT]                      # strictly by hash; no outcome consulted
    jobs = []
    for n in cohort:                               # adjacent seed pairs, cohort order
        for s in SEEDS:
            jobs.append({'name': f'{n}_s{s}', 'design_id': n, 'seed': s,
                         'binder': seq[n][0], 'target': seq[n][1], 'source': ARM})
    if len(jobs) != 2 * N_COHORT:
        print('SEEDREP FAIL job count mismatch', file=sys.stderr)
        return 4

    OUT.mkdir(parents=True, exist_ok=True)
    with open(OUT / 'seedrep_input.csv', 'w', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=['name', 'binder', 'target', 'source', 'seed'])
        w.writeheader()
        for j in jobs:
            w.writerow({k: j[k] for k in ('name', 'binder', 'target', 'source', 'seed')})

    per = {p: [] for p in PODS}
    for i, j in enumerate(jobs):
        per[PODS[i % len(PODS)]].append(j)
    for p in PODS:
        (OUT / f'per_pod/{p}.csv').parent.mkdir(parents=True, exist_ok=True)
        with open(OUT / f'per_pod/{p}.csv', 'w', newline='') as fh:
            w = csv.DictWriter(fh, fieldnames=['name', 'binder', 'target', 'source', 'seed'])
            w.writeheader()
            for j in per[p]:
                w.writerow({k: j[k] for k in ('name', 'binder', 'target', 'source', 'seed')})

    # fail closed: the seed MUST survive the CSV round-trip or the arm is not a seed arm
    back = list(csv.DictReader(open(OUT / 'per_pod' / 'p1.csv')))
    if not back or 'seed' not in back[0] or any(str(r.get('seed', '')).strip() == '' for r in back):
        print('SEEDREP FAIL per-pod CSV lost the seed column', file=sys.stderr)
        return 4
    allback = []
    for p in PODS:
        allback += list(csv.DictReader(open(OUT / 'per_pod' / f'{p}.csv')))
    if len(allback) != len(jobs):
        print('SEEDREP FAIL per-pod row total != jobs', file=sys.stderr)
        return 4
    seen = {(r['name'], str(r['seed'])) for r in allback}
    if len(seen) != len(jobs):
        print('SEEDREP FAIL duplicate or collapsed seed jobs', file=sys.stderr)
        return 4

    man = {
        'arm': ARM,
        'ruling': 'Astra 2026-10-25 (results/decisions/20261025-post-arm-next-gpu-astra.md)',
        'cohort_rule': ('current 180 scored R3 designs, sorted by sha256("arm|design_id") ascending, '
                        'first 80; no replacements; outcomes never consulted'),
        'selection_is_outcome_blind': True,
        'n_scored_r3': len(scored),
        'n_cohort': len(cohort),
        'seeds': SEEDS,
        'n_jobs': len(jobs),
        'concurrency_per_pod': 2,
        'cap_invocations': 160,
        'retries': 0,
        'cohort_sha256': hashlib.sha256('\n'.join(cohort).encode()).hexdigest(),
        'jobs_sha256': hashlib.sha256(
            '\n'.join(f"{j['name']}|{j['binder']}|{j['target']}" for j in jobs).encode()).hexdigest(),
        'per_pod_counts': {p: len(per[p]) for p in PODS},
        'target_sha256': hashlib.sha256(next(iter(targets)).encode()).hexdigest(),
        'cohort': cohort,
        'jobs': [{k: j[k] for k in ('name', 'design_id', 'seed')} for j in jobs],
    }
    (OUT / 'manifest.json').write_text(json.dumps(man, indent=1) + '\n')
    print(f"SEEDREP manifest: cohort={len(cohort)}/180 jobs={len(jobs)} "
          f"cohort_sha={man['cohort_sha256'][:12]}… per_pod={man['per_pod_counts']}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
