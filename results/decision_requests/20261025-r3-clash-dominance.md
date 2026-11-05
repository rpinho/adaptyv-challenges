# DECISION REQUEST — clash geometry, not iPTM, is the binding constraint on R3

requested 2026-10-25 02:12 ET. deciders: Kimi (primary), Astra (second). Orchestrator does not decide.

## Measured facts (all from pulled artifacts on the Mini; 96 of 182 R3 designs scored so far)
- Structural gate (unchanged rounds 1-3): binder pLDDT ≥80, ≥5 groove residues, ≥20 contacts ≤5 Å,
  **zero heavy-atom pairs <2.0 Å**, clean chain integrity, correct lengths.
- **96 evaluated: 45 PASS, 51 FAIL.**
- **Breakdown of the 51 failures: 50 from the clash rule (≥1 heavy-atom pair <2.0 Å), 1 from too few
  groove contacts. Zero from pLDDT, zero from chain integrity.**
- **iPTM does not discriminate the gate:** PASS median iPTM **0.910**, FAIL median **0.900**.
  Of 45 passes, 40 have iPTM ≥0.85; of 51 failures, **41 have iPTM ≥0.85**. 5 passes are below 0.85.
  So an iPTM threshold of 0.85 keeps 41/51 structurally ineligible designs and drops 5 eligible ones.
- By arm: H8 37/78 pass (47%), H4 8/18 pass (44%) — no arm advantage on this gate.
- This reproduces the E3 result exactly (E3: 7/24 eligible, clashes dominated, arms separated on clash
  rate not iPTM) and round 2 (19/24 ≥0.85 but only 7 eligible).

## The question
The design pipeline optimizes iPTM/RFD4 confidence, but the gate that actually decides is a
sub-2.0 Å heavy-atom clash count. A 2 Å overlap is a *steric* failure, and it is not being selected
against anywhere in the current loop. Options:

A. **Accept the gate as-is** and ship whatever passes (45 today). No new generation.
B. **Post-hoc clash repair** of near-miss designs (e.g. 1–2 clash pairs): relax/repack side chains
   with a fast tool, re-fold, re-gate. Cheap, uses the 51 existing failures.
C. **Change generation** to select against clashes at the backbone/MPNN stage (e.g. add a clash
   penalty during MPNN sequence design, or filter backbones by predicted clash before AF2M).
D. **Re-examine the 2.0 Å threshold** — is it the right cut for a designed binder at this resolution,
   or is it over-strict for a 5-model AF2M ensemble whose rank_001 may not be the best model?

## What the orchestrator needs
1. Which option (or a different one), and whether any is allowed tonight vs after Ricardo wakes.
2. If D: the threshold you want and the evidence basis; if you say keep 2.0 Å, say so plainly.
3. If B: which tool, which designs are eligible for repair, and whether repaired designs are new
   candidates or evidence only (they would be a NEW versioned file, never v8 edits).
4. Whether the 5 designs that PASS with iPTM <0.85 should be treated differently from the 40 that pass
   with ≥0.85, given iPTM is not the gate.
5. Anything you want recorded about the "optimize iPTM, gate on clashes" mismatch for the record.

## Non-negotiables
Nothing submitted, nobody contacted, no new spend beyond the five pods (≈$2.95/h), v6/v7/v8/v9/apical
untouched, frozen cohort and hash `eeba81b7…` unchanged, no v9 without an explicit ruling.
