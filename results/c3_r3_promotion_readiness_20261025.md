# C3 — R3 promotion-readiness dossier (read-only)

Generated 2026-10-25 after the R3 cutoff chain finalized. **This file promotes nothing, writes no CSV, and performs no gate transaction.** It states what the frozen evidence supports, what it does not, and what would still be required.

## 0. Evidence boundary (frozen)

- R3 cohort input: `eeba81b77d9485a6…` (`screen_input_20261025.csv`, 182 valid designs of 240 generated)
- Coverage ledger: `c37ba2f1d27e8fcd…` — **180/182 scored**, 2 unscored (NOT_STARTED_DEADLINE)
- Screen verifier: `4fc730455dc65fa4…` — expected 182, complete 180, incomplete 2, **bad evidence 0**, all-rules PASS **70**
- Finalize marker `.finalized` present; `report_20261025.FAILED` absent.
- Evidence manifest `SHA256SUMS.evidence`: **3709/3709 files verified**, append-only logs excluded by design (`SHA256SUMS` at 03:31:31 predates the 03:32:21 report rewrite).

## 1. Screen result (layer 1: screen eligibility)

| metric | value |
|---|---|
| generated designs | 240 |
| valid, queue-eligible | 182 |
| screened | 180 |
| **all-rules PASS** | **70** |
| FAIL | 110 |
| not screened (queue-excluded) | 60 |
| bad evidence | 0 |
| clash failures among screened | 100 |
| refold failures (pre-screen filter) | 40 |

**Structural PASS: 78; of those 8 are below the 0.85 iPTM floor**, leaving **70 all-rules PASS.** The 8 remain eligible only with an explicit `iPTM_low` flag and are never relabelled as all-rules PASS:

- `p1_H8_52_64_910006_s1` — iPTM 0.730 (fail)
- `p2_H8_65_80_910120_s1` — iPTM 0.840 (fail)
- `p2_H8_65_80_910120_s2` — iPTM 0.810 (fail)
- `p2_H8_65_80_910121_s1` — iPTM 0.840 (fail)
- `p3_H8_81_100_910200_s2` — iPTM 0.840 (fail)
- `p3_H8_81_100_910210_s1` — iPTM 0.810 (fail)
- `p4_H8_65_80_910124_s1` — iPTM 0.840 (fail)
- `p4_H8_65_80_910125_s1` — iPTM 0.770 (fail)

By arm: H8 57/145 screened (39%); H4 13/35 (37%).

## 2. Independence (layer 2: promotion-evidence completeness)

- Crosswalk complete over all 120 R3 backbones; 284 near-identical edges; rule: "near-identical iff TM>=0.65 AND coverage>=0.80; shared X### namespace".
- R3 all-rules PASS designs occupy **21 distinct components**, of which **18** contain no R1/R2 member.

**v8 baselines, all three recorded definitions (measured, not recomputed here):**

| universe | v7 | v8 | meaning |
|---|---|---|---|
| direct | 16 | 17 | rows not near-identical to any other final row |
| v7cc | 18 | 19 | connected components restricted to the final 20 rows |
| global | 15 | 16 | components over every measured design (excluded designs may bridge seats) |

Kimi later called **v7cc** authoritative; the implemented promotion gate and the binding-unit record use **global**. Under global, R3's components are the comparable figure; under v7cc they are not. This is why the strict count stays UNKNOWN.

**UNRESOLVED CONFLICT — both baselines reported, neither chosen:** the binding-unit record and the implemented gate disagree on the independence definition, and Kimi's later queue ruling called the v7 crosswalk authoritative. Until Ricardo resolves which governs, any strict component count is **UNKNOWN**.

- R3 components containing no prior R1/R2 member: **18**
- R3 distinct components (global universe, as the report computes them): **21**

## 3. Five-model evidence (Astra's retention rule)

- `five_model_recovery/inventory_20261025.json` records **16 recovered designs**, 80 score files.
- **Independently audited 03:22 ET:** 16/16 have 5 distinct score JSONs (models 1-5) and 5 PDBs, and every binder chain sequence extracted from the PDBs hashes to the verifier's recorded `binder_sequence_sha256`. Verdict: recovery is genuine for these 16; recorded as a separate reconciliation, **frozen ledger not edited**.
- Designs outside that inventory that are otherwise eligible remain **evidence INCOMPLETE** for strict promotion until the same audit is generalised. Screen PASS is unaffected.

## 4. What would a v9 require (future transaction requirements — none satisfied today)

Restated from the existing v7/v8 gates; this dossier tests **none** of them:

1. Frozen score/refold/structural/soluble gates, unchanged (incl. 0 heavy-atom pairs <=2.0 A).
2. iPTM >= 0.85 for every row unless explicitly carried as `iPTM_low`.
3. Verified five-model retention tied to the same design and run.
4. Crosswalked independence under **one** resolved definition, with the removal rule fixed.
5. Whole-set Jaccard / TM-coverage independence vs v8, not per-row novelty.
6. Atomic write, full row diff, v8 preserved byte-identical, independent audit.
7. **Ricardo's explicit authorisation.**

## 5. Shortlist — CONDITIONAL, not recommendations

Ordered by complete evidence, then demonstrated replacement-conditioned benefit, then score. No slot is filled to fill the table.

| design | iPTM | component | prior member? | five-model | status |
|---|---|---|---|---|---|
| `p4_H8_81_100_910228_s1` | 0.940 | X000 | yes | UNKNOWN | CONDITIONAL |
| `p2_H8_65_80_910100_s2` | 0.930 | X000 | yes | UNKNOWN | CONDITIONAL |
| `p4_H8_81_100_910231_s2` | 0.930 | X000 | yes | UNKNOWN | CONDITIONAL |
| `p5_H4_65_80_910406_s1` | 0.930 | X000 | yes | UNKNOWN | CONDITIONAL |
| `p5_H4_81_100_910502_s1` | 0.930 | X096 | **no** | verified | CONDITIONAL |
| `p1_H8_52_64_910002_s1` | 0.920 | X000 | yes | verified | CONDITIONAL |
| `p1_H8_52_64_910002_s2` | 0.920 | X000 | yes | UNKNOWN | CONDITIONAL |
| `p1_H8_52_64_910007_s1` | 0.920 | X000 | yes | UNKNOWN | CONDITIONAL |

Every row above is CONDITIONAL: the removal rule is unresolved, the independence definition is contested, and adding a design to a 20-row submission is not the same as improving it. **Addition-only coverage is reported; replacement-conditioned change is NOT established.**

## 6. Honest blockers

- No functional/agonism evidence exists for any R3 design. That limits the biological claim; it is **not** a frozen-gate failure and no agonism gate is invented here.
- 2 designs are `NOT_STARTED_DEADLINE`; they are incomplete, not failures.
- 60 generated designs were queue-excluded (refold/soluble); they are not screen failures.
- The independence-definition conflict is a **promotion blocker**, not a reporting detail.

## 7. The morning number

- Headline: **70 all-rules PASS** out of 180 screened (38.9%).
- Footnote: **78 structural PASS; 8 `iPTM_low` separately eligible.**
- Do **not** headline the structural count and do not add the live arm into the frozen 70.

