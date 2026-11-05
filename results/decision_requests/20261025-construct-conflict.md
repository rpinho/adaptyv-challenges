# DECISION REQUEST — construct mismatch found in C3 round 2 (2026-10-24 21:52 ET)

I am the orchestrator. I STOPPED all RFD4 generation pending your ruling. Facts only:

## The conflict
The RFD4 spec `configs/rfd4/c3_glp1r_ecd.yaml` says `contig: "45-100, /0, F38-154"`.
Generated complexes are 117 target residues, not 111:

  RFD4 frame: TVSL...ECEES **KRGERS** SPEEQLLFLY   (117 aa)
  AF2M target: TVSL...ECEES --------- SPEEQLLFLY   (111 aa)

The RFD4 frame contains `KRGERS` where the AF2M screen target has nothing. I verified the source:
`data/6x18.cif` entity sequence contains `...CEESKRGERSSPEEQLLFLY...`, so the 117-residue form is
the deposited 6x18 construct. The AF2M screen target has `KRGER` removed (111 aa).

I previously told you the construct check PASSED. That was WRONG: my check compared my own
literal F38-154 transcription against the screen target, not the actual generated CIFs. I
corrected it by parsing the RFD4 output directly. This is the mismatch your plan §2 warned about
("If the official target construct is found to differ, stop rather than guessing").

## What exists right now (all pulled to the Mini, pods still running)
- Bin A (52-64): **12/12 backbones complete**, all rc=0, 49-77 s each, binder lengths 52-62,
  target 117 aa — `results/c3_round2_20261025/binA.tgz`.
- Bin C (81-100): **5/12** before I stopped it — `binC_partial.tgz`.
- Bin B (65-80): env was still building on p2; **0 backbones generated**.
- Nothing screened, no MPNN run, no refold run, no CSV touched. v7 `1d99f843…` untouched.

## Questions
1. Which construct governs round 2? Options I can see, but you decide:
   (a) regenerate with the KRGER-deleted 111-residue target so round 2 is comparable to the
       floor and the existing AF2M screen;
   (b) accept the 117-residue frame and re-derive a floor for it (requires new BindCraft-equivalent
       anchors — I have none);
   (c) abandon round 2 for tonight and spend the remaining pods on something else you name.
2. If (a): the RFD4 input is a CIF with the deposited residue numbering. Do I (i) edit the CIF to
   delete 143-147, (ii) supply a sequence-only spec, or (iii) some other exact method? Give the
   concrete command/spec edit and how to verify the produced target is byte-identical to
   `results/c3_screen_input_20261024.csv`.
3. Do the 12 bin-A backbones have any value under option (a)? They were designed against the
   KRGER-containing groove frame; my read is they are NOT comparable, but that is your call.
4. Time: 21:52 ET now (machine clock). C3 GPU stops 12:00 ET. Is a corrected round 2 still
   feasible tonight, and what is the cut-off for starting it?

Do not propose submitting anything; nothing is submitted and nobody is contacted.
