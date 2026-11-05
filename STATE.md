# C4/C5 Orchestrator State

**Session:** adaptyv-c4-71 (Opus 4.6, orchestrator-only)
**Last updated:** 2026-11-01 13:56 UTC

## C4 Re-score: COMPLETE

- 342/342 score files pulled to `results/c4_full_rescore_20261027/pulled_scores/`
- 1 missing score: site2_96 (not site1_112 — site1_112 was recovered by bg_recovery)
- All 6 pods TERMINATED (2026-10-28 23:46 UTC) — disks were wiped on restart (no network volumes), PDBs unrecoverable
- v12 falls back to sequence-based clustering (no TM-align without PDBs)
- iPTM range: 0.79-0.89 (correct homodimer construct)
- Fable finding: within-design iPTM variance (mean 0.025) > between-design signal (sd 0.015)
- 66/340 designs have sequence liabilities; v10's site1_43 has HHHHHH

## Submissions

| Version | Date | Designs | Strategy | Status |
|---------|------|---------|----------|--------|
| v10 | Oct 28 11:00 UTC | 20 | Pure iPTM top 20 | SUBMITTED |
| v11 | Oct 29 12:47 UTC | 20 | Consistency filter, zero v10 overlap, liability-clean | SUBMITTED |
| v12 | Oct 30 12:53 UTC | 20 | Site+length backbone diversity (sequence-based) | SUBMITTED |
| v13 | Oct 31 13:04 UTC | 20 | REBUILT: 9 high-iPTM inconsistent + 11 pH-weighted (adversarial review) | SUBMITTED |
| v14 | Nov 1 13:56 UTC | 20 | REBUILT: farthest-first + length-reserve bins (adversarial review) | SUBMITTED, DESIGNATED |

- v11 CSV: `results/c4_submission_v11_20261029.csv` (Fable-built, validated)
- v11 audit: `results/c4_submission_v11_20261029.audit.json`
- v12 CSV: `results/c4_submission_v12_20261030.csv` (site+length diversity, consistency-filtered)
- v13 CSV: `results/c4_submission_v13_20261031.csv` (pH-switch / ionizable residues weighted)
- v14 CSV: `results/c4_submission_v14_20261101.csv` (max sequence diversity, farthest-first)
- v12-v14 audit: `scratchpad/c4_v12_v13_v14_audit.json`
- Submissions ACCUMULATE (verified from terms + PeptAI). Never resubmit a design.
- C4 deadline: Nov 1 23:59 AoE (= Nov 2 11:59 UTC)

## Pending Jobs

| Job | Owner | Status | Next action |
|-----|-------|--------|-------------|
| PDB extraction | FAILED | Pod disks wiped on restart (no network volumes). All 6 pods terminated. Saved ~$1.9/day disk fees. |
| v12-v14 CSV generation | DONE | 100 designs across v10-v14, all disjoint, all validated. |
| v11 submission | This session (browser) | WAITING | Submit at Oct 29 12:41 UTC via Chrome. CSV ready: results/c4_submission_v11_20261029.csv |

## C5 — Active (deadline Nov 8 23:59 AoE = Nov 9 11:59 UTC)

### Current Submission
**v25 on Proteinbase** as Submission 8 (DESIGNATED), Nov 5 ~16:42 UTC / ~11:42 AM ET.
- Confirmation: https://proteinbase.com/collections/anthropic-adaptyv-protein-design-competition-submission-8-l8k87rAaN1
- #1: c5_r40_f_r0 delta=+0.274, iptm=0.903, combined=5.475
- #2: c5_r40_l_r0 delta=+0.277, iptm=0.720, combined=5.143
- #3: c5_r47_i_r2 delta=+0.272, iptm=0.748, combined=5.167 (NEW in v25)
- 24h cooldown: next submission window ~16:42 UTC Nov 6

### R62 — Epitope conditioning: CLOSED
0/120 selective. WT mean=0.726 (worse than unconditioned baseline). binding_types on C:4..8
did not redirect contacts. Worse WT than baseline, not just same → closed at round 1.

### R63 — Nanobody-anything: CLOSED
0/73 selective. WT mean=0.828 (worst of all approaches). Nanobody scaffold binds MHC groove
even more strongly than miniproteins. Closed at round 1.

### R9 nanobody selectivity: ARTIFACT
Original R9 scores (delta +0.666, WT=0.174) do NOT replicate with opendde-abag.
Verified: nb_r2 delta=-0.049, nb_r5 delta=+0.051. The scoring model used in R9 was different.

