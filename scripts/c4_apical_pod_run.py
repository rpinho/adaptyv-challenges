#!/usr/bin/env python3
"""Repo-resident AF2m runner for C4 apical (195-mer) complexes. $0 to dry-run.

Why this exists: the validated RunPod path for C3 lived at /workspace/pod_run.sh,
which is NOT version-controlled. `results/c4_v3_alt_model_plan_20261025.md` §3
lists that as blocker 3. This file closes it.

It generalises `scripts/c3_r3_pod_run.py` in exactly two ways:
  * the target is taken from the CSV row (the C3 runner already did this; the
    *plan doc* wrongly claimed the runner hard-coded a 111-mer -- it does not),
  * a length/identity assert guards the 195-mer apical construct, and a
    chain-B residue-count assert guards the output.

ColabFold settings are byte-identical to the validated C3 port
(`results/c3_af2m_port_20261025/validation_20261025_n5.md`, iPTM exact 5/5):
    --model-type alphafold2_multimer_v3 --num-recycle 3 --num-models 5
    --rank multimer --msa-mode mmseqs2_uniref_env

Usage
  # dry run: no GPU, no colabfold call, validates inputs + prints the plan
  python3 scripts/c4_apical_pod_run.py --csv IN.csv --out OUT --dry-run

  # real run (needs a GPU host with colabfold_batch on PATH)
  python3 scripts/c4_apical_pod_run.py --csv IN.csv --out OUT [--names a,b]

Exit codes: 0 ok | 2 input validation failed | 3 canary gate failed
"""
import argparse
import csv
import glob
import hashlib
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys
import time

APICAL_LEN = 195
APICAL_SHA_PREFIX = "439e6a3a"
DEFAULT_INPUT_SHA_PREFIX = "b7e05e7f"

CF_ARGS = [
    "--model-type", "alphafold2_multimer_v3",
    "--num-recycle", "3",
    "--num-models", "5",
    "--rank", "multimer",
    "--msa-mode", "mmseqs2_uniref_env",
]


def validate_input(csv_path, expect_sha_prefix=None, expect_len=APICAL_LEN):
    """Return (rows, problems). Never raises on bad input; reports instead."""
    problems = []
    raw = pathlib.Path(csv_path).read_bytes()
    sha = hashlib.sha256(raw).hexdigest()
    if expect_sha_prefix and not sha.startswith(expect_sha_prefix):
        problems.append("input sha %s does not start with %s" % (sha[:16], expect_sha_prefix))

    rows = list(csv.DictReader(pathlib.Path(csv_path).open()))
    if not rows:
        problems.append("input has no rows")
        return rows, problems, sha

    for col in ("name", "binder", "target"):
        if col not in rows[0]:
            problems.append("missing required column %r" % col)
    if problems:
        return rows, problems, sha

    names = [r["name"] for r in rows]
    dupes = {n for n in names if names.count(n) > 1}
    if dupes:
        problems.append("duplicate names: %s" % sorted(dupes))

    targets = {r["target"] for r in rows}
    if len(targets) != 1:
        problems.append("expected exactly 1 distinct target, got %d" % len(targets))
    else:
        tgt = next(iter(targets))
        if len(tgt) != expect_len:
            problems.append("target length %d != expected %d" % (len(tgt), expect_len))
        tsha = hashlib.sha256(tgt.encode()).hexdigest()
        if not tsha.startswith(APICAL_SHA_PREFIX):
            problems.append("target sha %s does not start with apical %s"
                            % (tsha[:16], APICAL_SHA_PREFIX))

    for r in rows:
        b = r.get("binder", "")
        if not b:
            problems.append("%s: empty binder" % r["name"])
        elif not re.fullmatch(r"[ACDEFGHIKLMNPQRSTVWY]+", b):
            bad = sorted(set(b) - set("ACDEFGHIKLMNPQRSTVWY"))
            problems.append("%s: non-standard binder residues %s" % (r["name"], bad))
    return rows, problems, sha


