# DECISION REQUEST — how round-2 candidates enter the C3 gate (2026-10-24 23:20 ET)

I am the orchestrator. Round-2 screen is ~60% done. I need your ruling on ONE thing: the exact
mechanics by which round-2 candidates become v8, because the existing gate cannot currently
express them. Facts first; no proposal from me beyond the options.

## What the gate does today (`scripts/c3_screen_gate_20261025.py`, fail-closed)
- Single writer of `results/c3_submission_v7_20261025.csv`; writes nothing on any failure.
- Reads FIXED evidence paths: `c3_screen_af2m_scores_combined_20261025.json` (44 designs),
  `c3_refold_checks_20261025.json` (24 rows), `c3_structural_checks_20261025.json` (27 rows),
  `c3_groove_reference_20261025.json`, `c3_screen_shortlist_20261024.csv`, `c3_backbone_clusters_20261025.json`.
- Hard-coded assertions: "complete 44/44 screen over the exact input names", `rows_measured ==
  rows_expected` for clusters, floor = max(0.76, min anchor iPTM) = 0.850, replacements only of
  `c3_v_*` slots, 1..7 replacements, 3-mer Jaccard, independent-backbone increase >= 1.
- It has `--input/--scores/--refold/--structural/--clusters` overrides, but the 44-name
  completeness assertion, the anchor list, and the shortlist membership test are tied to round 1.

## Round-2 state
- 36 corrected backbones (111-aa target, byte-identical to the screen payload), 72 MPNN sequences,
  63 refold-pass, 56 also pass the four soluble/non-TM filters.
- Selected 24 (24 distinct TM clusters) and screening them now on 5 A40s; 15/24 scored so far,
  iPTM 0.26-0.94. Two of the 24 were filter failures discovered after launch; their 2 replacements
  are queued and will be screened too, so the final set is 24 valid candidates.
- v7 `1d99f843…` is untouched and remains the best on disk. Nothing has been written toward v8.

## The questions
1. **Evidence topology.** Should round-2 evidence be (a) appended into the existing round-1 files
   (making them 44+24 = 68 scores / 24+24 refolds / etc.), or (b) kept in new round-2 files and the
   gate taught to read round 1 + round 2 together, or (c) should v8 promotion be judged only among
   round-2 candidates against the round-1 floor, with round-1 evidence read-only?
2. **Completeness rule.** The gate asserts 44/44. What is the equivalent completeness assertion for
   round 2 — all 24 screened with a score, or something else? State it exactly so I can implement it.
3. **Floor and anchors.** Does the 0.850 floor and the BindCraft anchor set carry over unchanged to
   round-2 candidates (my reading of your plan §1 is yes), or must round-2 be judged differently
   because the design template differed (T2, AF2M-modeled 111-mer, which you already ruled acceptable)?
4. **Jaccard / independence.** Round-2 candidates are 3-mers against the retained v6/v7 set. Is the
   existing rule (set minimum pairwise similarity must not decrease, each new candidate not closer
   to the retained set than the variant it replaces; independent backbone must increase by >=1)
   applied unchanged, and is cluster `cl##` from `clusters_20261025.json` the correct independence unit?
5. **Write target.** Confirm: a new file `results/c3_submission_v8_20261025.csv`, 20 rows, replacing
   ONLY `c3_v_l65_E5Q`, all 19 other row identities unchanged, and v7 preserved byte-for-byte.
   If a promotion candidate would instead require replacing a *different* slot, say what to do.

Do not propose submitting; nothing is submitted and nobody is contacted. GPU work stops 11:30 ET.
