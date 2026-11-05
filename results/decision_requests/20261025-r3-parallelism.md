# DECISION REQUEST — per-pod AF2M parallelism for the R3 screen (2026-10-25 00:55 ET)

decider: Kimi (primary). second opinion: Astra. Orchestrator does not decide.

## Question
May the R3 AF2M screen run N>1 concurrent `colabfold_batch` processes per pod, and if so what N,
so that more of the 182 frozen eligible designs get scored before the 03:42 ET hard stop?

## Measured facts (orchestrator, on-pod, 00:44–00:52 ET)
- Per-design wall time **215–275 s** (12 observations across p1,p2,p3,p4,p5). Matches the round-2
  median 247 s and the 233 s benchmark. MSA mode `mmseqs2_uniref_env`, `--num-models 5`,
  `--num-recycle 3`, `--model-type alphafold2_multimer_v3`.
- **GPU utilisation sampled 6x at 2 s intervals on every pod: 0% except a single 100% sample.**
  GPU memory held 2.7–2.9 GB (of 48 GB). Python process CPU ≈ 12% of one core.
  => the dominant cost is MSA generation/network, not the folding forward pass. The A40 is idle
  ~90% of each design.
- Pod hardware: **96 vCPU, 503 GB RAM**, 48 GB A40. `XLA_PYTHON_CLIENT_MEM_FRACTION=4.0`,
  `XLA_PYTHON_CLIENT_PREALLOCATE=false` in `/workspace/pod_run.sh` (memory grows on demand).
- Current allocation: p3 running my 27-design R3 slice serially; p1,p2,p4,p5 running the sibling
  lane's bounded LigandMPNN pilot (24 designs, 6 each) serially, same 4-min cadence.
- Clock: 03:00 ET no new admissions, 03:15 quiesce, 03:30 persist+hash, **03:42 pods self-stop**
  (disk wiped on restart). It is now 00:55 ET => ~2h05m of usable wall.
- Capacity today: serial, 5 pods × ~2h05m at 4.1 min = ~150 designs max, and only 27 are actually
  launched on p3 right now, so realistically ~27 + whatever trickles in = well under 182.

## Why this is consequential
It changes screening *method* (concurrency), touching two pre-registered rules: "first pass = one
sequence per eligible backbone" ordering, and the Astra/Kimi cutoff plan that assumed 250 s/design
as a fixed per-pod rate. Running 2-3 wide does not change any threshold, any design, or the queue
order — it only changes how many of the frozen 182 are scored before the stop. It also changes the
cost/design figure Ricardo asked for. Risk: MSA server rate-limiting, RAM/CPU contention making
per-design time worse, or GPU OOM at high N.

## Options
A. **N=2 per pod** once a pilot pod frees (conservative; MSA overlap, GPU still idle most of the time).
B. **N=3 per pod** (still 6.4 GB GPU if XLA grows per process, 3×10% CPU).
C. Stay serial; accept partial coverage and record the shortfall explicitly.
D. N=2 on pilots' pods only after their pilot finishes, N=3 on p3 immediately (hybrid).

## What the orchestrator needs back
1. Which option; if parallel, the exact N and whether it is uniform.
2. Whether the per-design record needs a `concurrency`/`batch_id` field so that a parallel design can
   never be mistaken for a serial one in the final provenance (I propose yes, always recorded).
3. Whether a parallel-vs-serial *validation* is required first (e.g. re-score one already-scored
   design under N=2 and require iPTM identical to the Modal value) before scaling — I can do that in
   ~5 min on p3 and I would prefer to.
4. Explicit statement of what gets recorded as INCOMPLETE at 03:15, so coverage shortfall is legible.

## Non-negotiables (not yours to relax)
Nothing submitted, nobody contacted, no new spend beyond the five pods, frozen queue order and the
hash `eeba81b7…` unchanged, v6/v7/v8/v9/apical untouched.
