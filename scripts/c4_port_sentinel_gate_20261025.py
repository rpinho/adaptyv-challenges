#!/usr/bin/env python3
"""Fail-closed sentinel gate for the C4 Boltz-2 Modal -> A40 port.

WHY THIS EXISTS
The first port attempt produced a real disagreement (iPTM 0.7057 reference vs
0.5187 on the A40) and could not be diagnosed, because the pod lane archived no
input YAML, no MSA, no MSA hash, no seed, no config hash and no PDB. A tolerance
that can be computed but not explained is not a validated port.

This harness makes that failure class structurally impossible to repeat: a
sentinel run that does not carry complete, hash-pinned provenance is reported
INCONCLUSIVE. It can never be reported PASS.

WHAT IT CHECKS, PER SENTINEL RUN
  R1 identity      design resolves to exactly one reference record, name exact
  R2 target        run target sequence is byte-identical to the pinned reference
                   target (closes the 154-vs-195-residue hypothesis by
                   construction rather than by argument)
  R3 inputs        input YAML present, sha256 recorded and recomputed
  R4 msa           MSA file present, sha256 recorded and recomputed; the MSA
                   must be supplied offline (use_msa_server must be false) so
                   the bytes tested are the bytes archived
  R5 software      boltz version, torch, GPU, seed, diffusion_samples,
                   recycling_steps all recorded
  R6 outputs       confidence JSON present with finite iptm/confidence, plus a
                   PDB whose chain B length equals the reference target length
  R7 agreement     |d iPTM| <= 0.03 AND |d confidence| <= 0.03 vs reference

Verdicts: PASS / FAIL / INCONCLUSIVE. Missing or unverifiable provenance is
INCONCLUSIVE, never PASS. Any FAIL among gate members makes the gate FAIL. Any
INCONCLUSIVE among gate members makes the gate INCONCLUSIVE. PASS requires every
gate member to be PASS.

usage:
  python3 scripts/c4_port_sentinel_gate_20261025.py --spec SPEC.json
  python3 scripts/c4_port_sentinel_gate_20261025.py --spec SPEC.json --selftest
  python3 scripts/c4_port_sentinel_gate_20261025.py --spec SPEC.json --replay-known-failure

Exit codes: 0 PASS, 10 FAIL, 11 INCONCLUSIVE, 12 spec/config error.
Read-only with respect to every other artifact. No GPU, no network.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
DEFAULT_ARCHIVE = ROOT / "results/c4_apical_consolidated_results.json"
IPTM_TOL = 0.03
CONF_TOL = 0.03

PASS, FAIL, INCONCLUSIVE = "PASS", "FAIL", "INCONCLUSIVE"

EXIT = {PASS: 0, FAIL: 10, INCONCLUSIVE: 11}
SERVER_ERROR = 12


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _finite(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x)


def load_reference(archive_path, name):
    """Return the single archived reference record for `name`, or raise."""
    data = json.loads(pathlib.Path(archive_path).read_text())
    hits = [r for r in data["results"] if r.get("name") == name]
    if len(hits) != 1:
        raise KeyError(f"reference lookup for {name!r} returned {len(hits)} records")
    rec = hits[0]
    for key in ("iptm", "confidence"):
        if not _finite(rec.get(key)):
            raise KeyError(f"reference record {name!r} has no finite {key}")
    return rec, data["target_len"]


def pdb_chain_lengths(path):
    """Chain id -> number of CA atoms. Cheap, and independent of parser quirks."""
    seen = {}
    with open(path) as fh:
        for line in fh:
            if line.startswith(("ATOM  ", "HETATM")) and line[12:16].strip() == "CA":
                seen[line[21]] = seen.get(line[21], 0) + 1
    return seen


def check_sentinel(name, role, gate_member, run_dir, archive_path, spec):
    """Evaluate one sentinel. Returns a fully serialisable evidence dict."""
    ev = {"name": name, "role": role, "gate_member": bool(gate_member),
          "checks": [], "verdict": PASS, "reasons": []}

    def add(check, ok, detail, fatal_if_missing=True):
        ev["checks"].append({"check": check, "ok": bool(ok), "detail": detail})
        if not ok:
            if fatal_if_missing:
                ev["verdict"] = INCONCLUSIVE
                ev["reasons"].append(f"{check}: {detail}")
            return False
        return True

    try:
        ref, ref_target_len = load_reference(archive_path, name)
    except Exception as exc:                                    # R1
        add("R1 identity", False, f"{type(exc).__name__}: {exc}")
        return ev

    ev["reference"] = {"iptm": ref["iptm"], "confidence": ref["confidence"],
                       "complex_plddt": ref.get("complex_plddt"),
                       "target": ref.get("target"),
                       "target_len": ref_target_len}
    add("R1 identity", True,
        f"one reference record; iPTM {ref['iptm']:.4f}, conf {ref['confidence']:.4f}")

    run_dir = pathlib.Path(run_dir)
    meta_path = run_dir / "provenance.json"
    if not add("R3 inputs", meta_path.is_file(), f"missing {meta_path}"):
        return ev
    meta = json.loads(meta_path.read_text())
    ev["provenance"] = meta

    # --- R2 target identity (bytes, not length) -----------------------------
    target_seq = meta.get("target_sequence")
    pinned = pinned_target_sequence(spec, archive_path)
    if not add("R2 target", bool(target_seq),
               "run records no target_sequence"):
        return ev
    if not add("R2 target", len(target_seq) == ref_target_len,
               f"target length {len(target_seq)} vs reference {ref_target_len}"):
        return ev
    if not add("R2 target", target_seq == pinned,
               "target sequence is not byte-identical to the pinned reference target"):
        return ev
    ev["target_matches_reference"] = True

    # --- R4 offline MSA + hash ---------------------------------------------
    if not add("R4 msa", meta.get("use_msa_server") is False,
               "use_msa_server must be false; online MSA bytes are unpinnable"):
        return ev
    msa_rel = meta.get("msa_path")
    msa_want = meta.get("msa_sha256")
    msa_path = run_dir / msa_rel if msa_rel else None
    if not add("R4 msa", bool(msa_path) and msa_path.is_file(),
               f"missing MSA file ({msa_rel})"):
        return ev
    msa_got = sha256_file(msa_path)
    if not add("R4 msa", msa_got == msa_want,
               f"MSA sha256 {msa_got[:12]}... vs recorded {str(msa_want)[:12]}..."):
        return ev

    # --- R3 input YAML ------------------------------------------------------
    yaml_rel = meta.get("input_yaml")
    yaml_path = run_dir / yaml_rel if yaml_rel else None
    if not add("R3 inputs", bool(yaml_path) and yaml_path.is_file(),
               f"missing input YAML ({yaml_rel})"):
        return ev
    if not add("R3 inputs", sha256_file(yaml_path) == meta.get("input_yaml_sha256"),
               "input YAML sha256 does not match recorded value"):
        return ev

    # --- R5 software / seeds ------------------------------------------------
    required = ("boltz_version", "torch", "gpu", "seed",
                "diffusion_samples", "recycling_steps", "config_sha256")
    absent = [k for k in required if meta.get(k) in (None, "")]
    if not add("R5 software", not absent, f"missing fields: {absent}"):
        return ev

    # --- R6 outputs ---------------------------------------------------------
    conf_rel = meta.get("confidence_json")
    conf_path = run_dir / conf_rel if conf_rel else None
    if not add("R6 outputs", bool(conf_path) and conf_path.is_file(),
               f"missing confidence JSON ({conf_rel})"):
        return ev
    conf = json.loads(conf_path.read_text())
    iptm, confidence = conf.get("iptm"), conf.get("confidence_score", conf.get("confidence"))
    if not add("R6 outputs", _finite(iptm) and _finite(confidence),
               f"non-finite scores: iptm={iptm}, confidence={confidence}"):
        return ev

    pdb_rel = meta.get("pdb")
    pdb_path = run_dir / pdb_rel if pdb_rel else None
    if not add("R6 outputs", bool(pdb_path) and pdb_path.is_file(),
               f"missing PDB ({pdb_rel})"):
        return ev
    chains = pdb_chain_lengths(pdb_path)
    ev["pdb_chains"] = chains
    chain_b = chains.get("B") or chains.get("1")
    if not add("R6 outputs", chain_b == ref_target_len,
               f"receptor chain CA count {chain_b} vs reference target {ref_target_len}"):
        return ev

    # --- R7 agreement -------------------------------------------------------
    d_iptm = iptm - ref["iptm"]
    d_conf = confidence - ref["confidence"]
    ev["candidate"] = {"iptm": iptm, "confidence": confidence}
    ev["delta"] = {"iptm": d_iptm, "confidence": d_conf}
    ok = abs(d_iptm) <= IPTM_TOL and abs(d_conf) <= CONF_TOL
    ev["checks"].append({
        "check": "R7 agreement", "ok": ok,
        "detail": f"d iPTM {d_iptm:+.4f} (tol {IPTM_TOL}), "
                  f"d conf {d_conf:+.4f} (tol {CONF_TOL})"})
    ev["verdict"] = PASS if ok else FAIL
    if not ok:
        ev["reasons"].append(
            f"R7 agreement: exceeds tolerance (d iPTM {d_iptm:+.4f}, d conf {d_conf:+.4f})")
    return ev


def pinned_target_sequence(spec, archive_path):
    """The reference target bytes every sentinel must reproduce.

    Pinned in the spec so the comparison is a byte comparison against a value
    frozen before any pod run — not against whatever the run itself recorded.
    """
    seq = spec.get("target", {}).get("sequence")
    if not seq:
        raise ValueError("spec.target.sequence is required (pinned reference target)")
    if len(seq) != spec["target"].get("length"):
        raise ValueError("spec.target.length does not match spec.target.sequence")
    return seq


def evaluate(spec, archive_path):
    """Evaluate the whole spec. Provenance failures dominate agreement failures."""
    sentinels = [check_sentinel(s["name"], s.get("role", "sentinel"),
                                s.get("gate_member", True), s["run_dir"],
                                archive_path, spec)
                 for s in spec["sentinels"]]
    gate = [s for s in sentinels if s["gate_member"]]
    if not gate:
        raise ValueError("spec has no gate members")

    if any(s["verdict"] == INCONCLUSIVE for s in gate):
        overall = INCONCLUSIVE
    elif any(s["verdict"] == FAIL for s in gate):
        overall = FAIL
    else:
        overall = PASS

    return {
        "artifact": "C4 port sentinel gate — evaluation only, not an authorization",
        "rule": f"|d iPTM| <= {IPTM_TOL} AND |d confidence| <= {CONF_TOL} "
                f"per gate member, on complete hash-pinned offline provenance",
        "fail_closed": "missing or unverifiable provenance is INCONCLUSIVE, never PASS",
        "overall": overall,
        "gate_members": len(gate),
        "counts": {v: sum(1 for s in sentinels if s["verdict"] == v)
                   for v in (PASS, FAIL, INCONCLUSIVE)},
        "sentinels": sentinels,
    }


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--spec", required=True)
    ap.add_argument("--archive", default=str(DEFAULT_ARCHIVE))
    ap.add_argument("--out", default=None)
    ap.add_argument("--quiet", action="store_true")
    args = ap.parse_args(argv)

    try:
        spec = json.loads(pathlib.Path(args.spec).read_text())
    except Exception as exc:
        print(f"spec error: {exc}", file=sys.stderr)
        return SERVER_ERROR

    try:
        result = evaluate(spec, args.archive)
    except Exception as exc:
        print(f"evaluation error: {type(exc).__name__}: {exc}", file=sys.stderr)
        return SERVER_ERROR

    if args.out:
        pathlib.Path(args.out).write_text(json.dumps(result, indent=1) + "\n")

    if not args.quiet:
        for s in result["sentinels"]:
            marker = "" if s["gate_member"] else " (diagnostic)"
            print(f"{s['verdict']:12} {s['name']}{marker}")
            for r in s["reasons"]:
                print(f"    - {r}")
        print(f"\nOVERALL: {result['overall']}  counts={result['counts']}")
    return EXIT[result["overall"]]


if __name__ == "__main__":
    sys.exit(main())
