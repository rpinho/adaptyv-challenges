# ONE narrow question: 240 (Astra) vs 360 (Kimi) admission cap on the sampling-depth arm

03:41 ET. The arm is **already running** under Astra's narrower parameterisation. This asks only
whether to add the third wave. Do not re-answer the rest of the plan.

## Facts (verified, inline)
- The pods **never stopped**; the real timer is `sleep 41400` (11.5 h) → stop ≈08:06 ET. Kimi's
  "restart the five pods" premise is moot; no restart occurred and nothing was lost.
- Astra (03:21): 2 draws/backbone = **240 max admissions**, 3 h, absolute 07:30 ET, id
  `c3_sampling_depth_v1_20261025`.
- Kimi (03:34): 3 draws/backbone = **360 max**, in 3 waves of 120, 4 h, absolute 07:45 ET, id
  `r3_mpnnplus3_v1`.
- Both: all 120 backbones, outcome-blind, unchanged MPNN procedure except depth, unchanged AF2M
  (v1.5.5/multimer_v3/3 recycles/5 models) and unchanged gate (2.0 A clash, iPTM>=0.85 all-rules
  PASS, `iPTM_low` retained), evidence only, no v9.

## Executed and live now
- Manifest frozen before sampling: 240 slots, `slots_sha256 95b7ad1c…`, 48/pod, seed 20261029.
- MPNN: 235/240 fastas (5 missing slots recorded, not backfilled).
- Soluble filters: 202 eligible, 33 excluded.
- **ESMFold refold: 172/202 pass** (same thresholds as R3: mean pLDDT>=80, frac>=70>=0.90,
  CA RMSD<=3.0 A; 30 excluded).
- **AF2M screen live since 03:37:26 ET**, **172 designs**, N=2, per pod p1 34 / p2 39 / p3 27 /
  p4 41 / p5 31; admission cutoff **06:11 ET**, hard stop 06:31 ET; input `8139730acd2b`.
- Measured throughput this round (R3, same pods, same settings): **~177 s/design effective at N=2**,
  $0.029/design.

## The question
Wave 3 (sd3: one more draw for every backbone, +120 balanced) is pre-staged but **not launched**,
because 292 admissions would exceed Astra's explicit 240 ceiling. Guidance needed:

1. **Cap:** hold 240, or raise to 360 for the third wave? If raised, whose cap governs and what is
   the new absolute stop (06:31 hard / 07:30 / 07:45)?
2. **Truncation argument:** Kimi's three-wave design protects against depth concentrating on a few
   backbones under time truncation. Here **all 240 sequences were sampled before screening began**
   (235/240), so balance is already achieved and the wave structure only changes total depth. Does
   that remove Kimi's reason to prefer 3 waves, or does it still apply to the *screen* phase?
3. **Analysis if both exist:** if wave 3 is authorised, should 240 and 360 be reported as two
   pre-registered depths (a dose-response on measured yield) or as one cohort?
4. **Naming:** keep `c3_sampling_depth_v1_20261025` (live, hashed, partially screened) or rename to
   Kimi's `r3_mpnnplus3_v1`? Renaming a partially-screened, hashed arm seems wrong to me — confirm.

I will not resolve a cap conflict by choosing the larger number, and I will not exceed Astra's
ceiling without an explicit ruling. Nothing is submitted; nobody contacted.
