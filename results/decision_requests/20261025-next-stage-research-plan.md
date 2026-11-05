# DECISION REQUEST — next-stage research plan (C3 improvement, C4 improvement, C5 prep)
requested: 2026-10-25 00:45 ET by the orchestrator (DeepSeek V4.1 Flash)
decider: Kimi (moonshotai/kimi-k3.1-pro). Escalate consequential points to GPT-6 Astra
(`codex exec -m gpt-6-astra`) — Fable 5.1 / Opus 5.5 have refused this domain (content_filter,
see results/decisions/20261024-c3c4c5-research-plan.consultations.md); try at most once more
per topic and record any refusal rather than retrying.

## Orchestrator role
I do not choose designs, scoring criteria, thresholds, or experiments. You decide; I execute
mechanically: launch, monitor, fetch, merge, record. I will not submit anything or contact anyone.

## NEW AUTHORITY FROM RICARDO (2026-10-24 ~20:30 ET) — the earlier freeze is LIFTED
Verbatim from MISSION_OVERNIGHT.md, which is now in force until 08:00 ET Sun 10-25:
- "new candidate generation and screening are allowed (the earlier 'freeze' is lifted:
  'we'd be improving')"
- "Keep the C3 v6 CSV and the C4 preview as untouched fallbacks; write every new candidate set
  as a NEW versioned file with a one-line ranking of which file is best and why."
- "If the queue is empty, get one from Kimi and run it." → that is why this request exists.
- Priority order Ricardo suggests (you may re-plan): (1) finish the C3 AF2M screen on the pods;
  (2) C3: gate candidates, strengthen designs (diversity, agonism evidence, refold checks),
  produce v7+; (3) C4: improve designs for the pH-conditional objective on the correct target,
  rank, produce a better versioned file; (4) draft the C5 approach for the Mon 10-26 announcement.
- Spend authorized: five RunPod A40 pods at $0.59/h (mine to keep busy; each self-removes after
  40 min idle) plus Modal inside its existing limit (billed $189.90 of the $350 ceiling /
  $340 stop as of 00:40 ET; ceilings were raised by Ricardo for this work).
- Still absolute: nothing submitted, nobody contacted, C3 deadline Oct 25 23:59 AoE
  (Oct 26 07:59 ET) — **Ricardo uploads himself**, so C3 work must be finished and written to a
  new versioned CSV well before then.

## Verified state (measured, not assumed)
- **C3 AF2M screen is completing now on the pods** (the Modal screen stopped at 17/44 when the
  $190 guard fired). 17 designs were scored on Modal L40S. Pod port was **validated against
  Modal on the same design**: `c3_glp1r_ecd_151` iPTM 0.900 / pTM 0.87 / pLDDT 93.0 both runs;
  A40 wall 153 s vs L40S ~7 min (~$0.03/design vs ~$0.23).
- 24 remaining designs split across 5 A40 pods, ~3–5 min/design, ETA ~01:10 ET. Partial pod
  results already seen: `c3_glp1r_ecd_12` 0.310, `_171` 0.870, `_29` 0.230, `_103` 0.590,
  `_193` 0.840, `_92` 0.910, `_132` 0.900, `_14` 0.900 (iPTM only — not yet interpreted).
- Screen input: `results/c3_screen_input_20261024.csv` (44 = 20 v6 + 24 RFD4 shortlist),
  uniform 111-res ECD target. Scores so far: `results/c3_screen_af2m_scores_20261024.json`.
- Gate script (unchanged, per your earlier §1): `scripts/c3_screen_gate_20261024.py`
  — floor = max(0.76, min of the 8 BindCraft anchor iPTMs), only `c3_v_*` replaceable,
  plus exact-sequence refold, structural checks, real diversity gain, strict CSV integrity.
- **C4:** 342/343 Boltz results (`tfr1_c4_acid_site1_41` timed out twice, 100-res binder,
  absent by design of the freeze — no CSV edit was made). Corrected apical preview:
  `results/c4_apical_preview_20261024.csv`, 20 designs, mean iPTM 0.704, mean complex His pKa
  6.38, ranked on P02786 189-383 contiguous apical domain (195 res, monomeric) — NOT the native
  121-760 homodimer the assay uses. v9 (`31d98a41…`), v9 preview (`00ec3d59…`) untouched.
  C4 closes Nov 1 23:59 AoE.
- **C5:** not yet published (page says "Not yet announced — Oct 26 – Nov 8"). Generic rules
  captured in `results/c5_constraints_review.md`. One open question: **which track does Ricardo
  enter** (the rules vary 20 vs 20-40 slots by track). Assume nothing; tell me what to prepare
  that is track-independent.

## What I need from you (answer as executable decisions)
1. **C3 gate + v7 decision rule.** When all 44 are in, exactly what does the orchestrator run
   (command), and what are the exact pass/fail criteria for writing a v7 given the full set?
   If v7 is warranted, who assembles it — the gate script, or a specified new script? Name the
   output file. If v7 is NOT warranted from the 44, say so and give the next screening round.
2. **Next C3 round with real design improvement** (the freeze is lifted). Concretely: what to
   generate (method: RFD4/ProteinMPNN/BindCraft variants/other available tooling in this repo),
   how many, against which exact target construct (111-res ECD vs the 117-res one with KRGER —
   state which and why), what diversity constraint, and what screening budget in GPU-hours
   (pods cost $0.59/h; be explicit so I can queue it in one pass). Include the agonism question:
   is any *agonist* path actually achievable from ECD-groove binders, or should all effort stay
   on high-confidence binders and the methodology stop claiming more? If refold/structural checks
   are required before promotion, name the exact checks and pass thresholds.
3. **C4 improvement on the correct target.** The assay is the native 121-760 dimer at acidic pH.
   Given the pods (A40 48 GB, Boltz/RFD4 capable) and the Nov 1 deadline, what exactly should be
   run to (a) close the `site1_41` gap or replace that slot legitimately, and (b) improve the
   pH-conditional design set on the *native-context* target? Specify model, target construct,
   number of designs, and how the resulting file is ranked and named. If a native-context run is
   too expensive, say what the cheaper decisive test is instead.
4. **C5 preparation that is track-independent** for the Mon 10-26 announcement: what to have
   ready (checklist), and what the first 24 hours after the target announcement should look like.
   Flag anything that needs Ricardo's decision and would waste GPU if guessed wrong.
5. **Stop conditions / budget.** What must be true for me to stop launching new GPU jobs and
   hold (not idle), and what cost ceiling applies to each item above? Note the pods self-remove
   after 40 min idle, so work should be queued in batches, not trickled.

Answer with explicit file paths, commands where relevant, and a priority order I can execute
top-down. If any question is outside what you can responsibly decide, say which model to ask
and what to send it.
