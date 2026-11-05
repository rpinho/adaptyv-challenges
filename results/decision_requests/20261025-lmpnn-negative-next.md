# Decision request — LigandMPNN clash pilot came back NEGATIVE. What next?

Repo: /Users/ricardo/dev/adaptyv-c4 . Read these first (all small):
- results/c3_e3_ligandmpnn_20261025/RESULT.md          (the pilot result, 67 lines)
- results/c3_e3_ligandmpnn_20261025/pilot/clash_context_pilot.tsv (24 rows, every gate)
- results/c3_e3_ligandmpnn_20261025/pilot/evaluation_20261025.json
- results/c3_e3_result_20261025.md                      (E3: 7/24 eligible; subA best, subB trap)
- results/decisions/20261025-e3-next-work-astra.md      (your Q1-Q4 ruling)
- results/c3_r3_20261025/queue_20261025.json            (R3: 182 eligible designs queued, screening)

## What was measured (numbers, not impressions)
12 clashing E3 parents (iPTM .85-.92), frozen 111-mer target, redesign only binder residues
within 8 A, T=0.1, seed 20261029, one seq per parent per condition.
- side_chain_context OFF: 5/12 eligible, 27 clash pairs
- side_chain_context ON : 2/12 eligible, 23 clash pairs, mean iPTM .894 -> .903
- matched pairs: 3 CONTEXT_WORSE, 0 CONTEXT_BETTER, 2 both-eligible, 7 both-fail
- 24/24 scored, 0 attrition, 0 backbone-backbone clashes, 50 clash pairs, all sequence-rescuable
- vs their own E3 parents: total clashes 30 -> 27 (off) / 23 (on)

So: sequence redesign at the interface helps modestly; adding target side-chain context does not.

## Time budget (hard facts)
- Now ~01:10 ET. R3 AF2M screen runs until the 03:00 ET no-new-jobs cutoff; 182 designs at
  ~250 s/design over 5 pods (~100 min/pod) = full coverage is unlikely; priority is coverage.
- Pods stop themselves ~04:00 ET (self-terminate) / idle-killer 40 min. Mission window ends 08:00.
- Spend so far tonight is pods only ($0.59/h x5). No new Modal spend allowed.

## Questions (answer each briefly and concretely)
Q1. Given this negative result, what is the single highest-value experiment for the remaining
    ~1h45m of GPU time BEFORE the 03:00 cutoff, that does NOT displace R3 screening?
    Options I can see, but you decide (or name something better):
      (a) nothing on GPU — keep 100% of pods on R3 coverage, use CPU to build the v9 evidence pack
      (b) a 2nd clash experiment with a DIFFERENT, cheap lever: e.g. redesign with
          --ligand_mpnn_cutoff_for_score tightened, or higher T for diversity, or
          redesign ALL binder residues (not just 8 A) — but is any of these scientifically
          motivated given the data above, or just p-hacking?
      (c) something about the clash itself: are the 2.0 A clashes actually plausible physics
          (e.g. H-bond/salt-bridge atoms at 2.0 A) and would the gate be wrong to reject them?
          Note: the clash rule is pre-registered and Kimi+Astra already ruled to reject once.
Q2. Should the frozen v8 stay the sole candidate (I assume yes), and is there ANY evidence
    threshold by which these R3 results could justify a v9 before 08:00, or is v9 out of scope
    tonight regardless?
Q3. Is there anything you want verified/audited about the pilot itself before we treat the
    negative result as real? (I already re-derived sequences from FASTAs, checked fixed
    residues, checked 24 unique artifacts / no shadowing, and confirmed 0 backbone-backbone.)
