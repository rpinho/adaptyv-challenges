You asked: design binders that selectively bind the KRAS G12D pMHC complex over the WT pMHC complex.
I will: run R62 with BoltzGen epitope conditioning on chain C residues 4-8 (centered on the G12D mutation at position 6). This is the first round to use binding_types — all 61 previous rounds used unconditioned protein-anything. The hypothesis: conditioning on the mutation-containing peptide region will direct binder contacts to the Asp side chain at position 6, which becomes Gly in WT, yielding selectivity.

## Execution

```bash
cd /Users/ricardo/dev/adaptyv-c4
python3 scripts/c5_round.py \
  --round 62 \
  --length-min 230 --length-max 250 \
  --num-jobs 12 --num-designs 10 \
  --tag epitope \
  --binding-chain C --binding-range '4..8'
```

## Success criteria
- At least 1 design with delta > +0.015 AND wt_conf < 0.5 (strict selectivity)
- Best delta > +0.184 (R61 unconditioned baseline)

## Failure = same way as
- R41-R60 failure mode: all designs have WT > 0.5 (no selectivity). If this happens with epitope conditioning too, the approach gets round 2 of 3.
- R61 failure mode: worse delta than standard maxlong. Different mechanism — epitope conditioning vs length variation.

## Budget
~$10 estimated (12 design jobs × ~120 designs → 240 scoring jobs)
