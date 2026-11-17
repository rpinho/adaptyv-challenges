# Retro

What I learned in the Adaptyv Bio protein design challenges, C3, C4 and C5. I am a data engineer and I have never worked in a wet lab. C3 is an agonist binder, 18 de novo designs. C4 is a pH-conditional TfR1 binder. C5 is a KRAS G12D pMHC binder on HLA-A*11:01. These are candidates, and the lab results are not out.

## The rules disqualified what we had (C3)

In C3 we had 20 of them ready, and 8 of those came out of BindCraft, so they are not de novo. The portal says de novo binders only, and it checks that when you submit. So that one was out. I should have checked that first.

What we submitted is 18 of them from one RFD4-Proteina campaign, 52 to 100 residues, all de novo. All 18 have the 5-model AF2-Multimer run on disk, no clashes on any of the 5 models, and a minimum iPTM of 0.86, with a median of 0.90. We measured all 153 pairs, and the closest two are at TM 0.61. 18 of 18 passed novelty at the portal.

One of them without a 5-model run is not a good one, it is one we did not measure. That is what coverage means in our table.

The fix is the same one as the wrong target. Read the terms first and put them in the code, because the check that counts is the one at the portal, and that one runs at the end.

## We scored against the wrong target, twice

In C4 the target is the TfR1 homodimer at acid pH. We generated 342 binders with RFdiffusion and ProteinMPNN, and then we scored them with AlphaFold2-multimer against a monomer, not the homodimer. The one we should have used is P02786-1, residues 121-760, two chains of 640 aa each. I saw it after the first batch, so we scored all 342 again. I should have checked that first. Some of the ones that were high on the monomer dropped on the dimer.

C5 was worse. The target is HLA-A*11:01 and we scored against HLA-A*02:01 for about 80 rounds, which is about 10,000 paired predictions. The first 8 residues of the heavy chain are the same in both of them. Then A*11:01 has tyrosine at 9 and A*02:01 has phenylalanine. So we did all of that work on the wrong one. We also had a 24-residue signal peptide in there, and that should not be in a folded-complex input: 299 aa of A*02:01 precursor instead of 281 aa of A*11:01 mature chain.

I did have the challenge page from October 27, the day it opened, and it has the correct A*11:01 in it. So we had it right on day one and then we lost it when we built the code. I found it on November 7, 38 hours before the deadline, from a diff against that page. We did not know about it until then.

The fix was the same both times. One source of truth, checked byte for byte against the original page. `c5_target.py` runs `verify()` when you use it. The HLA length has to be 281, 9 has to be tyrosine, and all of it has to be in the file I kept from day one. The round script stops if that fails. I think that is step one, not something you do later.

## iPTM ranking is noise (C4)

The most useful thing we got out of C4 was this one. We took the 5-model AF2m ensemble scores on 336 of them, and this is what we got. On the same one, the models do not agree with each other by 0.025 iPTM on average. That is the within-design variance. Between one and the next it is only 0.015 iPTM, and that is the standard deviation. So the noise is bigger than the signal. To rank them by best iPTM is about the same as random. Two AF2m runs of the same one do not agree with each other as much as two different ones do. That is the whole problem with it.

What works better is a consistency filter. We used a 5-model mean iPTM of 0.826 or more, and a 5-model range of 0.03 or less. That one keeps the ones where all the models agree with each other on the pose, and not the ones that got it on one model.

I do not know how general that is. It might be only about our construct, because a 1280 aa receptor is big for AF2m. But it changed how we built everything we submitted after v10.

## The models do not agree on what matters (C5)

The most useful thing we got out of C5 was this one. We used three of them, on the same binders and the same target, and they do not rank them the same way at all.

OpenDDE-AbAg is an antibody-antigen confidence model. It put our best dual-conditioned ones at a delta of +0.72: G12D 0.878, WT 0.151. Boltz-2 is a general structure model, and it has the same ones at a delta of about 0: G12D 0.934, WT 0.943. On Boltz-2 they all bind everything the same. OpenDDE-AbAg is trained on antibody-antigen interfaces and Boltz-2 is a general folding model, so they do not see the same thing in the same complex.

This is not noise, the way iPTM ranking is noise. The models do not agree on what the protein does, and I do not know which one of them to trust.

We scored 735 of them on OpenDDE-AbAg, Boltz-2 and OpenFold3. One of them, c5_r36_b_r3 at 240 aa, is positive on all three: ODE +0.244, B2 +0.091, OF3 +0.079. Two of them are positive on at least two of the models. That is it, out of 735. The best one in v26, at +0.285 on OpenDDE-AbAg, is negative on both Boltz-2 and OpenFold3, so that one is just a single-model artifact.

## All of them bind it without the peptide (C5)

Every one we generated binds the peptide-free HLA+B2M complex, at a confidence above 0.5. All of them, every single one. It does not matter what size they are, from 40 to 250 aa. It does not matter which generator we used, BoltzGen or RFD4-Proteina. And it does not matter how we tried to condition it. The second thing the challenge ranks on is peptide dependence: it should not bind HLA if the peptide is not there.

The small ones do not help. The 40-80 aa ones are worse on this than the 230-250 aa ones.

