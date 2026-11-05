# C5 artifact naming & versioning convention (2026-10-24)

Rule from the mission: **every new candidate set is a NEW versioned file.** A previous version is
never edited, renamed in place, or overwritten — it is the fallback.

## Candidate sets
```
results/c5_submission_v<N>_<YYYYMMDD>.csv
```
- `N` is monotonically increasing per day and never reused.
- The date is the **date the file was written**, not the announcement date.
- Never re-write an existing `vN` with different content. If a gate fix changes a file, that is
  `vN+1`, and the one-line ranking entry says why.

## Supporting artifacts (same stem, distinct suffixes)
```
results/c5_v<N>_gate_report.json          # gate decision + per-candidate evidence
results/c5_v<N>_manifest.json             # validator output (hashes, reviewer, pass/fail)
results/c5_v<N>_provenance.md             # filled from c5_prep/templates/provenance_methodology.md
results/c5_v<N>_ranking.md                # one line per file: which is best and why
```

## Rank note (required)
Every new file gets exactly one line in `results/overnight_log.md` and in the handoff:
```
BEST: results/c5_submission_v3_20261028.csv — <why, in one clause>; supersedes v2 (<why not>)
```

## Integrity
- Record the sha256 of every written CSV at write time, in the same commit/append as the file.
- Before any promotion, re-verify the best file's sha256 and the previous version's sha256.
- A file whose hash is not recorded is not promotable.

## What is never done without Ricardo
Submitting, uploading, creating/using an account, contacting organisers, or writing to any
competition endpoint. This convention covers local files only.
