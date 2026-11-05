# C3 (GLP1R) — Evidence-Based Improvement Audit

**Date:** 2026-10-24 · **Author:** Claude (Opus) orchestrator, autonomous session
**Scope:** Audit the C3 portfolio for *validated* improvements before the Oct 25
23:59 AoE deadline (Ricardo uploads himself ~Mon Oct 26 morning).
**GPU spent this session: 0.** No submissions, no external contact.
**Best-file ranking: `results/c3_submission_v6_20261023.csv` (UNCHANGED).** No v7 written —
see §5 for why, and §6 for the one compute path that could justify one later.

`results/c3_submission_v6_20261023.csv` is preserved byte-for-byte. No older CSV was touched.

---

## 1. What v6 actually is

20 rows = **8 BindCraft + 7 point-mutant variants + 5 RFD4** (the review summary's
"6 RFD4" was stale; corrected). All target the GLP1R **extracellular domain (ECD)**
hydrophobic groove (PDB 6X18). Local CSV integrity previously verified
(`c3_readiness_review_20261024.txt`): 20 unique rows, canonical AAs, 52–100 res.

## 2. Diversity, quantified (not superficial filters)

Method: k-mer (k=3) Jaccard similarity, greedy single-linkage clustering at ≥0.40.
Script: `scripts/c3_diversity_audit_20261024.py` (local, no GPU, numpy only).

**Result: 20 rows collapse to 13 independent backbones.** 10 of 20 slots sit in
three redundant point-mutant families:

| Family | Members in v6 | Independent backbones |
|--------|---------------|-----------------------|
| l57_fbcf76 | parent + Q18K + F38Y + Q18K_F38Y | 1 |
| l65_8f7b63 | parent + E5Q + E53Q + E5Q_E53Q | 1 |
| l100_c674f8 | parent + E79Q_E93Q | 1 |
| 5 other BindCraft | one each | 5 |
| 5 RFD4 | one each | 5 |

The 7 variants are ≤2-residue edits of 3 parents → **they add ~0 backbone diversity.**
Within-family redundancy is highest for l57 and l65 (3 variants each, incl. both
singles *and* the double — the singles are strictly dominated by the double for
"shots on goal").

## 3. The RFD4 pool: diversity is abundant, evidence is not

The 200-design RFD4-Proteina pool (`results/c3_rfd4_sequences.csv`, chain A binders):
**184/195 unselected members pass the stated non-TM + soluble filters**, with
novelty 0.93–0.98 vs. the current 20 (the 5 *already-selected* RFD4 designs score
0.93–0.98 too — i.e. the pool is uniformly, abundantly diverse at the sequence level).

**Conclusion: sequence novelty is not the scarce resource.** Swapping variants for
"more novel" RFD4 members would raise a sequence-diversity number while adding no
binding evidence — the exact cosmetic reranking this task was told to avoid.

## 4. Provenance ladder (why this matters for a KD-scored competition)

Scoring is (1) lowest KD among binders, (2) agonism as upside. Evidence per class:

| Class | Count | Binding evidence | Fold evidence |
|-------|-------|------------------|---------------|
| BindCraft | 8 | **AF2-multimer complex iPTM 0.76–0.85 vs. ECD** + confirmed groove interface | ESMFold refold pLDDT 82–90 |
| Variants | 7 | inherits parent complex (≈) | own ESMFold refold 84–90 |
| RFD4 (selected) | 5 | **none** (never complex-scored) | ESMFold monomer refold 80–94 |
| RFD4 (unselected) | 195 | **none** | **none** (not refolded) |

Verified from the existing BindCraft complex CIF for the top design (l57, no GPU):
binder contacts ECD residues **W33, W39, R40, Y69, Y88, W91, R121** (22 ECD interface
residues; binder presents W41/W48 into the groove). These are genuine, well-posed
**groove binders** — good support for the *binding/KD* objective.

## 5. Candidate-replacement verdict (the bounded audit)

**No unselected candidate is justified by comparable evidence today.** Every unselected
RFD4 member lacks the complex-prediction provenance the BindCraft designs have, and
lacks even the monomer refold the 5 selected RFD4 designs have. Promoting any of them
now would be sequence-novelty reranking.

