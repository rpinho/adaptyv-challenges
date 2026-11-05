# Urgent factual check — the "control flipped the gate" conclusion appears WRONG

You (Astra) tiebroke at 04:11 and your corrections were recorded. Before acting on them I found a
numerical error in the recorded evidence. Please check this and rule.

## What the record says
`HANDOFF_KIMI.md` (04:02/04:15) and `results/overnight_log.md` state, as the central finding:
- control `p1_H8_52_64_910012_s1` at seed 0 gives **groove contacts 18 vs R3's 21**, "**crosses the
  20 gate**", gate verdict **PASS → fail**, and "**the PASS→fail flip survives**".
- A "reproducibility caveat" was written into the morning report: a single-run gate verdict near a
  threshold (groove 18–22, iPTM 0.84–0.86) "is not stable evidence".

## What the frozen code and artifacts actually say
The unchanged gate in `scripts/c3_round2_verify_20261025.py` is:
- `MIN_GROOVE = 5` — minimum **groove residues contacted**
- `MIN_CONTACTS = 20` — minimum **total contacts <=5 A**
- `CLASH_A = 2.0`, `BINDER_PLDDT_MIN = 80.0`, `FLOOR = 0.850`

Scored with that same verifier on the same artifacts:
| | R3 baseline | control seed 0 |
|---|---|---|
| status | PASS | **PASS** |
| iPTM | 0.920 | 0.910 |
| binder pLDDT | 96.73 | 95.45 |
| groove residues | 21 | **18** |
| **total contacts <=5 A** | 511 | **544** |
| clashes | 0 | 0 |

So the "21 -> 18" delta is on **groove residues**, where the threshold is **5**, not 20. The metric
with a 20 threshold is **total contacts**, and the control went **511 -> 544 (up, and far above 20)**.
The control therefore does **not** cross the gate and does **not** flip PASS->fail. It stays PASS on
both definitions. In R3 only 2 of 180 designs fail on the groove rule at all (0 and 1 residues).

## Why this matters
1. The "port validation found a real discrepancy / one control flipped the gate" story is the
   headline justification for the whole reproducibility arm and its caveat. If the flip does not
   exist, the caveat's stated evidence is wrong.
2. The 04:15 "re-scored on one definition ... the PASS->fail flip survives" correction repeated the
   same threshold mix-up, so it did not fix the root error.
3. What *is* real and unaffected: iPTM 0.920->0.910 and binder pLDDT 96.73->95.45 moved, all five
   models present, and the second/third controls reproduced 0.910 / 95.45 / 18 identically.

## Questions
1. Do you confirm the gate is 5 groove residues + 20 total contacts (not 20 groove residues)?
2. Given the control stays PASS, is the seed-replication arm still the right use of the remaining
   GPU window (~2 h 10 min before the 07:00 admission stop)? Options as I see them:
   (a) keep the frozen 160-invocation arm as-is (it still measures end-to-end gate stability);
   (b) keep it but re-frame the morning-report claim as "small metric drift with no observed
       classification change", dropping the flip/caveat language;
   (c) narrow it (e.g. 40 designs x 2 seeds) and spend the rest of the window on something else.
3. If the flip is not real, what is the *correct* headline for tonight's port-validation evidence?
   My read: the port is metric-consistent within ~0.01 iPTM / ~1.3 pLDDT on the same design and the
   same seed, with no gate-verdict change observed so far — weaker than "not bit-reproducible".

Please answer 1-3 concretely and briefly; I will implement immediately. Nothing has been submitted.
