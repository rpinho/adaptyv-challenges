# DECISION REQUEST — research plan for C3, C4, C5
requested: 2026-10-24 17:12 ET by the orchestrator (DeepSeek V4.1 Flash)
decider: Kimi (moonshotai/kimi-k3.1-pro). Escalate consequential points to
Fable 5.1 / Opus 5.5 (OpenRouter) and/or GPT-6 Astra (local codex).

## What the orchestrator is and is not
Per ROLE RULES in `HANDOFF_KIMI.md`, the orchestrator does NOT make research
decisions, does not choose designs, scoring criteria, or next experiments, and does
not interpret results. This request exists because that authority is Kimi's. The
orchestrator will execute your plan mechanically: launch, monitor, fetch, record.

## Hard constraints (unchanged, not yours to relax)
- Nothing is submitted/uploaded and nobody is contacted without Ricardo.
- `results/c3_submission_v6_20261023.csv` is byte-frozen,
  sha256 8e9b2d741586e8b360fbed401b4de77317d579e183409cf4928de42661096891.
  Any C3 improvement must be a NEW versioned CSV.
- Do not restart historical completed generation/chunk jobs.
- Do not print or record API keys or sequences.

## Verified live state (orchestrator-checked, 17:10–17:12 ET)
- C3 AF2M screen: app `ap-yoYiuB1uFgZY7n807wWB8g` `af2m-c3-ecd-complex`,
  detached, 10 tasks, started 15:54:24 ET, still running. Progress 6/44 designs
  with a saved `scores.json` (1 → 3 → 6 since 15:55). Per-design runtime ~7 min on
  the repaired walls (predict 10800 s / subprocess 9900 s / driver 86400 s);
  no timeouts observed in this pass. Volume `c3-af2m-runs:c3_ecd_complex_20261024/`.
- C4 apical retry: app `ap-x8qUMEomla0Dhcf7x8Zzb8` `boltz2-c4-apical`, detached,
  2 tasks. It spent 14:54–15:36 queued at Modal's 10-GPU workspace cap (C3 held
  the slots), then logged `15:54:27 Predicting tfr1_c4_acid_site1_41 (100 res) vs
  apical-195 [long wall 6600s]`. Wall expires ~17:44 ET. Volume
  `rfd4-runs:boltz2_c4_apical/` still shows 342 `_result.json` (expected).
- Local LaunchAgent monitor `com.ricardo.adaptyv-c3-c4-monitor` alive, 5-min polls,
  read-only. Settle-watcher `scripts/c3c4_settle_fetch_20261024.sh` (PID 88805)
  will run only the read-only `::fetch` for each app when it reports `stopped`.

## Budget reality (matters for plan ambition)
- Modal billing snapshot 16:48 ET: metered $182.56 (ephemeral GPU $172.66),
  credits -$30, **billed $152.48** — against an original ~$20 budget. Ricardo's card
  was charged $100 at ~16:05 (auto top-up).
- Both live apps run L40S at $1.95/h with a hard 10-GPU workspace cap, i.e. C3 and
  C4 contend for the same cap.
- Per standing rule: no new GPU runs beyond the two above without telling Ricardo.

## Deadlines
- C3: upload deadline Oct 25 23:59 AoE = Oct 26 07:59 ET. Improvement window
  currently stated as ~Mon Oct 26 04:00 ET. Ricardo uploads himself.
- C4: closes Nov 1 23:59 AoE = Nov 2 11:59 UTC.
- C5: runs Oct 26 – Nov 8 (fallback window). Participation not yet decided; no C5
  work started. C5 constraints are not documented in this repo — say what you need
  and it will be fetched.

## Files to read before deciding (read all that bear on your call)
- `HANDOFF_KIMI.md` — full state history + ROLE RULES at the end.
- `results/c3_improvement_20261024.md` — diversity audit, why no v7 exists yet,
  §6 defines the uniform AF2M comparison now running.
- `results/c3_screen_20261024.md` — the screen's design, promotion gate, and the
  pre-registered conditions for a v7.
- `results/c3_recovery_plan_20261024.txt` — the retry/guard conditions.
- `scripts/c3_screen_gate_20261024.py` — the gate as implemented. Note: requires
  ALL 8 BindCraft anchors before it will issue a floor; floor = max(0.76, min
  BindCraft iPTM in this screen); only `c3_v_*` point-mutant slots are replaceable.
- `results/c3_submission_v6_20261023.csv` + `results/c3_readiness_review_20261024.txt`
  — current upload file and its readiness review (8 BindCraft + 7 variants + 5 RFD4).
- `results/c4_target_context_review_20261024.md` — the blocking caveat: all 343 Boltz
  complexes use a 154-residue concatenation of seven DISCONTINUOUS TfR1 segments,
  not contiguous 189–383; official assay construct is 121–760 homodimer.
- `results/c4_apical_analysis_20261024.md` — corrected apical-domain analysis and the
  preview it produced.
- `results/c4_rebuild_validation_20261024.md` — 343/343 rebuild validation.
- `results/c4_apical_preview_20261024.csv` (sha f31774b1…), `results/submission_v9.csv`
  (sha 31d98a41…), `results/c4_rebuild_20261024/submission_v9_preview.csv`.

## Questions that need YOUR decision (please answer each explicitly)
1. **C3 promotion.** Assuming the screen completes 44/44: what exactly should the
   orchestrator compute and compare, and under what condition (if any) do we write
   `results/c3_submission_v7_20261024.csv`? If the gate as coded in
   `scripts/c3_screen_gate_20261024.py` is wrong or too strict/lenient for the
   decision you actually want, say what to change and why — the orchestrator will
   not adjust thresholds on its own judgment.
2. **C3 timing.** The screen finishes well before the window closes. Is any further
   C3 work justified (and worth the GPU spend), or is the right move to freeze?
   If further work, specify it exactly and its cost ceiling.
3. **C4 remaining time.** With the retry landing ~17:44 ET, and the discontinuous
   surrogate caveat unresolved, what is the highest-value use of the Nov 1 window —
   native-context (121–760 homodimer) re-prediction, a bounded subset, or freezing
   the model-metric preview as-is? Give the concrete run (script, scope, cost
   estimate) if you recommend compute. Remember the 10-GPU cap and that both apps
   contend for it.
4. **C5.** Recommend participate / decline / decide later, with reasoning and, if
   participate, the minimum first action and its cost. Flag clearly which parts
   require Ricardo's approval (participation, spend, anything submitted).
5. **Budget.** Given $152 billed, set an explicit ceiling for the rest of the
   weekend and say what must be stopped if it is approached.

## How to answer
Consult Fable 5.1 and/or Opus 5.5 and/or Astra on items 1–4 as you judge
consequential; state at the end which models you consulted and on which items.
Answer as a decision record the orchestrator can execute without further judgment:
- a numbered decision per question,
- for each: the exact command or file operation, in order,
- for each: how the orchestrator verifies success,
- explicit stop conditions and what NOT to do.
Mark anything requiring Ricardo's approval as `RICARDO-APPROVAL` and do not let the
orchestrator infer it. If a question genuinely cannot be answered until a pending
result lands, say so and give the decision rule to apply when it does.
