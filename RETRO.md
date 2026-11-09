# Retro

What I learned running the Adaptyv Bio protein design challenges (C3, C4, C5) as a data scientist with no wet-lab experience, using AI agents for most of the execution.

## The big one: we scored against the wrong construct

C4 designs target the transferrin receptor (TfR1) homodimer at acid pH. We generated 342 binders via RFdiffusion + ProteinMPNN. Then we scored them with AlphaFold2-multimer against a monomer construct instead of the homodimer (P02786-1, residues 121-760, two chains of 640 aa each).

Found the mistake after the first submission. Had to rescore all 342 designs from scratch. Six A40 GPUs, 45 hours. The scores came back different. Some designs that ranked high against the monomer dropped against the dimer.

The fix was straightforward but expensive. The lesson is obvious but I still missed it: verify the target construct before you start scoring. Read the challenge page, check the PDB, count the chains.

## iPTM ranking is noise

This was the most useful thing we found. Fable (Claude) computed the actual statistics from the 5-model ensemble scores across all 336 designs:

- Within-design model variance: mean 0.025 iPTM
- Between-design standard deviation: 0.015 iPTM

The noise is bigger than the signal. Ranking designs by best iPTM is basically random. Two independent AF2m runs of the same design will disagree more than two different designs differ from each other.

What works better: a consistency filter. We used 5-model mean iPTM >= 0.826 AND 5-model range <= 0.03. This selects for designs where all models agree on the binding pose, not designs that got lucky on one model.

I don't know how general this is. It might be specific to our construct (1280 aa receptor is big for AF2m). But it changed how we built every submission after v10.

## RunPod without network volumes loses data

We stopped 6 pods to save GPU costs while keeping the disks for later PDB extraction. When we restarted them, the disks were empty. The overlay filesystem came back fresh. All PDB structure files were gone.

The scores survived because we'd been pulling them to the local machine every 5 minutes with a background script. The PDBs were only on the pods.

If I need to keep files across pod stop/start cycles, I need a network volume. The container disk on a stopped pod is not reliable storage, at least on EU-SE-1.

## ColabFold 1.5.5 on RunPod: three bugs that cost hours

1. **cuDNN version**: JAX 0.4.23 needs cuDNN 8.9, not cuDNN 9. The newer version ships with the RunPod PyTorch image. JAX silently falls back to CPU. You don't notice until you check GPU utilization. Fix: `pip install nvidia-cudnn-cu12==8.9.7.29`.

2. **dm-haiku version**: dm-haiku 0.0.17 calls `jax.core.take_current_trace` which doesn't exist in JAX 0.4.23. Every design fails in 4-5 seconds with an AttributeError. Fix: `pip install "dm-haiku==0.0.10"`.

3. **Rename crash**: ColabFold crashes during final PDB rank-rename (batch.py line 533, FileNotFoundError). All 5 models actually completed, scores and PDBs are saved. But the exit code is 1 and the status is "error". We wrote a recovery daemon that runs every 2 minutes and converts these false errors to proper score files.

None of these are documented anywhere I could find. They're specific to the ColabFold 1.5.5 + JAX 0.4.23 + RunPod PyTorch image combination.

## Sequence liabilities should be screened during design, not after

66 out of 342 designs had issues: His6 tags (HHHHHH), homopolymer repeat tracts (5+ of the same amino acid), or low Shannon entropy. These are manufacturability red flags.

We only screened for them when building submission CSVs. By then, we'd already scored them all. ProteinMPNN generated them; we should have filtered the sequences before sending them to AF2m.

## AI orchestration context management

The first session that ran the rescore hit 19 context compactions. That's a lot of wasted tokens re-reading the same state after each compression. The problem was polling: an hourly /loop checking 6 pods every cycle, keeping all the SSH output in context.

What worked better:
- A background shell script that pulls scores every 5 minutes and writes status to a log file
- An event-watch config that only wakes the session when the log changes
- A STATE.md file that holds everything the session needs to know after a compaction

The orchestrator session stays cheap. The background script does the repetitive I/O.

## Submissions accumulate

Proteinbase accumulates all submitted designs. Submitting v11 doesn't replace v10. So we submit different designs each day — 20 per batch, different selection strategies, never overlapping. Five submissions of 20 = 100 designs evaluated.

This was in the terms but easy to miss. It means there's no downside to submitting early, and the optimal strategy is to spread your best designs across multiple submissions with different criteria.

## The same mistake, worse: C5 scored against the wrong HLA allele

The C5 challenge target is HLA-A*11:01. We scored against HLA-A*02:01 for ~80 rounds, about 10,000 paired predictions.

The two alleles share a heavy chain that starts with the same first 8 residues, then diverges. A*11:01 has tyrosine at position 9; A*02:01 has phenylalanine. The pipeline's sequence also had a 24-residue signal peptide that should not be in a folded-complex input. The A*11:01 mature chain is 281 aa; what we used was 299 aa of A*02:01 precursor. The B2M had an extra N-terminal methionine (100 aa instead of 99).

