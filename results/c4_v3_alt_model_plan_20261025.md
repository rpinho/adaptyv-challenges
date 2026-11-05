# C4-V3 alternative-model plan — bounded, $0 inventory. **Two trials worth doing; both need your word.**

**2026-10-25 17:24 ET. Scope: inventory + preflight only. No GPU started, no pod started, $0 spent,
no sixth design, no wave 3, nothing submitted.** Owner: `01a170d2` (canonical).
Artifact: input CSV built and validated (`results/c4_v3_af2m_input_20261025.csv`, sha `b7e05e7f`).

## 0. "V3" = `results/c4_ranked_v3_apical_20261025/` — confirmed from project evidence, not assumed

`c4_acid_ranked_v3_apical_20261025.json` self-describes as *"supersedes v2 for PILOT SELECTION only"*
and its `what_changed` is "ONLY the structural screen input directory: surrogate 154 → apical 195".
There are four siblings (v2/v3/v4 apical-L6 + the shipped v9), so "V3" is ambiguous in casual speech —
**this plan means the v3 apical ranking, 20 rows, sha of its CSV below**, not `submission_v9.csv`.

The premise in the 17:02 scoping ("try new models for V3") is **half wrong and that half matters**:
the correct-context Boltz-2 run already completed on 2026-10-24 (342 apical complexes, chain B = 195),
and L6 + v4 apical-L6 ranking are already built. The genuine gap is **model diversity**: only Boltz-2
has ever touched V3 on the correct construct.

## 1. The blocker is NOT cost, and that is the finding

Earlier today the assumption was "a second model cannot arrive in 3h even with GPU" — based on
**Modal L40S at $1.95/h, ~17 min/model, ~85 min/design for 5 models**, which is what made the C3
rescreen cost $2.79/design.

**That assumption is now stale.** The AF2m RunPod port was validated at **n=5** on 2026-10-24
(`results/c3_af2m_port_20261025/validation_20261025_n5.md`): iPTM reproduced **exactly 5/5**, zero
verdict flips, at **116–160 s/design for all 5 models** — not per model. That is **~34× faster per design in wall-clock** (85 min → 2.5 min)
and **3.3× cheaper per GPU-hour** than the Modal path.

| path | rate | wall / design (5 models) | cost / 20 designs |
|---|---:|---:|---:|
| Modal L40S | $1.95/h | ~85 min (86 min implied) | **~$55.9** (measured: canary billed **$2.79**/design × 20) |
| **RunPod A40 (validated)** | **$0.59/h** | **116–160 s (mean 149 s)** | **~$0.49** |

So a second model on V3 apical is **cheap and fits inside 3 hours easily**. The constraint is
**authorization**, not compute. Per `MISSION_ORCHESTRATOR.md` and the 2026-10-25 research plan
(*"GPU authorization expires 08:00 ET"*, and **$0** additional C3/C4/C5 GPU authorized), **I have no
standing authorization to start a pod.** All five A40 pods are `EXITED` (verified via RunPod API).
**Nothing has been started.**

## 2. Concrete model candidates, what is actually installed, and what each would prove

| candidate | installed where | correct apical target? | marginal evidence it adds | verdict |
|---|---|---|---|---|
| **AF2-multimer v3** (ColabFold 1.5.5) | Modal volume `colabfold-cache`; RunPod pods have localcolabfold | **needs target swap only** | second **folding engine**; agreement/disagreement with Boltz-2 on the same 20 | **PRIORITY 1** |
| **ESMFold v1** | Modal `hf_cache` has it; runner exists (`modal_esmfold*.py`) | needs target swap | monomer-only — **cannot** model a complex | **reject for complex work**; valid only as a binder-folds-alone sanity check |
| **Boltz-2, second seed / more samples** | already deployed | yes, today | measures *sampling* variance, not model variance | **cheap but answers the wrong question** |
| Chai-1 | **not installed anywhere** | — | third engine | **out of scope** — new image + weights + validation > 3h, and unvalidated against this target |
| Protenix / AF3-class | **not installed anywhere**; AF3 weights are gated | — | strongest third opinion | **out of scope** — licensing + new image |

### Why AF2m is the right first trial, specifically
It is the **only** candidate that is (a) already installed, (b) already validated on this machine's
exact protocol against the same code path, and (c) genuinely a **different engine from Boltz-2**.
Every V3 conclusion today derives from **one** predictor; AF2m disagreement would be the single most
informative cheap fact available.

