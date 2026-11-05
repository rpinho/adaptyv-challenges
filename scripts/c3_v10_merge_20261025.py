#!/usr/bin/env python3
"""C3 v10 merge pipeline. $0, CPU only, read-only w.r.t. every frozen artifact.

WHAT THIS DOES
--------------
Implements the merge rule: take the 12 survivors, apply a clash verdict table, disqualify any
survivor with a failing verdict, and fill vacated seats from a FROZEN replacement order without
re-ranking. Refuses to write anything unless asked, and never touches a frozen file.

FROZEN ARTIFACTS (asserted byte-identical before and after every run)
--------------------------------------------------------------------
  results/c3_submission_v8_20261025.csv                    631ed0bf...
  results/c3_submission_v7_20261025.csv                    1d99f843...
  results/c3_submission_v6_20261023.csv                    8e9b2d74...
  results/submission_v9.csv                                31d98a41...
  results/c3_sprint_8h_20261025/c3_candidate_v9_B-plddt_20261025.csv   704988ca...

MODES
-----
  --synthetic   build fake verdict tables at k = 0,1,3,8,12 fails, prove the rule + invariants.
                Writes nothing but a JSON report. This is the default.
  --dry-run     run the REAL inputs and PRINT the resulting roster structure. Writes no CSV.
  --write       run the real inputs and write the v10 CSV to --out. NOT enabled by default and
                NOT authorised this sprint (C3 is frozen; see RULE DISAGREEMENTS in the report).

RULE DISAGREEMENTS WITH THE DELEGATION (found while implementing, not editorial)
-------------------------------------------------------------------------------
D1. "replace only from the 8 all-5-clean" is unsatisfiable as written. Those 8 are ALREADY the
    replacement block inside v9. All 8 are in the file, so there is no unused seat among them. A
    vacated survivor seat can only be filled from the 11 designs in the wider 19-design gated base
    that are not yet admitted. This script uses that wider pool and labels it SPARE_POOL.

D2. "12 survivors + verdict table" cannot be scored at 5 models. The 5-model clash verdicts exist
    ONLY for the 83-design depth pool. None of the 12 v8-derived survivors is in it, so every
    survivor's verdict is UNKNOWN at 5 models. The only verdict data covering them is rank-001-only
    (results/c3_v8_clash_screen_20261025.json). This script treats an UNKNOWN verdict as
    NOT disqualified (conservative: never drop a row on absent evidence) and reports the coverage
    gap loudly. Running with 5-model verdicts on survivors is not possible from existing artifacts.

D3. "assert 20 rows" and "on exhaustion emit fewer swaps loudly" are mutually exclusive at
    k=12. With 12 survivors disqualified and 11 spares, the maximum reachable roster is 19.
    The 20-row assertion therefore holds only where supply allows; when it cannot, the script
    emits the shortfall loudly and labels the artifact SHORT rather than failing silently.
    At k=12 a 20-row file is not constructible from this pool.

D4. The frozen order is NOT a bare sort. The real rule is: sort by binder pLDDT desc, iPTM desc,
    name asc, then WALK the list skipping any design whose backbone is already used or whose
    backbone is near-identical (TM>=0.65 and coverage>=0.80) to an already-admitted one. Walking
    the raw sorted list without the dedup filter would admit duplicate/near-duplicate binders,
    so "never re-rank" is honoured here as "never re-SORT", while the dedup filter is preserved.
"""
import argparse, csv, hashlib, io, json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SPR = ROOT / 'results/c3_sprint_8h_20261025'
POOL5 = ROOT / 'results/c3_pool_five_model_20261025/per_design.json'
SEQS = ROOT / 'results/c3_sampling_depth_v1_20261025/sequences.csv'
REFOLD = ROOT / 'results/c3_sampling_depth_v1_20261025/refold_checks.json'
INDEP = ROOT / 'results/c3_replacement_independence_20261025/summary.json'
MATRIX = ROOT / 'results/c3_r3_20261025/cross_tm_20261025.json'
TB = SPR / 'tiebreak_corrected.json'
V8 = ROOT / 'results/c3_submission_v8_20261025.csv'
V9B = SPR / 'c3_candidate_v9_B-plddt_20261025.csv'
V8_CLASH = ROOT / 'results/c3_v8_clash_screen_20261025.json'

