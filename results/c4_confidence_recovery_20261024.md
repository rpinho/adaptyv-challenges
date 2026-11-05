# C4 exact-confidence recovery — 2026-10-24

**Incomplete: 122/343 exact ipTM values verified; 221 remain missing. Scoring and preview creation stopped.** All 343 canonical PDB identities and sequences passed validation. `results/submission_v9.csv` was preserved byte-for-byte. No predictions, remote compute jobs, submissions, or messages were initiated.

| Group | Expected | Exact ipTM | Missing exact ipTM |
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

## Exact sources and recovery

- Validated `results/c4_acid_scored_all88.json`: **88** baseline values, unique identities, exact sequence matches, finite numeric ipTM in [0,1]. Cross-checked overlapping original Boltz JSONs and historical scored files; no exact-value conflicts.
- `results/c4_acid_boltz2_batch1.json`: **30** full-precision records whose names and sequences match **chunk 5**, despite the batch filename. Original JSON rows and source hashes are recorded in `confidence_provenance.json` and `source_manifest.json`.
- **Four** exact chunk-4 values recovered from a prior audit's preserved tool output: `/Users/ricardo/.Codex/sessions/2026/10/24/rollout-2026-10-24T11-07-55-01a16e74-4284-7b23-89bd-910372280f6e.jsonl`, line 151. The output explicitly reported `CHUNK4 extra exact ipTM`. Preserved verbatim as numeric data in `chunk4_exact_preserved.json`; all four names belong to chunk 4 and all four values agree when rounded with that chunk's final stopped-app logs. These values were also documented in the completed pipeline audit.
- Checked committed historical JSONs (`git show HEAD:...`), the local session-recovery snapshot, relevant Claude session/tool-result history, Codex audit transcripts, local scratch/shell logs, and backup/cache locations. Historical score data and the recovery snapshot added corroboration but no further exact values. Search inventories are retained in this directory. This was a bounded search, not a claim that no other archive can exist.

## Chunk 3 and Modal evidence

Recovered stopped-app logs for **15** historical Boltz apps using the installed SDK's read-only log endpoint. Chunk 3 is **`ap-KhX61DV5a8nXciK8pO8oJY`**, created **2026-10-24 10:22:26-04:00**. Its logged name set matches all **30/30** chunk-3 inputs, with one prediction name and one confidence line per Modal input ID. The local `/tmp/chunk3.log` remains absent.

The prediction code prints `ipTM` with **three decimal places**. Per-input retained logs recover rounded evidence for all **255** chunk designs, including low-confidence designs omitted from local summaries; these values are saved separately in `rounded_evidence_excluded.json`. **No rounded value was promoted to an exact value.** Chunk 3 therefore remains **0/30 exact**. The numbered chunk 1/2/4 JSONs are known rounded reconstructions, and chunk 3/5/6/7/8/9 JSONs contain foreign baseline rows; these were excluded as recovery sources.

The **11** retained function-call IDs were queried with `FunctionGetOutputs`, `timeout=0`, and `clear_on_success=False`; all returned `NotFoundError`. The SDK's old `AppGetObjects` endpoint returned `UNIMPLEMENTED`; no app was started or changed. Existing `rfd4-runs:boltz2_c4_acid/` contains **343 PDBs and no confidence JSONs**. The `boltz2-cache` root contains model weights and molecular-component cache data, not persisted prediction output directories. A recursive cache listing was capped at 10,000 entries; its root listing is retained.

The earlier audit's 305 recovered entries included **183 rounded values**. Under this task's exact-only rule those are excluded. `verified_boltz.json` contains only the 122 values supported by full-precision historical records.

## Structure, coverage, and conflict validation

The expected pool is the disjoint union of baseline 88 and chunks 1–8 × 30 plus chunk 9 × 15, exactly the **343 PASS** records in the 387-record combined refold map. A fresh **read-only SDK snapshot** of all 343 existing volume PDBs is in `remote_pdbs/`. Every selected PDB has one model, exactly chains A/B, exact binder identity and sequence, the configured target sequence, finite coordinates, and complete N/CA/C/O backbones. No missing or unexpected PDB identities, duplicate binder sequences, duplicate structures under different names, or exact-confidence conflicts were found.

There are **20 stale top-level local PDB copies** with content differing from the canonical downloaded pool, all in chunk 4. Their paths, hashes, and resolution are recorded in `pdb_validation.json`. Every selected snapshot PDB matches an existing local copy; the 20 stale copies were left untouched and excluded. Existing local duplicate chain sequences were also checked. The CLI directory download produced a single-file destination artifact; it was rejected, and all canonical snapshot files were subsequently read individually with the SDK and hashed.

Missing exact-confidence names, grouped counts, the final-app mapping, and the scoring gate are in `coverage.json`. **No acid-OFF scoring or submission preview was run.** Full-pool confidence completeness is not established.

## Outputs

All rebuild artifacts: `results/c4_rebuild_20261024/`.

- `verified_boltz.json` — **122** exact, identity-matched records; intentionally partial.
- `coverage.json` — **221** exact-value gaps; `scoring_permitted=false`.
- `confidence_provenance.json`, `source_manifest.json`, `chunk4_exact_preserved.json` — exact-value evidence and hashes.
- `pdb_validation.json`, `remote_pdb_manifest.json`, `remote_pdbs/` — 343 validated canonical complexes, hashes, and resolved stale-copy conflicts.
- `modal_recovery_index.json`, `ap-*_logs.jsonl`, `rounded_evidence_excluded.json`, `rejected_metadata.json` — retained recovery evidence and exclusions.
- `submission_integrity.json` — original submission SHA256 **31d98a4133c558e1a3a9f582a607383bca8d7aad1b8bd820e684cb8fa231eadd**, unchanged.

Recovery/validation scripts are retained in this directory. Neither `c4_acid_off_scored.json` nor `submission_v9_preview.csv` was created there.
