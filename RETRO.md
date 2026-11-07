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

## What I still don't know

- Whether any of our designs will actually bind. We optimized for iPTM consistency, not experimental binding. No idea if that correlates.
- Whether the acid pH-switch approach works at all. The whole C4 strategy was proton-coupled design using histidine switches. The hypothesis is sound but untested.
- Whether we're competitive. Probably not. But I learned more about protein design in two weeks than I would have in a semester.