A competitor batch went out in public, 64 of them from @AllanatrixQ, RFD4-Proteina at 60 aa. Those have 4-7 structural peptide contacts each, and 0 of them with B2M. But on OpenDDE-AbAg that does not come out as peptide dependence at all. The model does not see what the structure shows.

So there is a gap here. The contacts are one thing, and the confidence numbers everybody ranks on are another thing. They might be peptide-dependent in the lab. Or the contacts might not matter for the energy. I do not think we can tell from here. The wet lab will tell us.

## D6 is buried, so we cannot touch it (C5)

Asp6 is the G12D mutation. In the 7OW6 crystal structure its solvent-accessible surface area is 7.9 A^2, so it is buried, and HLA Arg114 holds its carboxylate at 2.96 A. A binder cannot touch D6 the way a small-molecule drug can touch something that is out in the open. To tell G12D from wild-type, it has to use the indirect effects on the peptide positions next to it.

What a binder can read is on top. P4 is at 35 A^2 SASA, P7 is at 74 A^2, and P8 is at 46 A^2. P6 itself is mobile in the apo pMHC, and it is not even there in 7OW4 at 1.81 A resolution. It flips down when the TCR binds, by induced fit.

So to put the hotspots on D6 and nothing else, that is naive. We should have known that. We did it anyway, RFD4 with D6-only hotspots in rounds 4 to 7, and we did not get selective binders out of it. The better way is the indirect one, P4 to P8, which is what the later BoltzGen rounds tried. It is also what the pMHC binder workflow from the Baker lab does (Science 2025). They target the peptide residues that face up.

## Nobody has a binder for this one yet

The ADAPT preprint (doi:10.1101/2025.11.19.689381) found none for A11-VVVGADGVGK, which is our exact target. The 11-target pMHC panel from the Baker lab did not have HLA-A*11:01 in it. We did not find any in the literature for this allele and this peptide.

That makes it harder to check what we compute, because there is nothing to calibrate against. We do not know what a good number looks like here. Nobody has measured one, so there is nothing to go on.

The Adaptyv binder-prescreen v0.5 does add 51 known KRAS G12D TCR binders, from IEDB, VDJdb, PDB and patents. But those are on other HLA alleles, so they do not help us here.

## We should have checked the sequences first

66 of the 342 in C4 had something wrong with the sequence. Some have His6 tags (HHHHHH), some have 5 or more of the same amino acid in a row, and some have low Shannon entropy. Those are red flags for the people who have to make them.

We did it the other way around. We only checked for that when we were building the CSVs we submit, and by then we had scored them all. ProteinMPNN generated them, so the filter should have been there first, before any of it went to AF2m.

## More generators did not give us new hits (C5)

We tried four of them. BoltzGen was the main one, about 18,000 design jobs. Then RFD3-binder, which only does the backbone, so it needs ProteinMPNN. Then RFD4-binder, which does all of it and takes mmCIF. And then we tried the nanobody and antibody protocols too. We did all the sizes from 40 to 250 aa, and we tried it with the peptide only, with the peptide and the groove wall, and with both epitopes.

In 9 late rounds, R132 to R140, with different generators and different settings, we got 0 new consensus ones. Not one. The one we do have came out of early BoltzGen at 230-250 aa, with standard peptide conditioning. That was the first thing we tried.

Adaptyv looked at their own EGFR challenge and found that design diversity quadrupled the hit rate (bioRxiv 2025). That did not happen here. Maybe our consensus threshold is too strict. Or maybe the target is hard enough that more generators do not help at this resolution. I do not know which one of those it is.

## What you submit adds up

Proteinbase keeps everything you submit. To submit v11 does not replace v10. So we submitted different ones in each batch, 20 at a time, and we never submitted the same one twice.

That is in the terms, but it is easy to miss it. It means there is no downside to submitting early. So we did not wait, and we used a different way to rank them in each batch.

## What I still do not know

- If any of them will bind. We optimized for iPTM consistency in C4 and for cross-model consensus in C5, not for what the lab measures. I have no idea if either one correlates.
- If any of the C3 ones do anything to the receptor. Agonism is unproven, and nothing we ran tests it.
- If the acid pH-switch works at all (C4). The whole strategy was proton-coupled design with histidine switches. I think the hypothesis is fine, but nobody has tested it, so we do not know.
- If cross-model consensus is better than one model. We submitted it in C5 v27, but we do not know if a consensus delta of +0.09 tells you more about the lab than a single-model delta of +0.29.
- If the peptide-free binding is an artifact of the models or a real failure. Every team might have it. Or we might be the only ones.
- Why the wrong-allele ones scored well on the correct allele. The best ones we generated against A*02:01 scored better on A*11:01 than the fresh ones we generated against the correct one, +0.285 against +0.187. Maybe BoltzGen had already converged on the groove geometry they share, and the allele-specific residues matter less than the peptide does.

## References

- The Adaptyv Bio challenges, C4 and C5, and the page I kept from October 27.
- What the ADAPT preprint found for A11-VVVGADGVGK, which is nothing: [doi:10.1101/2025.11.19.689381](https://doi.org/10.1101/2025.11.19.689381)
- What the Baker lab does for a pMHC binder, Science 2025.
- What Adaptyv found in their own EGFR challenge, bioRxiv 2025.
