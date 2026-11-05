# C3 runner repair — 2026-10-24

Changed only the two requested scripts and added this report.

- `modal_af2m_c3_complex.py`: raised `predict`'s Modal timeout from 3600 to
  **10800 seconds**, its ColabFold subprocess timeout from 3000 to **9900 seconds**,
  and the remote `main` driver timeout from 7200 to **86400 seconds** to accommodate
  multiple waves of long predictions plus consolidation. Updated the smoke docstring.
  Retained the existing single `predict` path for screen and one-off smoke retries;
  no separate `predict_long` or retry machinery was needed. Inputs, AF2 model,
  recycles, model count, MSA mode, ranking, seeds, target, volumes, prefix, output
  format, idempotence, and persistence code are unchanged.
- `scripts/c3_screen_gate_20261024.py`: replaced the invalid nested f-string with
  a separately formatted score list. The floor now remains unavailable until all
  **8 distinct v6 BindCraft anchors** have numeric iPTM scores. Incomplete results
  print partial scores and missing anchors, label the screen incomplete, and issue
  no `CLEARS` labels or positive gate. A missing score file also reports incomplete.
  The complete-screen floor remains `max(0.76, min(BindCraft iPTM))`; all existing
  refold/structural, CSV-integrity, redundant-slot, and diversity requirements remain.

Verification: `python3 -m py_compile modal_af2m_c3_complex.py scripts/c3_screen_gate_20261024.py`
passed with exit code 0 on local Python **3.9.6**. Bytecode was redirected to fresh
temporary directories, avoiding existing caches. Lightweight in-memory gate checks
passed for 0/8, 7/8, 8/8 anchor scores and a missing score file. The complete fixture
retained the 0.800 floor, accepting 0.810 and rejecting 0.790. Fixtures used existing
names and synthetic scores only; no result files or candidate sequences were written.
An exact source comparison confirmed the runner has only the timeout/comment/docstring changes.

The v6 CSV's before/after SHA-256 is identical:
`8e9b2d741586e8b360fbed401b4de77317d579e183409cf4928de42661096891`.
`HANDOFF_KIMI.md` also retains its original SHA-256. No existing result artifacts
were removed or rewritten. No Modal command, app stop/launch, submission, message,
candidate generation, CSV edit, unrelated test, or heavy job was performed.
The running first-pass app `ap-kyeVNsRjGqksuudoNSczUN` was left untouched; lifecycle
and deployment of these local repairs remain with the parent orchestrator.