### Stop Rule (binding)
Three rounds that fail the same way end that approach.
- **de novo maxlong 230-250aa: STOPPED** (R41-R60, 20 dry rounds, WT>0.5 wall)
- **varied length ranges: STOPPED** (R61: worse than maxlong)
- **Boltz2 triage: DONE** (R47 candidate verified and included in v25)
- **epitope conditioning: STOPPED** (R62: worse WT than baseline)
- **nanobody-anything: STOPPED** (R63: worst WT of all approaches)
- **Remaining:** peptide-anything, shorter miniproteins (80-150aa), seed-controlled draws

### Three-Day Plan (Nov 5-8)
- Nov 5: v25 submitted (pending Ricardo's T&C click). R62+R63 both closed.
- Nov 6: R64 peptide-anything, R65 short miniproteins (80-150aa)
- Nov 7: Protect — re-verify v25 top 3 with fresh Boltz2
- Nov 8 by 6 PM ET: Final submission

### Pipeline Summary (R23-R63)
40 rounds, ~16,200 jobs, ~$344 spent, ~$666 remaining.
3 productive rounds: R23 (4 entries), R35 (#1 at the time), R40 (current #1).
Key finding: WT>0.5 wall. Every design since R23 has WT>0.5. Combined score (delta×10 + G12D + iptm×2) is the ranking metric.
New approach: epitope conditioning to direct contacts to the peptide mutation site.

### API
Base: https://api.japanfold.aiand.com, Bearer from ~/.config/japanfold/key
Design: POST /v1/designs {name, protocol:"protein-anything", spec:<yaml entities>, params:{num_designs:10}}
Predict: POST /v1/predictions {model:"opendde-abag", name, input:<fasta>}
YAML format returns 400 — use FASTA only for predictions.

### Target Sequences
HLA (276aa): MAVMAPRTLLLLLSGALALTQTWAGSHSMRYFFTSVSRPGRGEPRFIAVGYVDDTQFVRFDSDAASQRMEPRAPWIEQEGPEYWDQETRNVKAQSQTDRVDLGTLRGYYNQSEAGSHTIQIMYGCDVGSDGRFLRGYRQDAYDGKDYIALNEDLRSWTAADMAAQITKRKWEAAHVAEQLRAYLEGLCVEWLRRYLENGKETLQRTDAPKTHMTHHAVSDHEATLRCWALSFYPAEITLTWQRDGEDQTQDTELVETRPAGDGTFQKWAAVVVPSGQEQRYTCHVQHEGLPKPLTLRWE
B2M (99aa): MIQRTPKIQVYSRHPAENGKSNFLNCYVSGFHPSDIEVDLLKNGERIEKVEHSDLSFSKDWSFYLLYYTEFTPTEKDEYACRVNHVTLSQPKIVKWDRDM
G12D: VVVGADGVGK / WT: VVVGAGGVGK

### Results Ledger
~/.local/share/research-harness/lanes/c5/RESULTS.jsonl — log every round.

## Budget

- RunPod: ~$190 remaining (for C5 compute)
- C4 pods: all terminated (23:46 UTC Oct 28), no more disk fees
- Claude weekly limit: conserve through orchestrator-only pattern

## Expert Decisions (Oct 28 consultation)

Model rankings: Opus 5.5 > Fable 5.1 > Astra > Kimi

Key decisions (weighted consensus):
1. v11: 20 designs, consistency filter, zero v10 overlap (Fable)
2. v12-v14: different strategy per day, TM-align clusters, never resubmit (all)
3. PDB extraction: do it, saves $22 (Fable quantified)
4. C5: triad screen with Japanfold, specificity before affinity (Fable + Astra)
5. Molecule class diversification for v14 (Fable)
6. iPTM ranking is noise — consistency filter > peak score (Fable)

## X Lane

- Adaptyv post live: tweet 2115506602857967847
- Moritz DM replied with Japanfold credits (delivered to C5)
- 3 adaptyv technical questions: no replies after 24h
- DM log: `~/.local/share/x-engage/log.jsonl`
- **X API budget rule (Oct 29):** browser for all reads, API only for writes (likes/follows/replies unbilled). Cycle at $50/$60.

## Event-watch

- c4 job: COMPLETE (no waiter needed)
- c5 job: configured, push on
- Next wake source: ScheduleWakeup for v11 submission window

## Wake Schedule

## Research Cycle (2026-10-30)

- Literature review: 8 papers on binder ranking metrics (scratchpad/c4_literature_review_20261030.md)
- Community scan: 14 competitor pipelines analyzed (scratchpad/c4_community_scan_20261030.md)
- Adversarial review: provenance-tagged attack on our scoring (scratchpad/c4_adversarial_review_20261030.md)
- IDEAS.jsonl: 18 ideas, all externally sourced with provenance
- Key findings: iPTM/pTM r=0.985 (same metric), consistency filter is length filter (r=-0.73), field uses ipSAE not iPTM
- v13/v14 REBUILT on evidence: inconsistent high-scoring designs included, length coverage enforced
- Bug fixed: site1_14 had 7 models (truncated to 5), site1_87 has only 2 models (excluded)
- Boltz-2 ipSAE rescoring: proposed to Ricardo ($5-10, ~4h, pending approval)

## Immediate TODO
1. ~~PDB extraction~~ FAILED — pods wiped, all terminated (23:46 UTC Oct 28)
2. ~~v12-v14 CSVs~~ DONE — v13/v14 rebuilt 2026-10-30 based on adversarial review
3. ~~Submit v11~~ DONE — submitted Oct 29 12:47 UTC, novelty 20/20 passed
4. ~~Submit v12~~ DONE — submitted Oct 30 12:53 UTC, novelty 20/20 passed, DESIGNATED
   - Confirmation: https://proteinbase.com/collections/anthropic-adaptyv-protein-design-competition-submission-3-V3pzjcWVcF
5. ~~Submit v13~~ DONE — submitted Oct 31 13:04 UTC, novelty 20/20 passed
6. ~~Submit v14~~ DONE — submitted Nov 1 13:56 UTC, novelty 20/20 passed, DESIGNATED (Submission 5)
   - Confirmation: https://proteinbase.com/collections/anthropic-adaptyv-protein-design-competition-submission-5-sKFzE4rSRq
   - N-glyc sequon note: 5/20 designs carry NXS/NXT, flagged in methodology per Opus 5.5 expert review
7. **C4 COMPLETE** — 100 designs across v10-v14, all disjoint, all submitted. Deadline Nov 1 23:59 AoE.

## Key files
- v11 CSV: results/c4_submission_v11_20261029.csv (20 designs, validated, ready)
- v12 CSV: results/c4_submission_v12_20261030.csv (20 designs, validated, ready)
- v13 CSV: results/c4_submission_v13_20261031.csv (20 designs, validated, ready)
- v14 CSV: results/c4_submission_v14_20261101.csv (20 designs, validated, ready)
- v11 audit: results/c4_submission_v11_20261029.audit.json
- v12-v14 audit: scratchpad/c4_v12_v13_v14_audit.json
- All scores: scratchpad/c4_all_scores.json (336 designs)
- All sequences: scratchpad/c4_binder_sequences.json (342 designs)
- Build script: scratchpad/build_v12_v14.py
- Fable's v11 selection: consistency filter (5-model mean iPTM >= 0.826, range <= 0.03), zero v10 overlap, liability-clean
- Scratchpad: /private/tmp/claude-501/-Users-ricardo-dev-adaptyv-c4/05dba0a8-8f83-41a9-b82c-9c80715dca59/scratchpad/

## Wake schedule
- CronCreate 4489c370: Oct 29 08:28 EDT (12:28 UTC) — v11 submission (FIRED)
- CronCreate 882aa710: Oct 30 08:47 EDT (12:47 UTC) — v12 submission
- CronCreate 2b1631b0: Oct 31 08:47 EDT (12:47 UTC) — v13 submission
- CronCreate 4602f12a: Nov 01 08:47 EDT (12:47 UTC) — v14 submission (final, then designate active)
- Codex for engineering-only jobs, domain reasoning stays here
- event-watch c5 job configured (push on)

---

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

### Approach Summary (R62-R65, Nov 5)
All new approaches WORSE than baseline maxlong 230-250aa:
| Approach | WT mean | Best delta | vs baseline |
|---|---|---|---|
| maxlong 230-250 (baseline) | 0.66 | +0.274 | BEST |
| epitope C:4..8 (R62) | 0.726 | +0.226 | worse |
| nanobody 100-130 (R63) | 0.828 | +0.120 | worse |
| peptide 30-60 (R64) | 0.890 | +0.109 | worst |
| short 80-149 (R65) | 0.815 | +0.104 | worse |

**Conclusion:** v25 portfolio is likely near-optimal. WT>0.5 is a fundamental property of opendde-abag on this target. Shorter binders are WORSE (more groove contact relative to size). Remaining budget ($650) should be conserved for Boltz-2 re-verification of top 3 on Nov 7.
