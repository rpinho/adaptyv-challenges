You asked: score the R62 epitope-conditioned designs for G12D selectivity.
I will: harvest the R62 design output (results/japanfold_pilot/round62_seqs.csv), score each design with opendde-abag against both G12D and WT peptides, compute delta (g12d_conf - wt_conf) and composite (delta×10 + g12d_conf + iptm×2), and report the results.

## Execution
The round script (scripts/c5_round.py) handles harvest and scoring in phases 3-6 after design completes. This is already part of the design job. If run separately:

```bash
cd /Users/ricardo/dev/adaptyv-c4
# Scoring is built into c5_round.py — it runs design → harvest → score → report as one pipeline
```

## Log result
After scoring completes, log with:
```bash
log-result --ledger lanes/c5/RESULTS.jsonl --new <yes|no> --kind value \
  --what "R62 epitope conditioning C:4..8. N designs, M selective, best delta=+X.XXX" \
  --link results/japanfold_pilot/round62_sel_jobs.json --referee NONE
```

## Success = at least one design with delta > +0.015 AND wt_conf < 0.5