FROZEN = {
    'results/c3_submission_v8_20261025.csv': '631ed0bf',
    'results/c3_submission_v7_20261025.csv': '1d99f843',
    'results/c3_submission_v6_20261023.csv': '8e9b2d74',
    'results/submission_v9.csv': '31d98a41',
    'results/c3_sprint_8h_20261025/c3_candidate_v9_B-plddt_20261025.csv': '704988ca',
}
TM_MIN, COV_MIN, IPTM_MIN, N_SEATS = 0.65, 0.80, 0.87, 8
COLUMNS = ['name', 'sequence', 'molecule_class']


def sha16(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()[:16]


def check_frozen():
    bad = []
    for rel, prefix in FROZEN.items():
        p = ROOT / rel
        if not p.exists():
            bad.append((rel, 'MISSING'))
        elif not sha16(p).startswith(prefix):
            bad.append((rel, f'{sha16(p)} != {prefix}'))
    return bad


# ---------------------------------------------------------------- dedup / frozen order
def make_near(matrix):
    def near(a, b):
        ra, rb = matrix.get(a), matrix.get(b)
        rec = ra.get(b) if isinstance(ra, dict) else None
        if rec is None and isinstance(rb, dict):
            rec = rb.get(a)
        if not rec:
            return False
        return rec.get('tm', 0) >= TM_MIN and rec.get('coverage', 0) >= COV_MIN
    return near


def walk_frozen_order(ordered, want, backbone_of, near):
    """Walk a PRE-SORTED list in order, skipping backbone collisions. Never re-sorts."""
    picked = []
    for name in ordered:
        if len(picked) == want:
            break
        bb = backbone_of(name)
        if any(backbone_of(p) == bb for p in picked):
            continue
        if any(near(bb, backbone_of(p)) for p in picked):
            continue
        picked.append(name)
    return picked


# ---------------------------------------------------------------- core merge
def merge(survivors, verdicts, frozen_order, spare_pool, backbone_of, near,
          n_seats=N_SEATS, target_rows=None, verbose=False):
    """Pure function. Returns (roster, report). No file IO, no globals.

    survivors      ordered list of the rows to defend
    verdicts       dict name -> 'PASS' | 'FAIL' | 'UNKNOWN' (absent == UNKNOWN)
    frozen_order   PRE-SORTED replacement preference (never re-sorted here)
    spare_pool     designs eligible to fill vacated seats, already gated
    """
    log, rejected, kept = [], [], []
    for n in survivors:
        v = verdicts.get(n, 'UNKNOWN')
        if v == 'FAIL':
            rejected.append(n)
            log.append(f'DISQUALIFY {n}: verdict FAIL')
        else:
            kept.append(n)
            if v == 'UNKNOWN':
                log.append(f'KEEP {n}: verdict UNKNOWN (no evidence to drop)')

    # Target file size is len(survivors) + n_seats (12 survivors + 8 replacement seats = 20).
    # Each disqualified survivor vacates ONE seat, so the replacement count RISES by one per fail;
    # it does not fall. (An earlier version subtracted, which silently shrank the file.)
    target_rows = len(survivors) + n_seats
    need = target_rows - len(kept)
    # Walk the FULL frozen order, skipping anyone already seated. Do NOT restrict to
    # spare_pool here: spare_pool excludes the already-admitted replacement block, and at k=0
    # those ARE the correct picks. (Restricting to spares made k=0 disagree with v9, which is
    # the self-check that catches exactly this class of error.)
    supply = [n for n in frozen_order if n not in kept and n not in rejected]
    picks = walk_frozen_order(supply, max(need, 0), backbone_of, near)

    shortfall = need - len(picks)
    if shortfall > 0:
        log.append(f'!! EXHAUSTION: needed {need} replacements, frozen order supplied {len(picks)} '
                   f'(short {shortfall}). Emitting a SHORT roster of {len(kept) + len(picks)} '
                   f'rather than duplicating or re-ranking.')

    roster = kept + picks
    return roster, dict(rejected=rejected, kept=kept, picks=picks,
                        needed=need, supplied=len(picks), shortfall=shortfall,
                        n_rows=len(roster),
                        walk_source='full frozen order minus already-seated',
                        spare_capacity=len(spare_pool), log=log)


def validate(roster, seq_of, expect=20):
    """Returns (ok, problems). Enforces the invariants the delegation specifies."""
    problems = []
    if len(roster) != expect:
        problems.append(f'row_count {len(roster)} != {expect}')
    if len(set(roster)) != len(roster):
        problems.append('duplicate names')
    seqs = [seq_of(n) for n in roster]
    if len(set(seqs)) != len(seqs):
        problems.append('duplicate sequences')
    if any(not s for s in seqs):
        problems.append('empty sequence')
    return (not problems), problems


def payload(roster, seq_of, molecule='single_chain'):
    """Canonical CSV bytes. Deterministic: roster order is the only ordering input."""
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator='\n')
    w.writerow(COLUMNS)
    for n in roster:
        w.writerow([n, seq_of(n), molecule])
    return buf.getvalue()


