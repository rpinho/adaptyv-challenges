# C3 / C4 evidence table — one page, symmetric, measured

**Status: EVIDENCE ONLY.** Nothing submitted, nobody contacted, **$0 GPU**. Every number below is read
from a measured JSON/CSV named in the last line of each row — none is recalled or estimated.

## The four candidate artifacts

| | C3 **v8** | C3 **filtered** | C3 **all-five-robust** | C4 **direction-ranked** |
|---|---|---|---|---|
| sha256 | `631ed0bf…` | `1450bcc7…` | `643490da…` | `3370909a…` |
| validator | PASS | PASS | PASS | PASS |
| rows / slots | 20 / 20 | 20 / 20 | 20 / 20 | 20 / 20 |
| structures measured | 20 | 20 | 20 | 20 |
| rank-001 clash-clean | **13/20** | 20/20 | 20/20 | 20/20 |
| rank-001 clash-flagged | **7** | 0 | 0 | 0 |
| worst inter-chain dist | **0.967 Å** | 2.006 Å | 2.041 Å | 2.008 Å |
| components (corrected dedup) | 19 | 20 | 20 | 20 |
| near-identical pairs | **1** | 0 | 0 | 0 |
| iPTM (n measured) | **0.23–0.93** (20) | 0.85–0.93 (12) | 0.85–0.93 (12) | 0.604–0.862 (20) |
| **alt-model evidence** | **none** | 8 seats, 5/5 models | 8 seats, 5/5 models | **none** |
| **clean across ALL models** | — | **2/8** | **8/8** | — |
| composition | 8 BC + 12 RFD4 | 2 BC + 10 RFD4 + 8 arm | 2 BC + 10 RFD4 + 8 arm | 11 site1 + 9 site2 |

## What each column can and cannot support

- **v8** — the incumbent. Its **7 clash flags are real and measured**. The eligibility table flags
  **8** rows: those 7 plus `c3_glp1r_ecd_29` on **low iPTM (0.23)** alone, which is *not* a clash flag —
  `c3_glp1r_ecd_12` is the one row carrying both reasons. Separately, `B_26102611_s1` is **ELIGIBLE and
  not flagged**; an earlier "NO PDB" entry for it was a directory-glob bug (it resolves fine: 2 chains,
  0 clashes, 2.671 Å), which is why the denominator is **20/20 measured, not 19**. It has **zero**
  alternate-model evidence.
- **filtered** and **robust** — identical on every row above **except** five-model cleanliness (2/8 vs
  8/8) and 6 depth-arm seats. They share only **2 of their 8** new seats, so robust had to be verified on
  its own; it was, from raw PDBs.
- **C4** — the acid-ON set. Its **20/20 acid-ON is a selection artifact** (it was ranked on L6), and
  **all 20 margins are borderline** (2.008–2.447 Å, 11 of 20 inside 2.0–2.2 Å). Across the whole 343
  pool only 193 are clash-clean and **none is cleaner than 2.679 Å**, so wider margins do not exist here.
  It has **zero** alternate-model evidence — one PDB per design, no `rank_002–005` anywhere.

## One correction on the dedup column

The "components / near-identical pairs" row is now verified under a **corrected** rule: the shipped
predicate was direction-dependent in TM and its coverage clause never fired (it was exactly 1.0 for all
760 pairs). Under symmetric TM + true paired coverage **no artifact's count changes** — but two claims
need one qualifier each:

- **C4's "0 pairs" holds only in selection order.** Evaluated *order-free with the shipped rule*, C4 has
  **1 pair** (`site1_158` x `site2_1`, 0.7748). It drops out under the corrected rule because its true
  paired coverage is 0.734 < 0.80.
- **Dedup is not evidence for the robust pick.** Kimi's ruling: the challengers are **tied**, so the C3
  ranking rests on 8/8 vs 2/8 alone. (It already did.)

**Measured, not assumed.** The rule fix does **not** change any artifact's membership: re-running the
full C4 selection under the corrected rule returns the **same 20 designs in the same order** (it rejects
`site2_99`, accepts `site1_158` x `site2_1`, exactly as it should), and all four CSVs keep 19/20/20/20
components. **But it does change C3's clustering materially** — 131 of 284 frozen "near-identical" edges (46%)
are rejected by the corrected predicate, and the largest backbone component goes **73 → 33** keys. The
08:00 lexicographic verdict **survives** (depth vs v8 global components with PASS: **25 vs 9** frozen →
**42 vs 9** corrected), so the defective rule was understating the depth arm. That is a direction, not a
multiple: a 99-backbone pool vs a 20-row artifact measures qualifying units, not efficiency, and
single-linkage components do not prove distinct folds.

