# Decision request — model-pick bias found in the 16 recovered five-model R3 designs

$0, read-only, CPU only. Nothing changed, nothing launched. Script:
`scripts/c3_five_model_pick_20261025.py` → `results/c3_five_model_pick_20261025/`.

## Measured (all 16 recovered designs x 5 models = 80 structural runs, frozen verifier primitives)

- Rank-001 (the archived pick) passes all gates on **16/16** designs — as the pipeline already knew.
- Across the five models: **61 PASS / 19 FAIL**. Every failure is clash-driven except 2 pLDDT and 1 chain.
- **10 of 16 designs have at least one alternate model that clashes** (rank-001 = 0 clashes for all 16).
- Alternate models fall under the 0.85 iPTM floor in **8 runs** (worst 0.20).
- Model-index effect: model 5 mean iPTM **0.896** vs 0.849–0.873 for models 1–4; mean pLDDT **96.3** vs 95.2–95.5;
  clash runs **2/16** vs 3–5/16. **Rank-001 is model 5 in all 16** (ColabFold's ranking step selects it).

## The question

1. Is "the archived rank-001 structure clashes" now properly *worse* than we thought — i.e. is rank-001 a
   systematically optimistic pick whose gate verdict would not survive model resampling?
2. Does this change your ruling on v8? Specifically: does it strengthen "preserve v8 and disclose" or
   "build a filtered challenger", or does it argue the flag is a *pipeline artifact* rather than a design defect?
3. Given only 16 designs have five models and v8's flagged rows have rank-001 only, what is the honest
   statement Ricardo can put in front of the competition without a re-fold?

Files to read: this request, `results/c3_five_model_pick_20261025/summary.json`,
`results/c3_five_model_pick_20261025/per_model_metrics.json`,
`results/c3_v8_eligibility_20261025/eligibility.md`, `results/MORNING_REPORT_20261025.md` (§ READ THIS FIRST).
