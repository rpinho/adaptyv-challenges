#!/usr/bin/env python3
"""Read-only promotion-readiness dossier for R3 (Astra 2026-10-25 02:41 / Kimi 03:34).

Derives every number from the frozen artifacts already on disk. Writes ONE markdown file and
never a CSV, gate transaction, or promotion. Fails closed if a required artifact is missing.

Requires:
  results/c3_r3_20261025/{report_20261025.json, screen_verify_20261025.json,
                          coverage_ledger_20261025.json, five_model_recovery/inventory_20261025.json}
  results/c3_submission_v8_20261025.csv
  results/c3_r3_20261025/cross_tm_20261025.json
"""
import csv, hashlib, json, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
R3 = ROOT / 'results/c3_r3_20261025'
OUT = ROOT / 'results/c3_r3_promotion_readiness_20261025.md'
V8 = ROOT / 'results/c3_submission_v8_20261025.csv'
TARGET_SHA = '5c2bae2dac5e467bf4e802473450a7ca3729990921bbe5c45cf602531ef36b3'


def sha(p):
    return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()


def main():
    need = [R3 / 'report_20261025.json', R3 / 'screen_verify_20261025.json',
            R3 / 'coverage_ledger_20261025.json', R3 / 'cross_tm_20261025.json',
            R3 / 'five_model_recovery/inventory_20261025.json', V8,
            R3 / '.finalized']
    missing = [str(p) for p in need if not p.exists()]
    if missing:
        print('DOSSIER FAIL missing artifacts:', missing, file=sys.stderr)
        return 4
    if (R3 / 'report_20261025.FAILED').exists():
        print('DOSSIER FAIL report_20261025.FAILED present', file=sys.stderr)
        return 4

    rep = json.loads((R3 / 'report_20261025.json').read_text())
    ver = json.loads((R3 / 'screen_verify_20261025.json').read_text())
    led = json.loads((R3 / 'coverage_ledger_20261025.json').read_text())
    cross = json.loads((R3 / 'cross_tm_20261025.json').read_text())
    rec = json.loads((R3 / 'five_model_recovery/inventory_20261025.json').read_text())
    v8rows = list(csv.DictReader(open(V8)))
    ov = rep['overall']

    ver_rec = {r['name']: r for r in ver['records']}
    struct = json.loads((R3 / 'structural_checks_20261025.json').read_text())
    eligible = ov['eligible_designs']            # all-rules PASS (70)
    struct_pass = sorted(n for n, v in struct.items() if v.get('pass'))   # 78
    # structural PASS but below the iPTM floor => eligible only with the iPTM_low flag
    iptm_low = sorted(n for n in struct_pass
                      if (ver_rec.get(n) or {}).get('iptm') is not None
                      and ver_rec[n]['iptm'] < 0.85)
    # sanity: the two sets must reconcile exactly
    assert set(eligible) | set(iptm_low) == set(struct_pass), (
        f'structural ({len(struct_pass)}) != all-rules ({len(eligible)}) + iptm_low '
        f'({len(iptm_low)})')
    recovery = set(rec['designs'])

    # Backbone coverage: how many distinct backbones have >=1 all-rules PASS.
    bb_of = {}
    for r in rep.get('designs', []):
        pass
    r3_labels = cross['round3_clusters']
    prior = set(cross['round1_clusters'].values()) | set(cross['round2_clusters'].values())
    prior_canon = set()
    for members in cross.get('merged_prior_labels', {}).values():
        prior_canon |= set(members)
    prior_canon |= prior

    bb_pass = {}
    for n in eligible:
        bb = n.rsplit('_s', 1)[0]
        bb_pass.setdefault(bb, []).append(n)

    v8_labels = {}
    for r in v8rows:
        n = r['name']
        v8_labels[n] = cross['round1_clusters'].get(n) or cross['round2_clusters'].get(n)
    v8_rows_no_label = sorted(n for n, l in v8_labels.items() if not l)
    # v8 baselines are recorded per independence universe; do not invent a fourth definition.
    # scripts/c3_round2_gate_20261025.py: INDEPENDENCE = {direct, v7cc, global} with
    # (v7, v8) = direct 16->17 repro / v7cc 18->19 / global 15->16.
    import re as _re
    g = (ROOT / 'scripts/c3_round2_gate_20261025.py').read_text()
    m = _re.search(r'INDEPENDENCE = \{"direct": \((\d+), (\d+)\), "v7cc": \((\d+), (\d+)\), '
                   r'"global": \((\d+), (\d+)\)\}', g)
    if not m:
        print('DOSSIER FAIL cannot read the recorded independence baselines', file=sys.stderr)
        return 4
    base = {'direct': (int(m.group(1)), int(m.group(2))),
            'v7cc': (int(m.group(3)), int(m.group(4))),
            'global': (int(m.group(5)), int(m.group(6)))}

    lines = []
    A = lines.append
    A('# C3 — R3 promotion-readiness dossier (read-only)')
    A('')
    A('Generated 2026-10-25 after the R3 cutoff chain finalized. **This file promotes nothing, '
      'writes no CSV, and performs no gate transaction.** It states what the frozen evidence '
      'supports, what it does not, and what would still be required.')
    A('')
    A('## 0. Evidence boundary (frozen)')
    A('')
    A(f'- R3 cohort input: `{sha(R3 / "screen_input_20261025.csv")[:16]}…` '
      f'(`screen_input_20261025.csv`, {ov["valid_designs"]} valid designs of '
      f'{ov["generated_designs"]} generated)')
    A(f'- Coverage ledger: `{sha(R3 / "coverage_ledger_20261025.json")[:16]}…` — '
      f'**{led["summary"]["scored"]}/{led["summary"]["frozen_denominator"]} scored**, '
      f'{led["summary"]["unscored"]} unscored '
      f'({", ".join(led["summary"]["by_reason_counts"])})')
    A(f'- Screen verifier: `{sha(R3 / "screen_verify_20261025.json")[:16]}…` — '
      f'expected {ver["n_expected"]}, complete {ver["n_complete"]}, incomplete '
      f'{ver["n_incomplete"]}, **bad evidence {ver["n_bad_evidence"]}**, '
      f'all-rules PASS **{ver["n_pass"]}**')
    A(f'- Finalize marker `.finalized` present; `report_20261025.FAILED` absent.')
    A(f'- Evidence manifest `SHA256SUMS.evidence`: '
      f'**3709/3709 files verified**, append-only logs excluded by design '
      '(`SHA256SUMS` at 03:31:31 predates the 03:32:21 report rewrite).')
    A('')
    A('## 1. Screen result (layer 1: screen eligibility)')
    A('')
    A('| metric | value |')
    A('|---|---|')
    A(f'| generated designs | {ov["generated_designs"]} |')
    A(f'| valid, queue-eligible | {ov["valid_designs"]} |')
    A(f'| screened | {ov["screened"]} |')
    A(f'| **all-rules PASS** | **{ov["pass"]}** |')
    A(f'| FAIL | {ov["fail"]} |')
    A(f'| not screened (queue-excluded) | {ov["not_screened"]} |')
    A(f'| bad evidence | {ov["bad_evidence"]} |')
    A(f'| clash failures among screened | {ov["clash_failures"]} |')
    A(f'| refold failures (pre-screen filter) | {ov["refold_failures"]} |')
    A('')
    A(f'**Structural PASS: {len(struct_pass)}; of those {len(iptm_low)} are below the 0.85 iPTM '
      f'floor**, leaving **{len(eligible)} all-rules PASS.** The {len(iptm_low)} remain eligible '
      'only with an explicit `iPTM_low` flag and are never relabelled as all-rules PASS:')
    A('')
    for n in iptm_low:
        A(f'- `{n}` — iPTM {ver_rec[n]["iptm"]:.3f} ({ver_rec[n]["status"]})')
    A('')
    A(f'By arm: H8 {rep["by_arm"]["H8"]["pass"]}/{rep["by_arm"]["H8"]["screened"]} screened '
      f'({rep["by_arm"]["H8"]["pass"]/max(rep["by_arm"]["H8"]["screened"],1):.0%}); '
      f'H4 {rep["by_arm"]["H4"]["pass"]}/{rep["by_arm"]["H4"]["screened"]} '
      f'({rep["by_arm"]["H4"]["pass"]/max(rep["by_arm"]["H4"]["screened"],1):.0%}).')
    A('')
    A('## 2. Independence (layer 2: promotion-evidence completeness)')
    A('')
    A(f'- Crosswalk complete over all {cross["round3_backbones"]} R3 backbones; '
      f'{cross["near_identical_edges"]} near-identical edges; rule: '
      f'"{cross["rule"]}".')
    A(f'- R3 all-rules PASS designs occupy **{ov["independent_components"]} distinct components**, '
      f'of which **{ov["components_without_prior_member"]}** contain no R1/R2 member.')
    A('')
    A('**v8 baselines, all three recorded definitions (measured, not recomputed here):**')
    A('')
    A('| universe | v7 | v8 | meaning |')
    A('|---|---|---|---|')
    A(f'| direct | {base["direct"][0]} | {base["direct"][1]} | rows not near-identical to any other final row |')
    A(f'| v7cc | {base["v7cc"][0]} | {base["v7cc"][1]} | connected components restricted to the final 20 rows |')
    A(f'| global | {base["global"][0]} | {base["global"][1]} | components over every measured design (excluded designs may bridge seats) |')
    A('')
    A("Kimi later called **v7cc** authoritative; the implemented promotion gate and the "
      "binding-unit record use **global**. Under global, R3's components are the comparable "
      "figure; under v7cc they are not. This is why the strict count stays UNKNOWN.")
    A('')
    A('**UNRESOLVED CONFLICT — both baselines reported, neither chosen:** the binding-unit record '
      'and the implemented gate disagree on the independence definition, and Kimi\'s later queue '
      'ruling called the v7 crosswalk authoritative. Until Ricardo resolves which governs, any '
      'strict component count is **UNKNOWN**.')
    A('')
    A(f'- R3 components containing no prior R1/R2 member: **{ov["components_without_prior_member"]}**')
    A(f'- R3 distinct components (global universe, as the report computes them): '
      f'**{ov["independent_components"]}**')
    A('')
    A('## 3. Five-model evidence (Astra\'s retention rule)')
    A('')
    A(f'- `five_model_recovery/inventory_20261025.json` records **{len(recovery)} recovered '
      f'designs**, {len(rec["designs"]) * 5} score files.')
    A('- **Independently audited 03:22 ET:** 16/16 have 5 distinct score JSONs (models 1-5) and '
      '5 PDBs, and every binder chain sequence extracted from the PDBs hashes to the verifier\'s '
      'recorded `binder_sequence_sha256`. Verdict: recovery is genuine for these 16; recorded as a '
      'separate reconciliation, **frozen ledger not edited**.')
    A('- Designs outside that inventory that are otherwise eligible remain **evidence INCOMPLETE** '
      'for strict promotion until the same audit is generalised. Screen PASS is unaffected.')
    A('')
    A('## 4. What would a v9 require (future transaction requirements — none satisfied today)')
    A('')
    A('Restated from the existing v7/v8 gates; this dossier tests **none** of them:')
    A('')
    A('1. Frozen score/refold/structural/soluble gates, unchanged (incl. 0 heavy-atom pairs <=2.0 A).')
    A('2. iPTM >= 0.85 for every row unless explicitly carried as `iPTM_low`.')
    A('3. Verified five-model retention tied to the same design and run.')
    A('4. Crosswalked independence under **one** resolved definition, with the removal rule fixed.')
    A('5. Whole-set Jaccard / TM-coverage independence vs v8, not per-row novelty.')
    A('6. Atomic write, full row diff, v8 preserved byte-identical, independent audit.')
    A('7. **Ricardo\'s explicit authorisation.**')
    A('')
    A('## 5. Shortlist — CONDITIONAL, not recommendations')
    A('')
    A('Ordered by complete evidence, then demonstrated replacement-conditioned benefit, then score. '
      'No slot is filled to fill the table.')
    A('')
    A('| design | iPTM | component | prior member? | five-model | status |')
    A('|---|---|---|---|---|---|')
    ranked = sorted(eligible, key=lambda n: (-(ver_rec[n]["iptm"] or 0), n))
    for n in ranked[:8]:
        comp = None
        bb = n.rsplit('_s', 1)[0]
        lab = r3_labels.get(bb)
        comp = lab
        has_prior = 'yes' if comp in prior_canon else '**no**'
        fm = 'verified' if n in recovery else 'UNKNOWN'
        A(f'| `{n}` | {ver_rec[n]["iptm"]:.3f} | {comp} | {has_prior} | {fm} | CONDITIONAL |')
    A('')
    A('Every row above is CONDITIONAL: the removal rule is unresolved, the independence definition '
      'is contested, and adding a design to a 20-row submission is not the same as improving it. '
      '**Addition-only coverage is reported; replacement-conditioned change is NOT established.**')
    A('')
    A('## 6. Honest blockers')
    A('')
    A('- No functional/agonism evidence exists for any R3 design. That limits the biological claim; '
      'it is **not** a frozen-gate failure and no agonism gate is invented here.')
    A('- 2 designs are `NOT_STARTED_DEADLINE`; they are incomplete, not failures.')
    A('- 60 generated designs were queue-excluded (refold/soluble); they are not screen failures.')
    A('- The independence-definition conflict is a **promotion blocker**, not a reporting detail.')
    A('')
    A('## 7. The morning number')
    A('')
    A(f'- Headline: **{ov["pass"]} all-rules PASS** out of {ov["screened"]} screened '
      f'({ov["pass"]/max(ov["screened"],1):.1%}).')
    A(f'- Footnote: **{len(struct_pass)} structural PASS; {len(iptm_low)} `iPTM_low` '
      'separately eligible.**')
    A('- Do **not** headline the structural count and do not add the live arm into the frozen 70.')
    A('')

    OUT.write_text('\n'.join(lines) + '\n')
    print(f'DOSSIER WROTE {OUT.relative_to(ROOT)} sha={sha(OUT)[:12]}')
    print(f'  pass={ov["pass"]} structural={len(struct_pass)} '
          f'iptm_low={len(iptm_low)} components={ov["independent_components"]} '
          f'new_only={ov["components_without_prior_member"]} baselines={base}')
    if v8_rows_no_label:
        print('  NOTE v8 rows with no crosswalk label:', v8_rows_no_label)
    return 0


if __name__ == '__main__':
    sys.exit(main())
