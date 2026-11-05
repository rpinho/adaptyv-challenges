# Is there a clean replacement pool for the 8 flagged v8 rows? (read-only answer: yes)

Question this answers, so Ricardo does not have to: if he decides to drop the 8 flagged rows, is the
alternative an empty set?

**No. The bench is full — but using it is a decision, not a computation.**

## What exists, measured
| pool | size | clash status |
|---|---:|---|
| sampling-depth arm, all-rules PASS | **83** | **0** with any clash recorded (the gate required 0) |
| …of those, iPTM ≥ 0.87, binder pLDDT ≥ 85, refold PASS | **75** | 0 |
| distinct backbones represented | **61** | — |
| median iPTM of those 83 | **0.91** | — |
| replication arm designs passing both seeds | see Result 3 | 0 discordant on clash-only flips except grazing cases |

For scale: the 6 clash-flagged v8 rows carry iPTM 0.85–0.88. The bench median is **0.91**, i.e. the
bench is not a downgrade on the surrogate metric.

## What this does NOT settle (and why both consultants said "do not auto-refill")
1. **These are different backbones.** v8's 8 flagged rows are incumbents from the BindCraft/RFdiffusion
   cohorts; the bench is 61 new backbones. Swapping changes **portfolio composition**, not just rows —
   diversity, generation-method breadth and the "8 BindCraft rows" property both consultants wanted
   preserved all move.
2. **Independence must be re-measured against the surviving 12**, not assumed from the arm's own
   dedup. The repo already has a fail-closed rule for this (`c3_round2_gate_20261025.py`, condition 5–6:
   TM ≥ 0.65 AND coverage ≥ 0.80 = near-identical; connected components must rise).
3. **No new evidence is needed — but a new *decision record* is.** "Evidence only, no v9" was the ruling
   for tonight. A challenger CSV is a new artifact and therefore needs Ricardo's explicit approval,
   which is exactly what both consultants said.
4. **A clean clash verdict is still not binding.** Nothing here measures affinity or agonism.

## The honest one-liner for 08:00
"If you want to drop the 8, there are 75 clash-clean designs at iPTM ≥ 0.87 already scored — the
question is portfolio policy, not supply. Say the word and I build a filtered challenger as a NEW file;
v8 stays untouched either way."
