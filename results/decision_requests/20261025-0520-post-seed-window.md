# DECISION REQUEST — what to run on 5 A40 pods between the seed-replication arm and 07:55 ET

Time now: 2026-10-25 ~05:20 ET. Ricardo is asleep and unreachable. Mission authorization ends 08:00 ET;
nothing may be submitted and nobody may be contacted. Five A40 pods at $0.59/h are already running and
stop themselves at ~08:05 ET. Mission rule 5: never leave a pod idle. Mission rule 3: design selection,
scoring and "what to run next" require an external decision; DeepSeek orchestrates and does not decide.

## Measured facts (not projections)
- Screen arm `c3_sampling_depth_v1_20261025`: **158/172 complete, 76 all-rules PASS, ΔB 17**, 0 bad
  evidence, 0 duplicates. Per pod: p1 30/34, p2 34/39, p3 27/27 done, p4 36/41, p5 31/31 done.
- Screen finalizes at 06:13 or as soon as all slices report ALL_DONE; hard stop 06:31.
- Seed arm `c3_seed_replication_v1_20261025`: 160 runs (80 designs × 2 seeds), 24 runs scored, 0/80
  designs with both seeds yet. **Median wall 193-204 s**, measured 0.55-0.61 runs/min per pod with
  N=2. At five pods that is ~2.9 runs/min, so ~137 remaining runs need **~47 min** => the arm likely
  finishes **~06:20-06:35**, leaving roughly **60-90 min** of paid pod time before the 07:55 stop.
- Pods stop ~08:05 ET; seed hard stop 07:30; screen hard stop 06:31.
- Best C3 file on disk is v8 `631ed0bf…`; v6/v7/v9/apical unchanged. No v9 written. Nothing submitted.

## Constraints on any answer
- No new pods/endpoints/volumes; no credential use beyond compute on the five existing pods.
- No submission, no contact, no CSV overwrite. New candidate sets must be NEW versioned files with a
  one-line ranking. Thresholds/gates stay unchanged unless you explicitly rule otherwise.
- Work must be bounded and finish/checkpoint by 07:30 so retrieval completes by 07:50 and pods stop 07:55.
- CPU-only local analysis is free and always available; GPU time is the scarce resource.

## Questions (answer each explicitly, in order, as executable decisions)
1. **Q1 — Is my throughput estimate credible, and should pods be released early if the seed arm
   finishes ~06:30?** If yes, give the exact condition and action (e.g. "when a pod's seed slice reports
   ALL_DONE before 07:00, stop that pod's timer/remove it" vs "keep all five until 07:55").
2. **Q2 — What is the single highest-value GPU job for the free window?** Choose ONE and justify
   against the alternatives. Candidates on the table:
   (a) Kimi's staged same-backbone clash-resampling plan (32 FastRelax parents × 4 fresh MPNN sequences
       × 2 AF2M seeds = 256 folds; needs MPNN generation, which is CPU/GPU on the pods);
   (b) extend seed replication to more of the 180 R3 designs (cohort currently 80) — more stability data;
   (c) re-fold the ~40 v8/v7 candidate sequences that are currently single-run PASSes to test verdict
       stability before Ricardo submits Monday (directly de-risks the submission);
   (d) generate more sampling-depth draws on backbones that still have no PASS;
   (e) something else you consider better.
   Note: FastRelax needs a licensed PyRosetta container that does not exist on the pods — verify or
   propose a concrete substitute before choosing it.
3. **Q3 — If the answer is a stability/refold job (2b or 2c), give the exact scoring rule.** Which
   sequences, how many seeds, how many pods, and how a "stable PASS" is defined (e.g. PASS in >=2 of 3
   independent folds). Tonight's evidence: at 56 fully covered backbones, the two draws agree on the
   gate verdict only **55%** of the time, and several pairs have identical iPTM with opposite verdicts.
4. **Q4 — What must be true by 07:30 for the result to be usable?** Give the minimum coverage and the
   rule for reporting truncation (incomplete is never a failure; report by design and by seed).
5. **Q5 — Anything you would STOP doing?** Name any current spend or activity that should end now.

## Deliverable
Return a numbered ruling with: chosen job, exact command-level parameters (counts, seeds, pods, cutoffs),
acceptance/stop conditions, and what would make you reverse the choice. If you disagree with a premise,
say which measured number is wrong and what to measure instead. Mark anything needing Ricardo's approval
as `RICARDO-APPROVAL`.
