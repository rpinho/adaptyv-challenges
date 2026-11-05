#!/usr/bin/env python3
"""Materialize the E3 hotspot-arm RFD4 configs (Astra 2026-10-25 plan).

Pure text generation from the frozen round-2 configs; no GPU, no network, and it refuses to
overwrite an existing file. Only C_HOT membership changes between arms — every other line is
byte-copied from the validated round-2 config for that length bin.
"""
import hashlib
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
CFG = ROOT / "configs/rfd4"
BINS = {"52_64": "52-64", "65_80": "65-80", "81_100": "81-100"}

# residue -> atom selector, VERBATIM from the round-2 configs (round-1 hotspot set)
ATOMS = {
    5: "F/*/5/[CE2,NE1]",
    11: "F/*/11/[CE2,NE1]",
    12: "F/*/12/[NH1,NH2]",
    40: "F/*/40/[OE1,OE2]",
    41: "F/*/41/[OH]",
    60: "F/*/60/[OH]",
    63: "F/*/63/[CE2,NE1]",
    93: "F/*/93/[NH1,NH2]",
}
ARMS = {
    "ctrl": [5, 11, 12, 40, 41, 60, 63, 93],
    "subA": [11, 12, 40, 60],
    "subB": [41, 60, 63, 93],
}
SEEDS = {"ctrl": 26103000, "subA": 26103100, "subB": 26103200}


def render(bin_key, arm):
    contig = BINS[bin_key]
    hot = "\n".join(f"        - select: \"sel('{ATOMS[r]}')\"" for r in ARMS[arm])
    return f"""c3_ecd111_e3_{arm}_{bin_key}:
  input: ../../data/c3_ecd111_af2m_target_20261025.cif
  contig: "{contig}, /0, F1-111"
  conditions:
    C_CRDGRP:
      1:
        - select: "sel('F/*/[1-111]') and is_protein_backbone and not has_nan_coord()"
    C_SEQ:
      true:
        - select: "sel('F/*/[1-111]')"
    C_SEQ_PROB_CYS:
      0.0:
        - select: "sel('A')"
    C_HOT:
      true:
{hot}
"""


def main():
    wrote, skipped = [], []
    for arm in ARMS:
        for bin_key in BINS:
            p = CFG / f"c3_ecd111_e3_{arm}_{bin_key}.yaml"
            text = render(bin_key, arm)
            if p.exists():
                if p.read_text() != text:
                    print(f"REFUSING: {p.name} exists with different content", file=sys.stderr)
                    return 1
                skipped.append(p.name)
                continue
            p.write_text(text)
            wrote.append((p.name, hashlib.sha256(text.encode()).hexdigest()[:16]))
    for n, h in wrote:
        print(f"wrote {n} sha256[:16]={h}")
    for n in skipped:
        print(f"unchanged {n}")
    print(f"\narms={list(ARMS)} bins={list(BINS)} seeds={SEEDS}")
    print("seed offsets: +0..7 -> 52_64, +8..15 -> 65_80, +16..23 -> 81_100")
    return 0


if __name__ == "__main__":
    sys.exit(main())