I captured the challenge page verbatim on October 27, the day it opened. That capture has the correct A*11:01 sequence on line 236. The prep documents I wrote that day all say A*11:01. The allele was captured correctly on day one and then lost when an agent built the pipeline.

Found the error on November 7, about 38 hours before the deadline. Diffed the pipeline's sequence against the capture and counted 11 mismatches plus the missing C-terminal LSSQPT.

What I did:
1. Created a single source of truth (`c5_target.py`) with the correct sequences, verified byte-for-byte against the capture.
2. Added a pre-round assertion that refuses to run if the sequences don't match the capture.
3. Rescored all 140 eligible designs against the correct target.
4. Submitted v26 from the rescored top 20.

The designs generated against A*02:01 that happened to have high G12D specificity on A*11:01 are our best designs. Fresh designs generated against the correct A*11:01 target scored worse (best delta +0.187 vs +0.285 from the rescored pool). I don't have a good explanation for this.

The check that prevents it: `c5_target.py` runs `verify()` on import. It opens the pinned capture file, confirms every sequence appears in it byte-for-byte, checks the HLA length is 281, checks position 9 is tyrosine, and checks the capture mentions A*11:01. The round script calls this before anything else and exits if it fails.

This is the second time in this competition I scored against the wrong thing (C4 was the receptor monomer vs homodimer). The pattern is the same: the challenge page says one thing, the pipeline uses something else, and nothing checks until a human looks. The fix is the same too: pin the target to a verbatim capture and assert on every run. Should have done it from the start.

## Computational scorers disagree on what matters

The most useful finding from C5. Two scoring models, run on the same designs against the same target, give fundamentally different rankings.

OpenDDE-AbAg (an antibody-antigen confidence checkpoint) said our best dual-conditioned designs had delta +0.72: G12D confidence 0.878, WT confidence 0.151. That's extreme mutation specificity. Boltz-2 (a general structure prediction model) scored the exact same designs at delta ~0: G12D 0.934, WT 0.943. On Boltz-2 they bind everything equally.

This isn't noise. The two models see different things in the same protein complex. OpenDDE-AbAg is trained on antibody-antigen interfaces; Boltz-2 is a general folding model. A designed binder that OpenDDE-AbAg calls selective, Boltz-2 calls promiscuous. Neither is wrong in the way iPTM ranking is wrong (C4 retro above) — they genuinely disagree about the binding prediction.

The practical consequence: optimizing a single scorer doesn't tell you whether selectivity is real. The apparent breakthroughs in our late rounds were artifacts of one scorer. A multi-scorer consensus approach — requiring that multiple independent models agree before calling a design selective — is the only defensible path.

We ran it for v27. Scored 735 designs across OpenDDE-AbAg, Boltz-2, and OpenFold3. Two designs have positive delta on at least two models. One design (c5_r36_b_r3, 240 aa) has positive delta on all three. That's the one we submitted as #1. The v26 top-ranked design (delta +0.285 on OpenDDE-AbAg) shows negative delta on both Boltz-2 and OpenFold3.

## Peptide-free binding: the problem nobody's scorer catches

Every design we generated — all sizes (40-250 aa), all generators (BoltzGen, RFD4-Proteina), all conditioning strategies — binds the peptide-free HLA+B2M complex with confidence > 0.5. The challenge's second ranking criterion is peptide dependence: your binder should not bind the HLA without the peptide.

I tested the hypothesis that smaller binders (40-80 aa) would be forced to choose between peptide and HLA contacts and show lower peptide-free binding. They don't. The 40-80 aa designs have worse peptide-free scores than the 230-250 aa designs.

A publicly released competitor dataset (64 designs from @AllanatrixQ) showed that RFD4-Proteina at 60 aa generates designs that structurally contact the peptide — 4-7 contacts per design, zero B2M contacts. But when scored with OpenDDE-AbAg, those structural contacts don't translate into computational peptide dependence. The scorer doesn't see what the structure shows.

This suggests a gap between structural contact prediction and the confidence-based scoring everybody uses for ranking. The designs might actually be peptide-dependent in the lab. Or the contacts might not be energetically significant. Nobody knows until the wet-lab results come back.

## What I still don't know

- Whether any of our designs will actually bind. We optimized for iPTM consistency (C4) and OpenDDE-AbAg delta (C5), not experimental binding. No idea if either correlates.
- Whether the acid pH-switch approach works at all (C4). The whole strategy was proton-coupled design using histidine switches. The hypothesis is sound but untested.
- Whether cross-model consensus is better than single-model optimization. We submitted it (C5 v27) but don't know if consensus delta +0.09 predicts lab selectivity better than single-scorer delta +0.29.
- Whether the peptide-free binding problem is a scoring artifact or a real design failure. Every team might have this problem. Or we might be the only ones.
- Whether we're competitive. Probably not. But I learned more about protein design in three weeks than I would have in a semester.
