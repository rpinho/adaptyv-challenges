# Decision request — three new $0 findings after the 07:30 handoff, and what they change

Time: 2026-10-25 07:45 ET. Orchestrator. No GPU, nothing launched, nothing submitted, nobody contacted.
Both prior rulings said "stop, queue nothing, all remaining work is Ricardo's decision or a $0 CPU
analysis" (06:35 and 06:40). These are $0 CPU analyses; I need your ruling on what, if anything, they change.

## New evidence since your 06:40 plan (all read-only, all frozen inputs)

### 1. Replacement-pool independence vs the SURVIVING 12 — measured
`results/c3_replacement_independence_20261025/FINDING.md`
Your 06:40 plan and `c3_replacement_pool_20261025.md` §2 both said independence must be re-measured
against the 12 rows that would survive a filtered challenger, "not assumed from the arm's own dedup".
Measured with the frozen rule (TM≥0.65 AND coverage≥0.80), complete matrix 200 backbones × 20 v8 rows:
- depth-arm all-rules PASS: 61 backbones → **15 near-identical to a survivor, 46 clear (75.4%)**
- HQ subset: 56 backbones → 12 near-identical, **44 clear (78.6%)**
- only 3 of the 12 survivors (`c3_glp1r_ecd_14/_151/_26`) are matched by any pool backbone; 1 pool
  backbone matches a flagged row (`p3_H8_81_100_910210` → `c3_glp1r_ecd_29`, TM 0.6506).
Coverage is 1.0 for all pairs, so the frozen rule reduces to TM≥0.65 in this matrix (reported as measured).

### 2. Design-level worst-case rollup of the five-model panel — measured
`results/c3_five_model_pick_20261025/WORST_CASE_ADDENDUM.md`
Same 80 runs as the 07:17 finding, now stated per design:
- rank-001 only: **16/16 pass**
- "any failing model ⇒ design FAIL": **6/16 pass** (10 fail)
- all five models fail: **0/16**
The 10 failing designs are exactly the 10 you already named as having an alternate clashing model, so the
worst-case rollup introduces no new failure mode. 6 unanimous-pass designs are named in the addendum.

### 3. FastRelax cohort stratified as you required — measured
`results/c3_fastrelax_cohort_20261025/{cohort.csv,summary.md}`
You both required stratification "by severity and atom type" and exclusion of backbone–backbone collisions
before any pilot. Using the frozen 06:48 audit's actual atom pairs:
- 32/32 manifest designs audited; severity **S4<1.2 Å: 5, S3 1.2–1.5: 4, S2 1.5–1.9: 10, S1 1.9–2.0: 13**
  (reproduces the "9 below 1.5 Å" figure exactly)
- atom classes across 55 clash pairs: **side–side 30, backbone–sidechain 5, backbone–backbone 0**
- **0 designs excluded** by the backbone–backbone rule; 5 carry a backbone–sidechain contact and are
  flagged as a separate stratum.
No relaxation was run. Licence is still RICARDO-APPROVAL.

## Questions
1. Do findings 1–3 change any ruling you gave at 06:35/06:40/07:00/07:17? If yes, state exactly what
   changes; if no, say so plainly so it is recorded as "no change".
2. Does finding 2 create a NEW decision for Ricardo (choose rank-001 / best-model / worst-model /
   two-fold-agreement as the archived-model policy), or is it purely descriptive evidence to attach to the
   existing v8 decision?
3. Does finding 1 change the filtered-challenger recommendation in either direction — specifically, does
   "75–79% of the pool is structurally clear of the surviving 12" make a challenger more defensible, or is
   portfolio composition still the binding objection?
4. Is there any remaining $0 CPU analysis you would order before 08:00 that is NOT already done and NOT a
   Ricardo decision? If none, say "none" explicitly.
5. Anything in the three findings you believe is overstated or mis-framed — name it and I will correct it.

Files: the three FINDING/summary files above; plus `results/c3_v8_eligibility_20261025/eligibility.md`,
`results/MORNING_REPORT_20261025.md` (§ READ THIS FIRST, Result 5, Result 6).
Do not propose submitting; nothing is submitted and nobody is contacted.
