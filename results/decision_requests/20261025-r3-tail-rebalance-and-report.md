# R3 overnight — two decisions needed (03:00 cutoff in ~50 min). Evidence below; do not invent facts beyond it.

## State (verified 02:05-02:10 ET from the pods)
- 5 RunPod A40 pods running one N=2 AF2M screen driver each. 182-design frozen cohort, sha eeba81b7...
- Scored 102/182 at 02:09. Per-pod completion rate measured from artifact mtimes: ~128-147 s per design.
- Per-pod frozen slices (from screen_input_manifest_20261025.json, sha recorded, part of the cutoff contract):
  p1=39 (remaining 20), p2=44 (remaining 24), p3=26 (remaining 2), p4=38 (remaining 18), p5=35 (remaining 16).
- Per design ~139 s => each pod can start ~20 more before the 03:00:00 ET admission stop (epoch 1792911600).
- Projection at that rate: p2 strands ~4 designs; p3 idles from ~02:13 ET (it drains first).
- The cutoff snapshot script (scripts/c3_r3_cutoff_snapshot_20261025.py) reads each pod's /workspace/r3_screen/out
  and FAILS CLOSED if any name is outside that pod's frozen slice in screen_inputs/pN.csv.
- The runner on all five pods is now identical (sha 3c6d9f5d...), design-only claim key sha256("design|"+name),
  in-driver 03:00 cutoff, so a design launched from another pod's CSV would still not double-fold
  (claim files live per-pod though, so cross-pod dedupe is NOT guaranteed by the claim key alone).
- Nothing submitted; v8 631ed0bf... sole candidate; your Q5 prohibits v9 tonight.

## Q1 — rebalancing vs frozen slice (needs a ruling)
p3 will be idle ~45 min while p2 strands ~4 designs at the admission stop.
Options:
(a) FROZEN SLICE GOVERNS: do nothing. Those ~4 become INCOMPLETE/NOT_SCREENED with scores null.
    Bubble-free, contract intact, loses ~4 designs of a 182 cohort.
(b) REBALANCE: give p3 a small supplemental CSV = the tail of p2's slice that p2 cannot reach before 03:00
    (unstarted names only, verified not started and not claimed). This changes the per-pod slice membership,
    so the cutoff snapshot's "outside frozen slice" check must be extended to accept a recorded, hashed
    rebalance manifest rather than weakened.
(c) Some other rule you prefer.
Constraints I will not violate without your explicit word: do not relax gates, do not treat missing TM
evidence as novelty, do not extend the hard stop, do not retry failed designs.

## Q2 — what tonight's R3 report must contain
You required "a summary by H8/H4 and length bin: generated, valid, screened, clash failures, fully eligible,
and crosswalked-independent counts." The current finalizer
(scripts/c3_r3_finalize_20261025.py) emits: status counts overall and by arm/bin, per-pod records,
five-model split, and PASS/FAIL/INCOMPLETE/NOT_SCREENED. It does NOT emit: generated/valid counts,
clash-failure counts separately, or crosswalked-independent counts.
I plan to add a READ-ONLY post-cutoff report script that computes exactly those from
status_20261025.json + cross_tm_20261025.json + refold_checks + structural_checks, failing closed if the
crosswalk is incomplete or an eligible design has no backbone/TM mapping. No CSV writes, no v9.
Is that the right scope, and is counting "crosswalked-independent" as distinct X### components over the
eligible designs' backbones (with a separate "components that contain no prior R1/R2 member" number) the
unit you intend? Confirm or correct.

Answer briefly, and flag anything in the above that is inconsistent with your prior rulings.
