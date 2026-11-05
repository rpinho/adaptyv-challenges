# C4 — read-only reconciliation (Astra's Q2 item 2)

Written 2026-10-25 03:47 ET. **No GPU, no port retry, no native expansion, no new candidates.**
Both consultants deferred all C4 GPU work until after Ricardo's 08:00 review.

## What was checked, and how
Independent recomputation from the stored artifacts only — no figure below is copied from a prior
report without a check.

| check | result |
|---|---|
| canonical complexes present | **343/343** (`results/c4_rebuild_20261024/remote_pdbs/`, 343 files) |
| confidence rows | **343/343**, none with a missing `selected_source` |
| every cited source file exists | **343/343** |
| every cited source hash matches its `source_sha256` | **343/343** |
| precision split | **122 exact**, **221 at 3 decimals** |
| provenance groups | baseline 88, chunk1–8 ×30 each, chunk9 15 = 343 |

So the previously reported "343 canonical complexes / 343 confidence rows / 0 missing / 0 conflicting"
**reproduces**. The 3-decimal majority is a pipeline-precision property, not a loss of identity: the
row, source file and hash are recorded for each, and the rebuild report already treats 3-decimal
values as validated rather than inferred.

## What this does NOT establish (unchanged limitations)
1. **Domain-only / non-native.** These designs target the C4 apical construct as modelled; they are not
   a native-context prediction. Any claim about the native dimer is unsupported.
2. **Boltz port is still blocked.** The port failed validation at |ΔiPTM| **0.187** against a **0.03**
   rule. Nothing here re-tests or waives that; the rule is not relaxed and the port is not rerun.
3. **No new candidates.** `results/c4_apical_preview_20261024.csv` (20 rows + header, sha
   `f31774b1…`) remains the C4 fallback, untouched.

## Status
- C4 evidence: **reconciled, unchanged, read-only.**
- C4 GPU work: **not authorised before 08:00** (Kimi and Astra independently).
- C4 next step, for Ricardo only: decide whether to fund a stricter Boltz port protocol, or accept the
  domain-only limitation as the standing constraint on C4 claims.