**The predicate is now symmetric by construction (v2), and it was not before.** My first "corrected" rule
took TM both ways but coverage forward-only; measured on all 19,900 pairs, the **final verdict still
flipped by direction in 67 pairs**. The v2 rule (`max` TM, coverage = `max(paired cols)/max(len)`) is
order-free; it yields **exactly the same 209 edges, 117 components, largest 33 — zero edges changed**, so
every number above stands and now rests on a symmetric predicate rather than a lucky one.

Details and a passing regression validator: `results/c3c4_dedup_symmetry_20261025/` (see `rule_v2.json`,
`predicate_symmetry.json`) and `scripts/dedup_rule_validation_20261025.py`.

## The gap both halves share

**Both C3 challengers and C4 rest on rank-001-only evidence for most of their rows.** Measured on the
frozen 83-design five-model pool: **83/83 (100%) are clean at rank_001 but only 30/83 (36%) stay clean
across all five.** So *64% of designs a rank-001 gate certified have at least one clashing alternate.*
That is a **projection** for the retained rows, not a measurement of them.

## What is genuinely different between the artifacts

Only one axis, and it is narrow: **robust is the only artifact whose every new seat is clean across all
five archived models (8/8).** Filtered achieves 2/8; v8 and C4 cannot be assessed. This is why the C3
one-line ranking names robust as best — and **dedup is explicitly excluded** as supporting evidence
(Kimi: the challengers tie there).

## Money and state

$0 GPU this session; no pods running; Modal at 0 tasks. No artifact was modified — all four CSVs are
byte-identical to their recorded hashes, re-verified after every analysis.

**Sources:** `results/c3_variant_ranking_20261025/ranking.json` · `results/c4_ranked_20261025/c4_acid_ranked_20261025.json` ·
`results/c4_ranked_20261025/clash_population.json` · `results/c3_pool_five_model_20261025/per_design.json` ·
`results/c3_rank1_gate_generalization_20261025/FINDING.md` · `results/c3c4_dedup_symmetry_20261025/`

---

## ADDENDUM 10:55 ET — fourth C3 candidate, and v2 dominance on the same criterion

The table above is **still correct for the four files it describes**. A fourth C3 candidate now exists:

| | C3 **all-five-robust v2** |
|---|---|
| file | `results/c3_challenger_robust_v2_20261025/c3_challenger_all5robust_v2_20261025.csv` |
| sha256 | **`ed3d9e6240178517c10139f658418bd26959ff95d36d413f4e0b79e77aca9d26`** |
| rows | 20 (validator PASS) |
| new seats all-five clash-clean | **8/8**, 0 clashing alternates |
| vs `643490da…` | one seat: **+`910231_sd1` (0.92) / −`910107_sd2` (0.91)** |
| near-identical predicate | **v2** (the only correct one) |
| independent verification | 124 PDB-recomputed pairs, 0 violations, swap-invariant |
| sequence provenance | 20/20 CSV sequences match chain A of their own scored complex |

**Ranking implication:** `ed3d9e62…` ties `643490da…` on the five-model criterion and is the only candidate
free of the dead-coverage defect in its selection, so **it now leads the one-line ranking**. The caveat is
unchanged and applies as much to it as to its predecessor: this is a structural screen, not affinity or
agonism evidence, and it is a post-hoc correction rather than a preregistration.

**Not to be written:** "robust", "replicated", "ensemble-validated", or unqualified "clash-free".

---

## ADDENDUM 11:25 ET — novelty screening (new axis) and two retractions

**$0, read-only.** The four-artifact table above is unchanged and still correct. This adds a **new
measured axis** (database novelty) that no earlier version of this table had, plus corrections to two
claims made earlier in this session.

### Novelty — first screen ever run, both competitions

| | C3 (5 candidates / 36 unique) | C4 (35 unique) |
|---|---|---|
| swissprot / PDB / PLAbDab / therapeutic | 3/36 strict hits | **0/35 strict hits in all four** |
| positive control (same run) | passes | passes |
| strict shuffles | 108 → **0 hits** | 105 → **0 hits** |
| relaxed shuffles | **beat the real designs 24/36 → unusable** | — |
| usable conclusion | only the Ig-family designs hit anything | **novel at strict identity** |

Sources: `results/c3_novelty_screen_20261025/summary.json`, `results/c4_novelty_screen_20261025/`.