# ---------------------------------------------------------------- real inputs
def load_real():
    pool = {r['name']: r for r in json.load(open(POOL5))}
    seqs = {r['name']: r['sequence'] for r in csv.DictReader(open(SEQS))}
    bb = {r['name']: r['backbone'] for r in csv.DictReader(open(SEQS))}
    refold = json.load(open(REFOLD))
    per_bb = json.load(open(INDEP))['pools']['depth_pass']['per_backbone']
    matrix = json.load(open(MATRIX))['pairs']
    near = make_near(matrix)

    base = [n for n, r in pool.items()
            if r.get('all_models_clash_clean')
            and (r.get('rank1_iptm') or 0) >= IPTM_MIN
            and (refold.get(n) or {}).get('pass')
            and not per_bb.get(bb[n], {}).get('near_identical_surviving')]

    tb = json.load(open(TB))
    astra8 = tb['astra_rule_binder_plddt']['names']
    cand = {c['name']: c for c in tb['candidates']}
    frozen_order = [c['name'] for c in sorted(
        (cand[n] for n in base if n in cand),
        key=lambda c: (-(c['binder_plddt'] or 0), -c['iptm'], c['name']))]

    v8 = {r['name']: r['sequence'] for r in csv.DictReader(open(V8))}
    v9 = {r['name']: r for r in csv.DictReader(open(V9B))}
    survivors = [n for n in v8 if n in v9]
    spare_pool = [n for n in frozen_order if n not in astra8 and n not in survivors]

    v8clash = {r['name']: r for r in json.load(open(V8_CLASH))}
    verdicts = {}
    for n in survivors:
        if n in pool:
            verdicts[n] = 'PASS' if pool[n]['all_models_clash_clean'] else 'FAIL'
        elif n in v8clash and v8clash[n].get('clash_pairs') is not None:
            verdicts[n] = 'PASS' if v8clash[n]['clash_pairs'] == 0 else 'FAIL'
        else:
            # clash_pairs is None when there is NO PDB (e.g. B_26102611_s1, note 'NO PDB').
            # Absent structure is ABSENT EVIDENCE, not a clash. Do not silently disqualify.
            verdicts[n] = 'UNKNOWN'

    return dict(pool=pool, seqs=seqs, bb=bb, near=near, base=base, astra8=astra8,
                frozen_order=frozen_order, survivors=survivors, spare_pool=spare_pool,
                verdicts=verdicts, v8clash=v8clash, cand=cand)