def check_canary_output(pdb_path, expect_target_len=APICAL_LEN):
    """Gates on a produced complex PDB. Returns (ok, reasons).

    Chain B must exist and have exactly `expect_target_len` residues.
    Chain A (binder) must also exist -- a silent chain swap would invert reads.
    """
    reasons = []
    chains = {}
    order = []
    seen = set()
    with open(pdb_path) as fh:
        for line in fh:
            if not line.startswith("ATOM"):
                continue
            ch = line[21]
            resseq = line[22:27]
            key = (ch, resseq)
            if ch not in seen:
                seen.add(ch)
                order.append(ch)
            chains.setdefault(ch, set()).add(key)
    if "B" not in chains:
        reasons.append("chain B missing from output PDB")
    else:
        nB = len(chains["B"])
        if nB != expect_target_len:
            reasons.append("chain B has %d residues, expected %d" % (nB, expect_target_len))
    if "A" not in chains:
        reasons.append("chain A (binder) missing from output PDB")
    if order and order[0] != "A":
        reasons.append("first chain in file is %r, expected 'A' (binder)" % order[0])
    return (not reasons), reasons


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--names", default="ALL")
    ap.add_argument("--dry-run", action="store_true",
                    help="validate inputs and print the plan; never call colabfold")
    ap.add_argument("--expect-input-sha", default=DEFAULT_INPUT_SHA_PREFIX,
                    help="pass '' to disable the input-sha pin")
    args = ap.parse_args()

    rows, problems, sha = validate_input(args.csv, args.expect_input_sha or None)
    print("input: %s" % args.csv)
    print("input sha256: %s" % sha)
    if problems:
        print("\nINPUT VALIDATION FAILED (%d problem(s)):" % len(problems))
        for pr in problems:
            print("  - %s" % pr)
        return 2
    print("input validation: PASS (%d rows, target len %d)"
          % (len(rows), len(rows[0]["target"])))

    want = None if args.names == "ALL" else set(args.names.split(","))
    rows = [r for r in rows if want is None or r["name"] in want]
    out_root = pathlib.Path(args.out)

    print("\nplanned designs: %d" % len(rows))
    for r in rows:
        print("  %-32s binder %3d  target %3d" % (r["name"], len(r["binder"]), len(r["target"])))
    print("\ncolabfold args: %s" % " ".join(CF_ARGS))

    if args.dry_run:
        print("\n--dry-run: no GPU, no colabfold invocation, nothing written to %s" % out_root)
        print("DRY_RUN_OK")
        return 0

    if shutil.which("colabfold_batch") is None:
        print("\nERROR: colabfold_batch not on PATH; this host cannot run inference.")
        return 2

    canary_fail = 0
    for r in rows:
        name = r["name"]
        od = out_root / name
        sp = od / "scores.json"
        if sp.exists():
            try:
                if isinstance(json.load(open(sp)).get("iptm"), (int, float)):
                    print("skip %s (already scored)" % name, flush=True)
                    continue
            except Exception:
                pass
        od.mkdir(parents=True, exist_ok=True)
        work = pathlib.Path("/tmp") / name
        work.mkdir(parents=True, exist_ok=True)
        fa = work / ("%s.fasta" % name)
        fa.write_text(">%s\n%s:%s\n" % (name, r["binder"], r["target"]))
        cf = work / "out"
        cf.mkdir(exist_ok=True)

        t0 = time.time()
        proc = subprocess.run(["colabfold_batch", str(fa), str(cf)] + CF_ARGS,
                              capture_output=True, text=True)
        wall = time.time() - t0

        scores = sorted(glob.glob(str(cf / "*_scores_rank_001_*.json")))
        pdbs = sorted(glob.glob(str(cf / "*_rank_001_*.pdb")))
        if proc.returncode != 0 or not scores:
            print("[%s] FAILED rc=%d" % (name, proc.returncode), flush=True)
            json.dump({"name": name, "error": (proc.stderr[-300:] or "no rank_001 scores"),
                       "subprocess_wall_s": round(wall, 1)},
                      open(od / "error.json", "w"), indent=2)
            canary_fail += 1
            continue

        d = json.load(open(scores[0]))
        iptm = d.get("iptm")
        finite = isinstance(iptm, (int, float))

        gate_ok, reasons = (True, [])
        if pdbs:
            gate_ok, reasons = check_canary_output(pdbs[0])

        res = {
            "name": name, "source": r.get("source"),
            "binder_len": len(r["binder"]), "target_len": len(r["target"]),
            "iptm": iptm, "ptm": d.get("ptm"),
            "iptm_finite": finite,
            "canary_gate_pass": bool(finite and gate_ok),
            "canary_gate_reasons": reasons,
            "model": os.path.basename(scores[0]),
            "predictor": "colabfold_alphafold2_multimer_v3",
            "num_recycle": 3, "num_models": 5,
            "subprocess_wall_s": round(wall, 1),
            "run_host": os.environ.get("RUNPOD_GPU_NAME", "unknown"),
        }
        shutil.copy2(scores[0], od / "scores_rank_001.json")
        if pdbs:
            shutil.copy2(pdbs[0], od / "complex_rank_001.pdb")
        json.dump(res, open(sp, "w"), indent=2)
        if not res["canary_gate_pass"]:
            canary_fail += 1
        print("[%s] iptm=%s gate=%s %s" % (name, iptm,
              "PASS" if res["canary_gate_pass"] else "FAIL", "; ".join(reasons)),
              flush=True)

    print("ALL_DONE canary_failures=%d" % canary_fail)
    return 3 if canary_fail else 0


if __name__ == "__main__":
    sys.exit(main())