### RETRACTED — "ecd_12 resemblance is not confined to the framework"
Wrong null (composition shuffles of ecd_12 cannot detect derivation). With a like-for-like control
(10 unique real heavy/VHH domains after dedup, identical segmentation): ecd_12 framework
**0.660 = 60.0th percentile (median 0.629)**, CDR **0.400 = 0.0th percentile (median 0.500)**,
**4/10** and **10/10** chains match or beat it. *(Corrected 11:45 ET — the earlier
0.633/0.500/5-of-11/9-of-11 came from an alignment-offset bug plus duplicate chains;
see `CORRECTION_20261025.md` §1.)*
→ The "common framework defence is unavailable" conclusion is **withdrawn**.

### WITHDRAWN — "RFD4 arm lands on its own input"
Earlier 6/29 vs 0/15 was measured on a reference set containing essentially **one** Ig domain, and the
two Ig scripts used **different panels** (keyword filtering dropped real Ig chains and would have
admitted a non-Ig structure). Rebuilt balanced panel: 19 Ig chains, inclusion = **TM ≥ 0.50 vs a known
VH**, positive control **1.000000**.

| balanced-panel result | value |
|---|---|
| Nanobody35 is top Ig match | **2/44** (both BindCraft at NB-TM 0.37/0.36 — not Ig folds) |
| among the 6 genuinely Ig-folded designs | **never #1** (ranks 5, 6, 9, 14, 17, 17 of 19) |
| **fold preference (retained)** | RFD4 **6/29** vs **0/15**, Fisher **p = 0.067**, perm **p = 0.070** |

### Two opposing controls on ecd_12 (both new)
| comparison | ecd_12 | reference |
|---|---:|---|
| best germline-VH fident, vs **4 real heavy chains** | **0.629** (lowest of 5) | min 0.704 / median **0.806** / max 0.902; **4/4** at or above it |
| reference set | — | **54 human IGHV germline entries**, qcov ≥ 0.60 (earlier 0.939 control **withdrawn** — it hit IGKC/IGHG1 constant regions) |
| rank among **my own designs** (IGHV only, v2) | **1/36 (97th pct)** | median 0.000; 33/36 have no hit |
| **span-matched (83 aa) germline** | **0.629** | controls min **0.681** / median 0.782–0.806 / max 0.936 — ecd_12 below all 10 |

**Not a germline copy.** Also **not** established as an ordinary de-novo design — and the below-background
score is **not** evidence of derivation: it points the other way, and it clears nothing about provenance.

*(Corrected 12:10 ET: `germline_design_baseline.json` v1 had the same flaw Astra found in the withdrawn
control — all-Swiss-Prot, no coverage floor, hand-typed "IGHV" list. `ecd_29`'s 0.438 "germline" hit was
`A0A0B4J1Y8` = **`LV949_HUMAN`, a lambda LIGHT-chain variable germline**. At the correct floor `ecd_29` has
no germline V-region hit. IGHV hits: **1/36, `ecd_12` only** — conclusion survives, that sentence does not.
v2: `germline_design_baseline_v2.json`.)*

*(Length confound raised on myself at 12:15 and excluded at 12:20: controls truncated to ecd_12's 83 aa at
N-term/middle/C-term keep min 0.681, still above 0.629. `span_matched_germline.json`.)*

### Re-verified, with its limit stated correctly
**All 311** generated CIFs are chain set **`('A','F')`**, **zero** contain chain D → the **recorded** runs
consumed chain F. (Re-verified by parsing `auth_asym_id` with the column index read from the file header.)
**This does NOT mean "the input never reached the generator"** — Astra: *"sibling outputs containing only
A+F do not prove Nanobody35 never influenced ecd_12's actual run."* ecd_12's original run is not on disk,
so its inputs are **unverified**. All nine artifact hashes above re-verified byte-identical.

### Disposition (12:25 ET) — flag RETAINED, allegation NARROWED
Both advisors, re-asked on the corrected evidence, say **keep flagged**; neither says clear. Basis went
Nanobody35-CDR (retracted) → P01767/Lirentelimab excess (measured, absent) → **unresolved provenance**.
At finalization, if unresolved: **omit as a precaution**, not as a proven violation.
`results/decisions/20261025-1145-ecd12-disposition.md`.

**Still not to be written:** "input pull", "contaminated", "confirmed structural convergence", "the
resemblance is not confined to the framework". Details: `results/c3_novelty_screen_20261025/CORRECTION_20261025.md`.
