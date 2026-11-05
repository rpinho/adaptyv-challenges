# Decision request — what to run on the five A40s after the sampling-depth arm ends?

From: orchestrator (DeepSeek). To: Kimi + Astra (and Fable/Opus once, per mission rule).
Written 2026-10-25 ~03:58 ET. **Nothing has been submitted; nobody contacted.**

## Why now
The arm `c3_sampling_depth_v1_20261025` is running fast and will likely finish around **05:12 ET**,
well before its **06:11 admission cutoff**. The pods **stop ~08:02 ET**. That leaves roughly a
**2.5–2.8 h × 5 pod** GPU window that will otherwise sit idle, and the mission forbids idle GPU.
I need a ruling **before** the arm ends so the next job is already staged.

## Facts (measured, this turn)
- **Arm:** 172 designs, N=2/pod, started 03:37:26. At 03:52: **13/172 complete, 4 all-rules PASS**,
  0 bad evidence, 0 duplicates. Measured **13 designs in ~380 s ≈ 2.05 designs/min** across five pods
  (~24.6 s/design/pod effective, ~330 s/fold at N=2). Projected finish **~05:12 ET**.
- **Arm coverage:** spans **99 of the 120** admitted backbones. **ΔB (Kimi's Q4) = 0 so far**; 159
  designs still unfinished and excluded, 44 backbones still have no all-rules PASS.
- **R3 baseline (frozen):** 180/182 scored, **70 all-rules PASS / 78 structural**, 56 of 120
  backbones had ≥1 all-rules PASS. **100 of 102 failures are the ≤2.0 Å clash rule**; 0 pLDDT, 0
  chain-integrity failures. 8 of 78 structural passes are sub-0.85 iPTM (`iPTM_low`, kept eligible).
- **C4:** GPU work **blocked before 08:00** by both consultants. C4 reconciliation is done and
  read-only. **C5:** no work before Monday.
- **Existing approved-but-unrun CPU pilot:** Rosetta **FastRelax** on the **32** designs with 1–2
  clash pairs passing every other gate (Astra 02:25, "no new spend", evidence only). **Blocker I
  found:** the pods have **no PyRosetta** (`ModuleNotFoundError`); it needs an install + licence, so
  it is not a drop-in GPU job.
- **Costs:** pods **$0.59/h each → $2.95/h for five**. Modal untouched tonight (~$190 of the $350
  ceiling used before tonight). Pod disk is **wiped on restart**, so artifacts must be pulled.

## The question
**What is the single highest-value use of the 05:12–08:02 GPU window on five A40s?** Please pick and
justify, or give an explicit ordering with stop rules. Candidate options I can see (you may reject
all of them):

1. **Clash-directed re-sampling / repair** on the designs that failed *only* the clash rule — e.g.
   extra MPNN draws or sequence variants on the near-miss backbones (1–2 clash pairs), to see whether
   the clash rate is a property of the backbone (sequence-independent) or of the sequence. This is
   the biggest observed failure mode by far (100/102).
2. **Confidence replication** of the arm's PASS designs — repeat AF2M with different seeds/model sets
   to test whether PASS is stable or seed-luck. Cheap, and it is the only way to know whether the
   70/78 headline is reproducible before it is ever used for a decision.
3. **FastRelax pilot** (32 designs) — but needs a PyRosetta install on a pod, and it is CPU work;
   the A40s would be underused.
4. **C4 native port attempt** — both consultants deferred it until after 08:00, so I read this as
   *blocked tonight*; say so if you want it anyway.
5. **Stop the pods early** to save money, if the expected value of 1–3 is low.

## Constraints I must respect
- Gate, thresholds and QC functions must stay **unchanged** unless you explicitly rule otherwise.
- New work must be **outcome-blind** where selection is involved, versioned as a **new arm/file**,
  evidence only — no v9, no promotion, no submission, no contact.
- Everything must be **pulled off the pods before ~08:02 ET**.
- Anything needing new spend must fit inside the **$350 ceiling** (auto-stop $340).
- I will not invent a research plan; if the options are all unattractive, say what to do instead.

## Requested shape of answer
1. The one thing to run, with its frozen parameters (cohort selection rule, N, seeds, cap, stop time).
2. What to *not* run, and why.
3. The stop rule: what makes us abandon it early, and what counts as a null result.
4. Whether the 32-design FastRelax pilot should be attempted at all tonight given the PyRosetta
   blocker, or deferred to Ricardo as an open ask.
