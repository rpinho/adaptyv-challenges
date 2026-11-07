#!/usr/bin/env python3
"""The one source of truth for the C5 target, with the official sequences.

Written 2026-11-07 after finding that every round in this lane had been scored against
HLA-A*02:01 plus a signal peptide while the challenge target is HLA-A*11:01 mature chain.
See scratchpad/C5_WRONG_TARGET_20261107.md.

Nothing in this lane should carry its own copy of these strings. Import from here, and run
this file (`python3 scripts/c5_target.py`) to re-verify every sequence against the local
verbatim capture of the challenge page before a round or a submission.

Source: results/c5_pagecheck_20261027/c5_challenge_verbatim.txt, captured 2026-10-27 from
https://proteinbase.com/competitions/anthropic-adaptyv-2026/challenges/pmhc
Allele A*11:01:01:01, IPD-IMGT/HLA HLA00043, UniProt Q5S3G3 residues 25-305.
Beta-2-microglobulin: UniProt P61769 residues 21-119.
"""
import os
import sys

# HLA-A*11:01 heavy chain, mature, 281 aa. Starts GSHSMRYFYTSV (Y at 9; A*02:01 has F).
HLA = ("GSHSMRYFYTSVSRPGRGEPRFIAVGYVDDTQFVRFDSDAASQRMEPRAPWIEQEGPEYWDQETRNVKAQSQTDRVDLG"
       "TLRGYYNQSEDGSHTIQIMYGCDVGPDGRFLRGYRQDAYDGKDYIALNEDLRSWTAADMAAQITKRKWEAAHAAEQQRA"
       "YLEGRCVEWLRRYLENGKETLQRTDPPKTHMTHHPISDHEATLRCWALGFYPAEITLTWQRDGEDQTQDTELVETRPAG"
       "DGTFQKWAAVVVPSGEEQRYTCHVQHEGLPKPLTLRWELSSQPT")

# Beta-2-microglobulin, mature, 99 aa. No leading M.
B2M = ("IQRTPKIQVYSRHPAENGKSNFLNCYVSGFHPSDIEVDLLKNGERIEKVEHSDLSFSKDWSFYLLYYTEFTPTEKDEYA"
       "CRVNHVTLSQPKIVKWDRDM")

G12D = "VVVGADGVGK"   # KRAS 7-16 with Gly12->Asp, peptide position 6
WT = "VVVGAGGVGK"     # the wild-type stretch, Gly at position 6

# Submission rules, same source (challenge page "Submission requirements" and FAQ 1/4/5).
MIN_LEN, MAX_LEN = 10, 250
SLOTS = {"track1": 40, "track2": 20, "track3": 20}

# The three targets every tested design is measured against, in the same conditions.
# Ranking: (1) mutation specificity, (2) peptide-dependence against the peptide-free
# complex, (3) affinity. A binder that reads the heavy chain or B2M binds all three.
TARGETS = ("g12d", "wt", "peptide_free")

# What the lane used until 2026-11-07, kept so old result files can be identified as
# belonging to the wrong target rather than silently compared against new ones.
WRONG_HLA_A0201_WITH_LEADER = (
    "MAVMAPRTLLLLLSGALALTQTWAGSHSMRYFFTSVSRPGRGEPRFIAVGYVDDTQFVRFDSDAASQRMEPRAPWIEQEG"
    "PEYWDQETRNVKAQSQTDRVDLGTLRGYYNQSEAGSHTIQIMYGCDVGSDGRFLRGYRQDAYDGKDYIALNEDLRSWTAA"
    "DMAAQITKRKWEAAHVAEQLRAYLEGLCVEWLRRYLENGKETLQRTDAPKTHMTHHAVSDHEATLRCWALSFYPAEITLT"
    "WQRDGEDQTQDTELVETRPAGDGTFQKWAAVVVPSGQEQRYTCHVQHEGLPKPLTLRWE")
WRONG_B2M_WITH_MET = "M" + B2M


def fasta(binder, target="g12d"):
    """Four-chain complex for g12d/wt, three-chain for the peptide-free control."""
    if target not in TARGETS:
        raise ValueError("target must be one of %s, got %r" % (TARGETS,))
    if target == "peptide_free":
        return ">A\n%s\n>B\n%s\n>D\n%s" % (HLA, B2M, binder)
    pep = G12D if target == "g12d" else WT
    return ">A\n%s\n>B\n%s\n>C\n%s\n>D\n%s" % (HLA, B2M, pep, binder)


CAPTURE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                       "results/c5_pagecheck_20261027/c5_challenge_verbatim.txt")


def verify(capture=CAPTURE):
    """Re-read the captured challenge page and confirm each sequence appears in it verbatim."""
    problems = []
    if not os.path.exists(capture):
        return ["capture not found: %s" % capture]
    text = open(capture).read()
    for name, seq in (("HLA", HLA), ("B2M", B2M), ("G12D", G12D), ("WT", WT)):
        if seq not in text:
            problems.append("%s (%d aa) is NOT verbatim in the capture" % (name, len(seq)))
    if len(HLA) != 281:
        problems.append("HLA is %d aa, official is 281" % len(HLA))
    if len(B2M) != 99:
        problems.append("B2M is %d aa, official is 99" % len(B2M))
    if "A*11:01" not in text:
        problems.append("capture does not mention A*11:01 — wrong capture file?")
    if HLA.startswith("MAVMAP") or HLA[8] != "Y":
        problems.append("HLA looks like A*02:01 or still carries the signal peptide")
    return problems


if __name__ == "__main__":
    bad = verify()
    print("HLA  %3d aa  %s..." % (len(HLA), HLA[:24]))
    print("B2M  %3d aa  %s..." % (len(B2M), B2M[:24]))
    print("G12D %3d aa  %s" % (len(G12D), G12D))
    print("WT   %3d aa  %s" % (len(WT), WT))
    print("length cap %d-%d aa, targets %s" % (MIN_LEN, MAX_LEN, ", ".join(TARGETS)))
    if bad:
        print("\nFAILED:")
        for p in bad:
            print("  - " + p)
        sys.exit(1)
    print("\nverified verbatim against %s" % os.path.relpath(CAPTURE))
