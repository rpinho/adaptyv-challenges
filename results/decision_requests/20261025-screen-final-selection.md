# Decision request — what to do with the finished sampling-depth screen (C3)

Time: 2026-10-25 05:45 ET. Deadline pressure: pods stop ~07:55; Ricardo uploads himself later; nothing is submitted.

## Measured facts (all from frozen artifacts, no impressions)
- Arm `c3_sampling_depth_v1_20261025` is FINALIZED: 172/172 complete, 83 all-rules PASS, 89 FAIL, 0 bad evidence, 0 duplicates.
  Evidence: results/c3_sampling_depth_v1_20261025/{coverage_ledger.json, summary.md, verify.json, delta_b.json, SHA256SUMS.evidence}
- Gate unchanged: complex ipTM>=0.85, binder pLDDT>=80, >=5 groove residues, >=20 contacts <=5A, ZERO heavy-atom pairs <2.0A.
- 83 PASS span 61 distinct backbones; 22 backbones have >=2 PASS. 83/83 also passed refold.
- Delta-B = 19 distinct backbones whose FIRST all-rules PASS came from this arm (baseline 56/120 R3 backbones already passed).
- All 83 PASS sequences are <=0.116 3-mer Jaccard to any v8 sequence (max 0.116); zero exact sequence duplicates. So they are sequence-novel, but they come from the SAME 120-backbone cohort v8 was drawn from (8 BindCraft + 0 variants + 12 RFD4 in v8).
- v8 remains the sole submission candidate: results/c3_submission_v8_20261025.csv (20 rows, sha 631ed0bf...), untouched.
- A separate seed-replication arm (160 folds, 80 designs x 2 seeds) is running and will finish by ~07:30; its purpose is reproducibility evidence, not candidate generation.

## Question (one answer, please)
Given the competition allows 20 designs and v8 already has 20, what is the best defensible use of these 83 PASS designs?
Please choose and justify:
(A) Write NO new candidate CSV; keep v8 sole candidate. Use the screen as evidence only (ΔB/backbone yield).
(B) Write a NEW versioned 20-row CSV (e.g. v9) replacing some v8 rows with screen PASSes, under a pre-specified, non-cherry-picked rule (state the exact rule, how many rows replaced, which slots, and the independence/diversity test).
(C) Write a NEW versioned file as an ALTERNATE/CHALLENGER set (not claiming to beat v8), with a one-line ranking vs v8.
(D) Something else.

Also answer:
1. If (B) or (C), what exact replacement/selection rule should be frozen BEFORE looking at which designs are best? The concern is outcome-blind selection (we already know all 83 pass).
2. Does replacing v8 rows with same-cohort backbones risk reducing portfolio diversity or agonism potential? v8 is 8 BindCraft + 12 RFD4; the screen is all RFD4/ProteinMPNN backbones from that cohort.
3. Is there any reason to prefer keeping all 8 BindCraft rows (different generation method) over swapping them for higher-iPTM RFD4 screen hits?
4. If no new CSV is warranted, what should the remaining ~2h of pod time be used for (the seed arm is already running; C4 GPU is blocked until 08:00)?
