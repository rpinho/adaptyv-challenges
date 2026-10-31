## Scheduled-tick audit, 2026-10-31 18:44 UTC (codex lane, adopted per Ricardo)

The tick fired into the **archived** codex orchestrator thread. Its premise (C3 deadline, C3
blocking decision) is a week stale — C3 was submitted 2026-10-26 and this lane was archived the
same day. Three things were found and two fixed.

### 1. FIXED — tick scheduler re-armed itself on reboot

`ADAPTYV_THREAD` still points at the archived thread `01a173a5` (see `~/.config/codex-lanes.conf:36`).
`com.ricardo.codex-adaptyv-tick` has `RunAtLoad: true`, so the 2026-10-31 reboot re-armed it after I
had unloaded it on 2026-10-26. Log evidence: a 4-day gap, then
`2026-10-31 14:29:04 skip: cannot read orchestrator turn state` and a queued cycle at 14:44.

Action taken: `RunAtLoad` set to **false** and the job unloaded. It will not return on reboot.
Plist backup at `/tmp/tick.plist.bak.1793472289` (temporary). Nothing else on the machine depends
on this tick. To revive deliberately: retarget `ADAPTYV_THREAD` first, set `RunAtLoad` back to true,
then `launchctl load`.

### 2. FIXED — v14 verified independently of the lost scratchpad

`scratchpad/` was in `/private/tmp` and was **wiped by the reboot**. Gone: `build_v12_v14.py`,
`c4_v12_v13_v14_audit.json`, `c4_all_scores.json`, `c4_binder_sequences.json`, the literature
review, community scan and adversarial review. The CSVs and all 342 pulled score files survive, so
v14 was re-verified directly against scores:

- 20/20 rows have a `scores.json`; **0 missing**
- 5/5 models present for every row (no truncated design)
- best iPTM min 0.80 / median 0.83 / max 0.84; pLDDT 88.1-90.3
- 15/20 meet the v11 consistency rule (range <= 0.03); the other 5 are 0.04 and were chosen under
  the v14 diversity brief rather than the consistency brief — not a violation, just a different rule
- lengths 64-99, inside the 10-250 AA rule; no duplicate names

**Never-resubmit rule verified across all five CSVs:** v10/v11/v12/v13/v14 = 100 rows,
**100 distinct canonical sequences, 0 pairwise overlap, 0 duplicates**. Designing this check before
v14 goes in was worth doing — a collision would have been unrecoverable.

### 3. FLAGGED — 5/20 v14 rows carry an N-glycosylation sequon

`N[^P][ST]` hits in site1_157 (NDT), site2_182 (NLS, NLT), site2_140 (NVT), site2_69 (NDS),
site1_197 (NGS). No poly-His, no low-complexity runs; v10's HHHHHH defect did not recur.

**This is not a proved defect.** A sequon is not a glycan, and the peroxisomal routing pathway may
not glycosylate a designed binder at all. But v11's brief excluded liabilities and v14 was selected
on diversity, so this is a genuine **difference in rule between submissions**, not clearly an error.
Ricardo's call: submit as-is, or swap 5 rows for clean alternates from the surviving 342 scores.
The 15 clean rows are a viable submission on their own if a smaller set is acceptable.

### Still true

- C4 deadline **2026-11-02 11:59 UTC** (Nov 1 23:59 AoE). At audit time: **1d 17h** remaining.
- C3 frozen artifacts verify **4/4 OK**; no `ALARM_*`.
- Both codex workers dormant since 2026-10-26 (last log writes 11:00:46 / 11:00:50). Not restarted.
- $0 GPU spent by this audit. No submission, no upload, no organiser contact.
