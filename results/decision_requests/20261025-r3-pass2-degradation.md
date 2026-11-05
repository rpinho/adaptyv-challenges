# DECISION REQUEST — the second MPNN sequence per backbone is materially worse

02:57 ET. deciders: Astra (fast) + Kimi. Orchestrator does not decide.

## Measured (163 of 182 R3 designs through the structural gate; artifacts on disk)
| stratum | pass | rate |
|---|---|---|
| **pass 1** (one sequence per eligible backbone, s1-first) | **46/94** | **48.9%** |
| **pass 2** (the second MPNN sequence, s2) | **24/69** | **34.8%** |

- The gate is unchanged. Same clash rule dominates both strata: **92 of 93 failures are ≥1
  heavy-atom pair ≤2.0 Å**, 1 is a contact-count failure.
- So the *same backbone* yields an acceptable design about half the time on its first MPNN sample
  and about a third of the time on its second. This is not backbone quality — it is sequence sampling.
- Consequence for the morning: of the ~70 eligible designs, roughly **46 come from pass 1 and 24 from
  pass 2**. If pass 2 is a weaker population, any ranking that treats them identically is diluted.

## Questions (Answer 1–4)
1. **Is pass 2 evidence-only, or eligible on equal terms?** Both earlier rulings said "advance only
   unchanged-gate passes", which would make them equal. Does a measured 34.8% vs 48.9% pass rate
   justify stratification (rank pass-1 first, pass-2 as alternates), or is that post-hoc selection on
   the same data that set the gate?
2. **Is the difference even significant at this n?** 46/94 vs 24/69. StaAight proportions test: is
   this a real effect or sampling noise? If not significant, say so and I will record it as
   "not established".
3. **Does this change what runs next?** Both of you proposed prospective **geometry selection** (Kimi's
   C). Does this result support sampling **more MPNN sequences per backbone** (cheap, no new
   backbones) rather than new backbones — and if so, is that a morning decision for Ricardo or
   something I may queue tonight?
4. **Anything to record** about sequence-sampling depth vs backbone quality as the binding lever.

## Constraints
Nothing submitted, nobody contacted, no new spend beyond the five pods, frozen cohort/hash unchanged,
no v9, no promotion, no threshold changes.
