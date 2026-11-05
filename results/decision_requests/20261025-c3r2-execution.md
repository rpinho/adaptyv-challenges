# DECISION REQUEST — C3 round-2 execution spec (2026-10-24 21:35 ET)

Role: I am the orchestrator only. I am not choosing any parameter below; every "?" needs your
answer, as executable decisions with verification + stop conditions.

## State you should assume (all verified on disk tonight)
- C3 screen complete 44/44 (17 Modal L40S + 27 RunPod A40; same settings).
  `results/c3_screen_af2m_scores_combined_20261025.json`.
- Floor 0.850 (8 BindCraft anchors). 15/24 shortlist clear the floor.
- Evidence: `results/c3_structural_checks_20261025.json` (12/27 pass),
  `results/c3_refold_checks_20261025.json` (14/24 pass), groove from
  `results/c3_groove_reference_20261025.json` (23 residues).
- Backbone clusters now computed: `results/c3_backbone_clusters_20261025.json`
  — 44/44 rows, 18 near-identical pairs (TM>=0.65 AND cov>=0.80), v6 = 8 independent backbones.
- Your fail-closed gate was repaired and now passes 15/15 refusal fixtures
  (`scripts/c3_gate_fixtures_20261025.py`, log `results/c3_gate_fixtures_20261025.log`).
- **v7 written by that gate**: `results/c3_submission_v7_20261025.csv`,
  sha256 1d99f843b9d5af6cedd74e5ccfbf6cfd260f26e5461b2bffb0a4ee2204349c55, 20 rows.
  6 promotions: _26 _188 _132 _14 _46 _127 replacing six c3_v_* slots. v6 unchanged.
- Compute: 5 x RunPod A40 at $0.59/h, idle and keepalive'd. RFD4-Proteina installed and
  working ("RF_OK torch 2.14.1+cu126 cuda True") on pod 1 ONLY. Pods 2-5 have ColabFold.
- Inputs/data present: `data/6x18.cif`; RFD4 spec `configs/rfd4/c3_glp1r_ecd.yaml`
  (contig "45-100, /0, F38-154", 8 hotspot residue selections on chain F).
  I verified chain F residues 38-154 == EXACTLY the 111-residue ECD used as `target` in
  `results/c3_screen_input_20261024.csv`, so the plan's byte-equality precondition HOLDS.

## Questions (answer each with a concrete command/parameter, not an option list)

1. **Round-2 gate still applies?** The current 6 promotions already fill all six variant slots
   that passed. Your plan §2 says run round 2 only if fewer than seven variant slots can be
   filled. Six were filled. Do we (a) stop C3 candidate generation and spend remaining C3 GPU
   on strengthening evidence for v7, (b) run round 2 anyway for diversity, or (c) something
   else? If (a) or (c), give the exact next experiment, because "nothing" is not allowed.

2. **If round 2 runs:** RFD4 arguments. The existing spec was used with
   `rfd4-generate inputs=<spec> recycle_strategy=medium/front_loaded num_replicates=N
   batch_size=1 seed=S save_chain_of_interest=true prevalidate_inputs=true '~metrics'`.
   - For 36 backbones split 12/12/12 across lengths 52-64 / 65-80 / 81-100 against the SAME
     contig+hotspots, what exact CLI should I use? Does the length distribution require
     separate specs (contig "45-64, /0, F38-154" etc.), or one spec with a length override?
   - Seeds and batch_size per pod, given 5 pods x A40 48 GB.
   - Expected wall-clock per backbone on an A40 with this spec (so I can set timeouts).

3. **MPNN step:** the pods have no ProteinMPNN and the repo has no MPNN script; the previous
   C3 RFD4 sequences came from elsewhere. Give me the exact source (upstream repo + weights),
   the CLI, and the 2-sequences-per-backbone command line, or state an alternative sequence
   design step (e.g. RFD4's own sequence output) if MPNN is not required.

4. **Refold/filters:** confirm the exact monomer-refold tool for the 72 sequences (ESMFold on
   the pod, as used for the C3 refold gate?) and the exact selection rule from 72 -> 24 with
   >=8 clusters at TM 0.65 / cov 0.80, <=2 per cluster. State whether TM clusters are computed
   on the DESIGNED backbone or the refolded monomer.

5. **C4 priority conflict:** §3 says port Boltz-2 to an A40 and reproduce one apical result.
   Meanwhile pods are the only compute and C3 GPU stops at 12:00 ET. Which do the 5 pods do
   first tonight, in what split? Give a concrete per-pod assignment.

6. **C5:** confirm "templates only, $0 GPU" still holds after the target announcement on Oct 26,
   and whether anything should be prepared tonight that does not depend on the target.

Constraints: no new Modal spend; 5 pods max, $0.59/h each, they self-stop when idle 90 min;
nothing is submitted; nobody contacted. Record any answer that changes a threshold as
RICARDO-APPROVAL-NEEDED rather than assuming it.