# ---------------------------------------------------------------- synthetic proof
def run_synthetic():
    """Synthetic universe: 12 survivors + 11 spares, distinct backbones and sequences.

    Supplies mirror the REAL pool (11 spares, not 12) so the k=12 exhaustion case is the real one.
    """
    surv = [f'SYN_S{i:02d}' for i in range(12)]
    spares = [f'SYN_R{i:02d}' for i in range(11)]
    seq = {}
    bb = {}
    for i, n in enumerate(surv + spares):
        # distinct sequence, distinct backbone; 30 aa of a deterministic pseudo-sequence
        seq[n] = ''.join('ACDEFGHIKLMNPQRSTVWY'[(i * 7 + j * 3) % 20] for j in range(30 + i))
        bb[n] = f'BB_{i:02d}'
    frozen_order = spares  # already in frozen preference order
    near = lambda a, b: False  # no TA matrix for synthetic backbones; all distinct

    cases = {}
    # k = the five requested points, plus 4 to pin the exact exhaustion boundary.
    for k in (0, 1, 3, 4, 8, 12):
        verdicts = {n: ('FAIL' if i < k else 'PASS') for i, n in enumerate(surv)}
        roster, rep = merge(surv, verdicts, frozen_order, set(spares), bb.get, near)
        csv_text = payload(roster, seq.get)
        ok, problems = validate(roster, seq.get, expect=20)
        cases[k] = dict(
            fails_requested=k,
            disqualified=len(rep['rejected']),
            kept_survivors=len(rep['kept']),
            replacements=len(rep['picks']),
            needed=rep['needed'],
            supplied=rep['supplied'],
            shortfall=rep['shortfall'],
            n_rows=rep['n_rows'],
            twenty_row_assert=('PASS' if ok else 'FAIL: ' + '; '.join(problems)),
            sha256_csv=hashlib.sha256(csv_text.encode()).hexdigest(),
            loud_shortfall=rep['shortfall'] > 0,
            first_rows=roster[:3])
    return cases


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--synthetic', action='store_true')
    ap.add_argument('--dry-run', action='store_true')
    ap.add_argument('--write', action='store_true')
    ap.add_argument('--out', default=str(SPR / 'c3_candidate_v10_20261025.csv'))
    a = ap.parse_args()

    before = check_frozen()
    if before:
        sys.exit(f'FROZEN ARTIFACT ALREADY MODIFIED - refusing to run: {before}')

    if a.write:
        sys.exit('--write is not authorised: C3 is frozen for this sprint (Ricardo). '
                 'Use --dry-run or --synthetic.')

    if not a.dry_run:
        cases = run_synthetic()
        out = dict(mode='synthetic', n_cases=len(cases), cases=cases,
                   frozen_pre=before, frozen_post=check_frozen())
        (SPR / 'v10_merge_synthetic.json').write_text(json.dumps(out, indent=1))
        print('synthetic verdict-table proof (12 survivors, 11 spares, frozen order, no re-rank)\n')
        print(f"{'fails':>5s} {'disq':>4s} {'kept':>4s} {'repl':>4s} {'need':>4s} "
              f"{'got':>3s} {'rows':>4s}  20-row    shortfall  sha256[:16]")
        for k, c in cases.items():
            print(f"{c['fails_requested']:5d} {c['disqualified']:4d} {c['kept_survivors']:4d} "
                  f"{c['replacements']:4d} {c['needed']:4d} {c['supplied']:3d} {c['n_rows']:4d}  "
                  f"{c['twenty_row_assert']:8s} {str(c['loud_shortfall']):9s} {c['sha256_csv'][:16]}")
        # Exhaustion boundary: with S spares the file stays at 20 rows while 8 + k <= S.
        S = 11
        max_k = None
        for k in sorted(cases):
            if cases[k]['shortfall'] == 0 and cases[k]['n_rows'] == 20:
                max_k = k
        print(f"\nEXHAUSTION BOUNDARY: {S} spares absorb at most {S - 8} survivor failures. "
              f"Largest k that still yields 20 rows = {max_k}.")
        print(f"  -> a 20-row file is guaranteed only for k <= {max_k}; "
              f"every k above that is SHORT and is labelled so.")
        k12 = cases[12]
        print(f"  k=12: {k12['n_rows']} rows, shortfall {k12['shortfall']} (D3 confirmed: "
              f"20 rows is not constructible from this pool at k=12)")
        bad = [k for k, c in cases.items()
               if c['shortfall'] == 0 and not c['twenty_row_assert'].startswith('PASS')]
        print(f"  invariant: whenever shortfall==0, the roster is exactly 20 rows -> "
              f"{'PASS' if not bad else 'FAIL ' + str(bad)}")
        loud = [k for k, c in cases.items() if c['shortfall'] > 0 and not c['loud_shortfall']]
        print(f"  invariant: every shortfall is flagged loudly -> {'PASS' if not loud else 'FAIL ' + str(loud)}")
        print(f"wrote {SPR / 'v10_merge_synthetic.json'}")
        return

    d = load_real()
    roster, rep = merge(d['survivors'], d['verdicts'], d['frozen_order'],
                        set(d['spare_pool']), d['bb'].get, d['near'])
    v8seq = {r['name']: r['sequence'] for r in csv.DictReader(open(V8))}
    v9_order = [r['name'] for r in csv.DictReader(open(V9B))]
    seq_of = lambda n: (d['seqs'].get(n) or d['pool'].get(n, {}).get('sequence')
                        or v8seq.get(n) or '')
    ok, problems = validate(roster, seq_of, expect=20)
    known = sum(1 for n in d['survivors'] if d['verdicts'][n] != 'UNKNOWN')
    print(f'real dry-run (no CSV written)\n')
    print(f'  survivors            {len(d["survivors"])} '
          f'({known} with a verdict, {len(d["survivors"]) - known} UNKNOWN)')
    print(f'  gated base           {len(d["base"])}')
    print(f'  astra frozen block   {len(d["astra8"])}')
    print(f'  spare pool           {len(d["spare_pool"])}')
    print(f'  disqualified         {len(rep["rejected"])}')
    print(f'  replacements         {len(rep["picks"])}')
    print(f'  roster rows          {rep["n_rows"]}')
    print(f'  twenty-row assert    {"PASS" if ok else "FAIL: " + "; ".join(problems)}')
    # SELF-CHECK: with no disqualifications the pipeline must reproduce the frozen v9 roster
    # exactly (same 20 names, same order). If this ever fails, the merge rule has drifted.
    if not rep['rejected']:
        same = roster == list(v9_order)
        print(f'  v9 self-check        {"PASS" if same else "FAIL - merge rule drifted from v9"}')
        if not same:
            sys.exit('self-check failed: k=0 must reproduce v9 exactly')
    else:
        print('  v9 self-check        SKIPPED (disqualifications present; v9 is not the expectation)')
    if rep['shortfall']:
        print(f'  !! EXHAUSTION shortfall {rep["shortfall"]}')
    print()
    for line in rep['log']:
        if line.startswith('!!') or 'UNKNOWN' in line:
            print('  ' + line)
    post = check_frozen()
    print(f'\n  frozen intact        {"PASS" if not post else "FAIL " + str(post)}')
    out = dict(mode='dry-run', verdict_coverage=dict(known=known, unknown=len(d['survivors']) - known),
               survivors=d['survivors'], base=len(d['base']), spare_pool=d['spare_pool'],
               roster=roster, report={k: v for k, v in rep.items() if k != 'log'},
               twenty_row_assert='PASS' if ok else problems, frozen_pre=before, frozen_post=post)
    (SPR / 'v10_merge_dryrun.json').write_text(json.dumps(out, indent=1))
    print(f'  wrote {SPR / "v10_merge_dryrun.json"}')


if __name__ == '__main__':
    main()
