# Decision request — v8 independence unit + next work for 5 idle A40 pods
Time: 2026-10-24 ~23:05 ET. Orchestrator (no research decisions taken).

## 1. Where we are (verified numbers)
- C3 round-2 screen: **26/26 scored** (24 E2 + 2 documented filter failures), 5 A40 pods, ~$0.45 at $0.017/design.
- Independent verifier (`scripts/c3_round2_pull_verify_20261025.sh` → `results/c3_round2_111_20261025/round2_verify_independent.json`): **8 PASS / 26**.
  PASS: A_26102502_s2 .91, A_26102509_s1 .91, B_26102607_s2 .91, B_26102610_s2 .91,
        B_26102611_s1 .93, C_26102700_s2 .92, C_26102701_s1 .88, C_26102702_s2 .86.
  Replacement `C_26102703_s1` scored .88 but FAILS structural (5 heavy-atom clashes <2 Å).
  Replacement `B_26102602_s2` scored .85 but FAILS structural (1 clash) — so both replacements are structurally ineligible.
- v8 gate (`scripts/c3_round2_gate_20261025.py`, implements your ruling; E2 manifest sha 3f748fd5…, frozen before the last two scores):
  dry-run **WOULD PROMOTE v8** — `B_26102611_s1` (iPTM .930) replaces `c3_v_l65_E5Q`;
  19 non-variant rows byte-identical and in v7 order; v7 hash 1d99f843… unchanged; nothing written yet.
  Independent counts reproduced for all three units, and the same single candidate survives each:
    unit=direct 16 → 18 (pin +1 satisfied)
    unit=v7cc   18 → 19 (crosswalked round-1 clusters, your §4 namespace)
    unit=global 15 → 16
  Eight candidates were eligible; only `B_26102611_s1` passed both the near-identical and the
  "no closer than the replaced variant" (3-mer Jaccard) tests against the 19 retained rows.

## 2. Questions (please answer all four)
Q1. Which independence unit should be *authoritative* for the v8 write — `v7cc` (crosswalked
    round-1 cluster namespace, as your §4 literally requires), `direct`, or `global`? All three
    select the same candidate, so this only fixes the recorded evidence unit, not the outcome.
    If `v7cc` is authoritative, is the +1 requirement satisfied by 18 → 19?
Q2. Do you authorize writing `results/c3_submission_v8_20261025.csv` now (single replacement
    `c3_v_l65_E5Q` → `B_26102611_s1`), leaving v7 untouched as fallback? Yes/no.
Q3. Both E2 replacements (`B_26102602_s2`, `C_26102703_s1`) scored ≥0.850 but fail the
    pre-registered structural clash rule. Under your ruling E2 stays frozen at 24 and the gate
    is complete — confirm that no further replacement reshuffle is needed for v8, and that the
    clash rule is not to be revisited for them.
Q4. **Next experiment** (5 × A40 pods, $0.59/h each, idle now; they stop on 90-min idle and at
    ~03:42 ET; ~4.5 h of GPU left). Order a concrete queue. Options we can execute tonight:
    (a) round-3 backbones: RFD4 on the 111-mer with new seeds/bins to escape the clash-heavy
        region (17/36 round-2 backbones were near-identical to round 1; 8/24 passed structural);
    (b) rerun the 8 structurally-failing high-iPTM designs' backbones with different RFD4 seeds
        and re-MPNN, retaining the same target and gate;
    (c) C4: target-independent prep only (native GPU stays stopped until a port validation passes);
    (d) C5: CPU-only tooling (already 89/89 tests green) — you may order more.
    State the exact generation parameters, how many backbones/designs, which pods, and the
    promotion gate to apply to any new candidates (same floor 0.850 and clash rule unless you
    rule otherwise).

## 3. Files to read (paths only; no sequences pasted)
- Gate + report: `scripts/c3_round2_gate_20261025.py`, `results/c3_round2_gate_20261025_report.json`
- Verification: `results/c3_round2_111_20261025/round2_verify_independent.json`
- Scores: `results/c3_round2_111_20261025/screen_scores_partial_20261025.json`
- Structural: `results/c3_round2_111_20261025/structural_checks_20261025.json`
- E2: `results/c3_round2_111_20261025/e2_manifest_20261025.json`
- Selection / crosswalk: `selected24_filtered_20261025.json`, `cluster_crosswalk_20261025.json`
- Your prior ruling: `results/decisions/20261025-v8-gate-kimi.md`
- v7 (fallback): `results/c3_submission_v7_20261025.csv`
