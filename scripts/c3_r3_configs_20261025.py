#!/usr/bin/env python3
"""Materialize Kimi's R3 H4-spread configs (residues 5, 40, 63, 93 only).

Kimi R3 ruling: copy the corresponding round-2 config and change ONLY C_HOT membership.
Input, contig, C_CRDGRP, C_SEQ, C_SEQ_PROB_CYS stay byte-identical. Never overwrites the
round-2 configs; refuses to replace a differing existing file.
"""
import hashlib
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
CFG = ROOT / "configs/rfd4"
BINS = {"52_64": "52-64", "65_80": "65-80", "81_100": "81-100"}
ATOMS = {5: "F/*/5/[CE2,NE1]", 40: "F/*/40/[OE1,OE2]",
         63: "F/*/63/[CE2,NE1]", 93: "F/*/93/[NH1,NH2]"}
H4 = [5, 40, 63, 93]


def main():
    wrote = []
    for bin_key, contig in BINS.items():
        src = CFG / f"c3_ecd111_r2_{bin_key}.yaml"
        text = src.read_text()
        start = text.index("    C_HOT:")
        head = text[:start]
        head = head.replace(f"c3_ecd111_r2_{bin_key}:", f"c3_ecd111_r3_h4_{bin_key}:", 1)
        hot = "\n".join(f"        - select: \"sel('{ATOMS[r]}')\"" for r in H4)
        out_text = f"{head}    C_HOT:\n      true:\n{hot}\n"
        # invariants: everything except the name and C_HOT must be identical
        assert head.split("\n", 1)[1] == text.split("\n", 1)[1][:len(head.split("\n", 1)[1])]
        dst = CFG / f"c3_ecd111_r3_h4_{bin_key}.yaml"
        if dst.exists():
            if dst.read_text() != out_text:
                print(f"REFUSING: {dst.name} differs", file=sys.stderr)
                return 1
            continue
        dst.write_text(out_text)
        wrote.append((dst.name, hashlib.sha256(out_text.encode()).hexdigest()[:16]))
    for n, h in wrote:
        print(f"wrote {n} sha256[:16]={h}")
    print(f"h4 hotspots={H4}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
