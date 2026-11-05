# C4 rebuild validation — 2026-10-24

**PASS: 343/343 designs resolved and scored; preview contains exactly 20 validated rows.**

Three-decimal ipTM is accepted pipeline precision. Exact values were preferred where available: **122 exact + 221 validated three-decimal values; zero missing or conflicting records.** The 255 chunk log records were independently reconstructed by Modal input ID, requiring one prediction name and one confidence record per input, matching function-call/task identity, input length, complete chunk membership, and the retained recovery index. All 34 overlaps with exact chunk values agree at three decimals. Conflicting or ambiguous identities/values cause the rebuild to fail. Per-design precision, sources, hashes, app/input IDs and log lines are retained. Chunk 3 is complete (30/30).

| Group | Designs | Exact | Three decimals |
|---|---:|---:|---:|
| baseline | 88 | 88 | 0 |
| chunk1 | 30 | 0 | 30 |
| chunk2 | 30 | 0 | 30 |
| chunk3 | 30 | 0 | 30 |
| chunk4 | 30 | 4 | 26 |
| chunk5 | 30 | 30 | 0 |
| chunk6 | 30 | 0 | 30 |
| chunk7 | 30 | 0 | 30 |
| chunk8 | 30 | 0 | 30 |
| chunk9 | 15 | 0 | 15 |
| **Total** | **343** | **122** | **221** |

**PDB coverage:** 343/343 canonical files in `results/c4_rebuild_20261024/remote_pdbs/`; no missing/unexpected identities or duplicate sequences/structures. Download hashes, single model, chains A/B, binder and configured target sequences, finite coordinates and full backbones were revalidated. The 20 stale local copies were excluded and left unchanged. The configured target remains 154 residues; this rebuild does not resolve the prior report’s 195-residue target-context discrepancy.

**Execution:** ran `scripts/score_acid_off.py` against only the canonical directory, with the original `results/c4_acid_combined_refold.json` and the new combined confidence JSON; then ran `scripts/build_submission_v9_acid_off.py --max 20` with an explicit preview output. All 343 scored records preserve confidence and original refold metadata. Preview columns exactly match the official template (`name,sequence,molecule_class`); all 20 IDs and sequences are unique and match source metadata and canonical structures. The actual builder T1 threshold (>2) was preserved.

**Selection comparison:** 20 existing → 20 preview rows (count change +0); 6 retained, 14 added, 14 removed. Tiers: existing {'T1': 18, 'T2': 2}; preview {'T1': 20}. Existing-ID tiers are recalculated from preserved pre-rebuild scores; the CSV has no tier field. The final historical scored pool selects 17/20 existing IDs, so it is not treated as the exact CSV-generation snapshot. ID/tier-only selections and changes are in `selection_comparison.json` (no sequences).

**Outputs** (under `results/c4_rebuild_20261024/`):

- `combined_boltz_validated.json` — complete combined Boltz confidence input with precision/source per design.
- `confidence_provenance_validated.json`, `coverage_validated.json` — evidence and current coverage.
- `c4_acid_off_scored.json`, `submission_v9_preview.csv` — rebuilt scores and 20-row preview.
- `selection_comparison.json`, `rebuild_validation.json`, `preserved_original_files.json` — validation and integrity.
- `score_acid_off_validated.log`, `build_submission_v9_preview.log`, `finish_rebuild.py` — execution logs and reproducible procedure.

All 465 snapshotted original files remain byte-for-byte unchanged. Earlier exact-only reports/artifacts are preserved as historical records; `coverage_validated.json` supersedes their incomplete-coverage gate under the corrected precision policy. No GPU jobs, remote actions, submissions, or messages were initiated. Original `results/submission_v9.csv` SHA256: `31d98a4133c558e1a3a9f582a607383bca8d7aad1b8bd820e684cb8fa231eadd`.
