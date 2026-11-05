# R3 will finish its screen at 03:00 ET. What is the next job? (No v9 tonight — I am asking about a READ-ONLY readiness dossier.)

## Established state
- 182-design frozen R3 cohort; ~129-140 scored at 02:25 ET; cutoff 03:00, quiesce 03:15, finalize+hash 03:30, pods stop 03:42.
- Report (read-only) now emits per H8/H4 and length bin: generated/valid/screened/clash fails/refold fails/
  fully eligible/crosswalked-independent components/no-prior-member components. Counts reconcile against
  3 independent records or it exits 4.
- Provisional at 129 scored: 21-48 fully eligible depending on how many land; all PASS have structural+refold pass;
  iPTM range 0.85-0.93. Crosswalk complete over all 120 R3 backbones (284 near-identical edges measured).
- v8 `631ed0bf...` remains the sole candidate. Nothing submitted. Your Q5 prohibits a v9 tonight and any
  further v8 replacement, and that stands regardless of what I ask below.

## Q1 — is a read-only "promotion readiness dossier" the right next job?
Proposal: after 03:30, produce ONLY analysis (no CSV, no gate transaction, no promotion):
  (a) the exact frozen promotion criteria a hypothetical v9 would have to satisfy, restated from the
      existing v7/v8 gates (iPTM floor, refold, structural/clash, TM/coverage independence, five-model rule,
      CSV integrity, atomic write, v8 preserved);
  (b) for every fully eligible R3 design: would it clear each criterion, and how many NEW crosswalked
      independent components would adding it create vs v8's current count;
  (c) the honest blockers (what evidence is missing: e.g. five-model retention split, agonism/functional
      evidence, anything the frozen gates demand that R3 does not provide);
  (d) a ranked shortlist of at most 5 designs with the reason each is or is not worth a v9 attempt tomorrow.
Is this the right scope? Anything to add or drop? Should it be written as `results/c3_r3_promotion_readiness_20261025.md`?

## Q2 — what else should run tonight after 03:30?
Candidate options I see, all CPU-only, no pods (they stop at 03:42), no Modal spend:
  (i) the dossier above;
  (ii) C4: re-verify the 342/343 apical analysis and document the domain-only/non-native caveat as the
      standing blocker (C4 native expansion is stopped by Astra until a Boltz port passes; the port failed
      with |delta iPTM| 0.187 vs the 0.03 rule);
  (iii) C5 target-independent prep is already done and tested (18/18) — nothing more to do before the target
      is announced Mon 10-26;
  (iv) strengthen next-round design diversity: use the measured crosswalk to identify which of the 56 R3
      components are crowded by existing designs, so a future round samples under-represented regions.
Which one(s) do you want as the post-03:30 queue, in priority order? If you want (iv), state the rule for
what counts as "under-represented" — I will not invent a threshold.

## Q3 — the five-model evidence gap
The finalizer currently splits PASS into "five models retained" vs "rank-1 only". Serial-era rows (16 of them,
from before the runner persisted all five) can never be upgraded; their /tmp dirs are gone. For a hypothetical
v9, does the strict five-model rule bar using an R3 design that is otherwise fully eligible? R3 rows were all
folded by runners that persist all five, so I expect R3 to be clean, but confirm the rule you intend.
