# RunPod AF2M cost per design — measured, 2026-10-25

## Answer
**$0.029 per scored design** at N=2 concurrency on a $0.59/h A40 (was **$0.041** serial).
Modal at $1.95/h L40S is **3.3× the hourly rate** for the same ColabFold run, so the RunPod lane is
the cheap one, and N=2 widens the gap.

| setting | per-design wall | designs/pod/day | $/design @ $0.59/h |
|---|---|---|---|
| serial (N=1) | 250 s (median of 53 measured designs) | 346 | **$0.041** |
| **N=2 (adopted)** | **177 s effective** | **488** | **$0.029** |
| Modal L40S, serial | 250 s | 346 | $0.135 (at $1.95/h) |

## Where the numbers come from
- 53 pulled R3/E3 designs: median `subprocess_wall_s` = **256 s**, range ~211–358 s.
- N=2 measured on p2: two designs completed in one ~355 s wall ⇒ 177 s/design effective,
  **1.41× serial**. GPU 4.99 GB of 48 GB, two concurrent ColabFold processes, 100% util in bursts.
- Why parallelism works here: the A40 is **idle ~90%** of each design (MSA generation/network
  dominates). We are not buying GPU throughput, we are overlapping wait time.
- Gate that justified it: `results/c3_r3_20261025/validation/verdict_par2.json` (sha `6f5dcde…`) —
  serial 0.920/0.920 vs parallel 0.920/0.920, **Δ=0.0000**, five models complete both arms.

## Spend to date
- 5 pods × $0.59/h = **$2.95/h**. The overnight window (00:47→03:42) costs ≈ **$8.85** total,
  containing up to ~150 designs — i.e. **≈$0.06/design all-in including idle tail**, still far below
  the Modal rate.
- Modal: **$0 spend tonight**; the ~$190 recorded earlier is from the prior round and is inside the
  $350 ceiling.

## Caveat
N=2 raises RAM/CPU per pod but both are barely used (96 vCPU, 503 GB; <15% of one core per fold).
N=3 is **not** validated and stays off (Astra rejected it; Kimi requires a separate N=3 gate).