## 3. Exact blockers to clear before any run (all $0, ~20–30 min of my time)

1. **Target constant.** `modal_af2m_c3_complex.py` hard-codes the **111-residue C3 ECD**; there is no
   C4/apical variant in any AF2m or ESMFold runner. **Already solved for the input side:** I built
   `results/c4_v3_af2m_input_20261025.csv` with the true **195-residue apical** target extracted from a
   real apical PDB and **byte-verified identical** to `TFR1_APICAL_189_383` in `modal_boltz2_apical.py`.
2. **Longer sequences.** C3 complexes were 157–211 residues total; **C4-V3 are 260–295** (+40%). No
   AF2m run in this repo has gone past 211. This is the one real technical risk: it needs a single
   canary design before a 20-design batch, and MSA depth may need capping.
3. **`pod_run.sh` is on the pod, not in the repo.** The validated script lives at
   `/workspace/pod_run.sh`; only `scripts/c3_r3_pod_run.py` (the C3-specific, cutoff-hardcoded sibling)
   is version-controlled. A C4 run needs a repo-resident copy so the protocol is reproducible.
4. **Policy, not cost.** `results/c4_apical_run_20261024.md` records **two prior sessions declining
   candidate-specific apical launches on assistance-scope grounds.** I have no evidence that blocker was
   lifted, and it is the reason I am not treating "$0.60 is trivial" as permission.

## 4. The two trials I would prioritize (in this order)

**Trial 1 — AF2m canary on 3 V3 designs (~$0.07 compute, ~7.5 min serial GPU, ~20 min wall with setup).**
Three designs spanning the binder-length range and the apical clash flags (one clean, one of the six
flagged). Purpose is *not* new science; it is to prove the port works at 260–295 residues and that the
target swap is correct, before spending 20× that. **Gate: canary must produce finite iPTM on all 3, and
chain B must parse as exactly 195 residues.** If either fails, stop — do not escalate to 20.

**Trial 2 — full AF2m on the 20 V3 rows (~$0.49 compute, ~50 min serial GPU, ~65 min wall), only if Trial 1 passes.**
Output is the first **cross-model** V3 evidence in the project: per-row Boltz-2 vs AF2m iPTM, and
agreement/disagreement on which of the 6 apical-flagged rows are structurally credible.

**What Trials 1+2 would NOT establish** (say this plainly, it will be over-read otherwise):
- Not experimental binding, and not pH-conditional binding/release.
- Not native context — still the domain-only 195-residue construct.
- Not a re-ranking: two models disagreeing is a *flag*, not a verdict on which is right.

**Why not the 6-pair pilot instead:** the earlier decision record already established that six pairs
must be **reseeded** on apical L6 before any confirmatory pilot, and that work is GPU-plus-selection, not
a model swap. Model diversity is the cheaper, more orthogonal fact right now.

## 5. What I need from you (one decision, not three)

**One line: "authorize Trial 1" (≈$0.07) or "authorize Trials 1+2" (≈$0.56), via RunPod A40 pod
`fak1k8jnuxwtc5`, and confirm the assistance-scope blocker does not apply to C4 apical.**

Without that I stay at $0 and the plan sits here. If you want it *today*, Trials 1+2 fit comfortably
before 19:30; if you would rather keep the sprint C3-only, this is ready to run cold tomorrow — nothing
expires except pod availability.

## 6. Artifacts and state

| item | value |
|---|---|
| V3 apical ranking CSV | `results/c4_ranked_v3_apical_20261025/…csv` (20 rows, 20 unique) |
| **AF2m input built now** | `results/c4_v3_af2m_input_20261025.csv`, sha **`b7e05e7f`** |
| apical target | 195 aa, extracted from `all343/tfr1_c4_acid_site1_0_complex.pdb` chain B, == Boltz constant |
| port validation | `results/c3_af2m_port_20261025/validation_20261025_n5.md` — iPTM exact 5/5, 0 flips |
| pod inventory | 8 pods defined, **all EXITED**; A40 $0.59/h, 80 GB disk, image `runpod/pytorch:1.0.2-cu1281-torch280-ubuntu2404` |
| **spend this plan** | **$0.00** — no pod started, no Modal task, no fold |

Not uploaded, not submitted, nobody contacted.