The 7 variants, though backbone-redundant, each carry *more* binding evidence (parent
complex + own refold) than any unselected pool member. In a 20-slot budget with no
penalty for correlated entries, dropping a validated variant for an unvalidated novel
backbone **trades evidence for a diversity statistic** — net negative.

→ **Keep v6. No v7 is defensible from existing data.**

## 6. The one path to a *validated* improvement (concrete compute need)

To make RFD4 backbones comparable to BindCraft, give them the same binding evidence:
**uniform complex prediction against the identical ECD target.**

- **Target is recovered and reproducible (no fetch needed):** the exact 111-residue ECD
  construct BindCraft used is embedded as chain A in the ranked complex CIFs, e.g.
  `results/pods/c3_glp1r/3_Ranked/c3_glp1r_ecd_groove_forced_l57_*.cif`. Sequence:
  `TVSLWETVQKWREYRRQCQRSLTEDPPPATDLFCNRTFDEYACWPDGEPGSFVNVSCPWYLPWASSVPQGHVYRFCTAEGLWLQKDNSSLPWRDLSECEESSPEEQLLFLY`
  (hotspots set A67–A145; raw full complex at `data/6x18.cif`).
- **Plan (bounded):** run one complex predictor (AF2-multimer, to match BindCraft's
  calibration — *not* Boltz-2, whose iPTM is not cross-comparable) on (a) a ~24-design
  shortlist of the most diverse, soluble, groove-relevant RFD4 members and (b) **the
  current 20**, so ranking is uniform. Detached Modal, separate output prefix
  (`c3_ecd_complex_<date>/`), persist confidence remotely.
- **Promotion gate:** replace a redundant *variant* slot only with an RFD4 backbone whose
  iPTM ≥ the BindCraft floor (~0.76) under the *same* predictor, that passes refold and
  strict CSV integrity. Only then write `results/c3_submission_v7_20261024.csv`.
- **Cost/benefit:** real but bounded GPU (~44 AF2M complexes). Upside is modest — the
  portfolio is already anchored by 8 evidence-bearing BindCraft backbones — so this is
  **reported as a concrete need for explicit go/no-go, not spent autonomously.** It is
  the only non-cosmetic route to a v7.

## 7. Agonism — do NOT claim it

Two-domain model for class B GPCRs (GLP1R): the peptide's **C-terminal** helix binds the
**ECD**; the **N-terminal** residues insert into the **TMD** and *drive activation*
(sources below). Every C3 design binds the ECD groove — the C-terminal-helix site —
and nothing engages the TMD. Therefore:

- These are **binders** (scoreable on KD), **not demonstrable agonists.** Mechanistically
  a groove occupant is more likely a **competitive antagonist** of GLP-1's ECD engagement.
- **Methodology error to fix before upload:** `results/c3_methodology.txt` line 1 says the
  groove "natively accommodates GLP-1's **N-terminal** helix." That is backwards — the ECD
  groove accommodates the **C-terminal** helix. Recommend correcting, and removing/qualifying
  any "agonist" framing to "ECD-groove binder; agonism not structurally supported."
- Structural evidence that *would* support agonism (absent here): a design that stabilizes
  the active-state TMD, or tethers an agonist peptide N-terminus into the TMD core. None do.

## 8. Limitations

- k-mer Jaccard is an alignment-free sequence proxy, not structural identity.
- Interface contacts in §4 are from the AF2 *prediction*, not experiment.
- No affinity or agonism is predicted anywhere here; ESMFold/AF2 metrics are confidence,
  not KD.
- Platform acceptance, eligibility, and novelty clearance remain unverified.

## 9. Exact commands / artifacts

```
# Diversity audit (local, no GPU):
python3 scripts/c3_diversity_audit_20261024.py
# Interface check (local, no GPU): parse chain A/B of a ranked BindCraft complex CIF
#   results/pods/c3_glp1r/3_Ranked/c3_glp1r_ecd_groove_forced_l57_fbcf76*_seq0.cif
# Target for any future complex screen: chain A of that CIF (111 res, sequence in §6).
```
No Modal app launched. No app IDs created this session.

**Sources (agonism mechanism):**
- https://pmc.ncbi.nlm.nih.gov/articles/PMC5118412
- https://www.nature.com/articles/nature25153
- https://pmc.ncbi.nlm.nih.gov/articles/PMC4933217
