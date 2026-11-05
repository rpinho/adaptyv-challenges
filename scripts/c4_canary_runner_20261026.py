#!/usr/bin/env python3
"""
C4 CANARY RUNNER — AF2m re-score of 6 designs against P02786-1 homodimer on RunPod A40.

This script runs ON THE POD. Upload it alongside the FASTA files.
It wraps colabfold_batch with the same settings as the validated C3 port
(alphafold2_multimer_v3, num-recycle 3, num-models 5, rank multimer).

The homodimer construct is ~1344-1380 aa total (binder + 2x 640-aa receptor).
TF_FORCE_UNIFIED_MEMORY=1 is set to allow GPU memory spill to CPU RAM.

Usage (on the pod):
  export TF_FORCE_UNIFIED_MEMORY=1
  export XLA_PYTHON_CLIENT_MEM_FRACTION=4.0
  export XLA_PYTHON_CLIENT_PREALLOCATE=false
  python3 /workspace/c4_canary_runner_20261026.py /workspace/canary_fasta /workspace/canary_out

Ceiling: $100 total (Ricardo confirmed). Serial only — N=1 at this scale.
"""

import argparse
import glob
import hashlib
import json
import os
import pathlib
import subprocess
import sys
import time


SETTINGS = {
    "predictor": "colabfold_alphafold2_multimer_v3",
    "model_type": "alphafold2_multimer_v3",
    "num_recycle": 3,
    "num_models": 5,
    "rank": "multimer",
    "msa_mode": "mmseqs2_uniref_env",
}

EXPECTED_TARGET_SHA256 = "5345f9f5333fd71cdc0ccfdccab7ef27645c89a437e871af6672470a98b16f93"
EXPECTED_TARGET_LEN = 640


def sha256_str(s):
    return hashlib.sha256(s.encode()).hexdigest()


def sha256_file(p):
    return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()


def validate_fasta(fasta_path):
    with open(fasta_path) as f:
        lines = f.readlines()
    header = lines[0].strip()
    seq_line = lines[1].strip()
    parts = seq_line.split(":")
    if len(parts) != 3:
        return False, f"Expected 3 chains (binder:receptor:receptor), got {len(parts)}"
    binder, chain_a, chain_b = parts
    if len(chain_a) != EXPECTED_TARGET_LEN:
        return False, f"Chain A length {len(chain_a)} != {EXPECTED_TARGET_LEN}"
    if len(chain_b) != EXPECTED_TARGET_LEN:
        return False, f"Chain B length {len(chain_b)} != {EXPECTED_TARGET_LEN}"
    if chain_a != chain_b:
        return False, "Chain A != Chain B (homodimer chains must be identical)"
    if sha256_str(chain_a) != EXPECTED_TARGET_SHA256:
        return False, f"Receptor sha256 mismatch"
    return True, f"OK: binder={len(binder)}aa receptor=2x{len(chain_a)}aa total={len(binder)+len(chain_a)+len(chain_b)}aa"


def extract_scores(cf_out_dir, name):
    ranking = cf_out_dir / "ranking_debug.json"
    if not ranking.exists():
        return None
    with open(ranking) as f:
        rank_data = json.load(f)
    order = rank_data.get("order", [])
    if not order:
        return None
    best = order[0]
    scores_file = cf_out_dir / f"{name}_scores_{best}.json"
    if not scores_file.exists():
        score_files = sorted(glob.glob(str(cf_out_dir / f"*scores*.json")))
        if not score_files:
            return None
        scores_file = pathlib.Path(score_files[0])
    with open(scores_file) as f:
        scores = json.load(f)
    iptm = scores.get("iptm", None)
    ptm = scores.get("ptm", None)
    plddt = scores.get("plddt", None)
    if isinstance(plddt, list):
        plddt = sum(plddt) / len(plddt) if plddt else None
    return {
        "iptm": round(iptm, 4) if iptm is not None else None,
        "ptm": round(ptm, 4) if ptm is not None else None,
        "mean_plddt": round(plddt, 2) if plddt is not None else None,
        "best_model": best,
        "n_models": len(order),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("fasta_dir", help="Directory with *_homodimer.fasta files")
    ap.add_argument("out_dir", help="Output directory")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--skip-existing", action="store_true", default=True)
    a = ap.parse_args()

    fasta_dir = pathlib.Path(a.fasta_dir)
    out_root = pathlib.Path(a.out_dir)
    out_root.mkdir(parents=True, exist_ok=True)

    fastas = sorted(fasta_dir.glob("*_homodimer.fasta"))
    if not fastas:
        print("ERROR: no *_homodimer.fasta files found", file=sys.stderr)
        return 1

    print(f"Canary: {len(fastas)} designs")
    print(f"Output: {out_root}")
    print(f"Settings: {json.dumps(SETTINGS)}")
    print(f"Env: TF_FORCE_UNIFIED_MEMORY={os.environ.get('TF_FORCE_UNIFIED_MEMORY', 'NOT SET')}")
    print(f"     XLA_PYTHON_CLIENT_MEM_FRACTION={os.environ.get('XLA_PYTHON_CLIENT_MEM_FRACTION', 'NOT SET')}")
    print()

    # Validate all FASTAs before starting
    for fa in fastas:
        ok, msg = validate_fasta(fa)
        name = fa.stem.replace("_homodimer", "")
        status = "PASS" if ok else "FAIL"
        print(f"  Validate {name}: {status} — {msg}")
        if not ok:
            print(f"ERROR: construct validation failed for {name}", file=sys.stderr)
            return 2

    if a.dry_run:
        print("\nDry run — would fold the above designs. Exiting.")
        return 0

    run_record = {
        "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "pod_id": os.environ.get("RUNPOD_POD_ID", "unknown"),
        "gpu": os.environ.get("RUNPOD_GPU_NAME", "unknown"),
        "settings": SETTINGS,
        "target_sha256": EXPECTED_TARGET_SHA256,
        "designs": [],
    }

    total_wall = 0
    n_ok = 0
    n_fail = 0

    for fa in fastas:
        name = fa.stem.replace("_homodimer", "")
        design_out = out_root / name
        scores_path = design_out / "scores.json"

        if a.skip_existing and scores_path.exists():
            try:
                existing = json.load(open(scores_path))
                if isinstance(existing.get("iptm"), (int, float)):
                    print(f"SKIP {name}: already scored (iPTM={existing['iptm']:.4f})")
                    continue
            except Exception:
                pass

        design_out.mkdir(parents=True, exist_ok=True)
        work = design_out / "work"
        work.mkdir(exist_ok=True)
        cf_out = work / "out"
        cf_out.mkdir(exist_ok=True)

        # Copy FASTA to work dir
        work_fa = work / fa.name
        work_fa.write_text(fa.read_text())

        cmd = [
            "colabfold_batch", str(work_fa), str(cf_out),
            "--model-type", SETTINGS["model_type"],
            "--num-recycle", str(SETTINGS["num_recycle"]),
            "--num-models", str(SETTINGS["num_models"]),
            "--rank", SETTINGS["rank"],
            "--msa-mode", SETTINGS["msa_mode"],
        ]

        print(f"\nFOLD {name} ({fa.name})...")
        t0 = time.time()
        try:
            p = subprocess.run(cmd, capture_output=True, text=True, timeout=7200)
            rc = p.returncode
            stderr_tail = (p.stderr or "")[-1000:]
        except subprocess.TimeoutExpired:
            rc = -2
            stderr_tail = "TIMEOUT after 7200s"
        except Exception as e:
            rc = -1
            stderr_tail = str(e)
        t1 = time.time()
        wall = round(t1 - t0, 1)
        total_wall += wall

        if rc == 0:
            scores = extract_scores(cf_out, name)
        else:
            scores = None

        rec = {
            "name": name,
            "fasta_sha256": sha256_file(fa),
            "exit_code": rc,
            "wall_s": wall,
            "scores": scores,
        }

        if scores and scores.get("iptm") is not None:
            n_ok += 1
            print(f"  OK {name}: iPTM={scores['iptm']:.4f} pTM={scores['ptm']:.4f} "
                  f"pLDDT={scores['mean_plddt']:.1f} wall={wall:.0f}s")
            with open(scores_path, "w") as f:
                json.dump({"iptm": scores["iptm"], "ptm": scores["ptm"],
                           "mean_plddt": scores["mean_plddt"],
                           "best_model": scores["best_model"],
                           "wall_s": wall, "construct": "C_homodimer",
                           "target_sha256": EXPECTED_TARGET_SHA256}, f, indent=2)
        else:
            n_fail += 1
            print(f"  FAIL {name}: rc={rc} wall={wall:.0f}s")
            print(f"  stderr tail: {stderr_tail[-300:]}")
            with open(design_out / "error.json", "w") as f:
                json.dump({"name": name, "exit_code": rc, "wall_s": wall,
                           "stderr_tail": stderr_tail}, f, indent=2)
            if "out of memory" in stderr_tail.lower() or "oom" in stderr_tail.lower():
                print(f"\n  *** OOM DETECTED — A40 (48GB) may be insufficient for {len(fa.read_text().split(':')[0].split(chr(10))[-1])+1280}aa ***")
                print(f"  *** Consider A100 80GB or reducing num_models ***")
                rec["oom"] = True

        run_record["designs"].append(rec)

    run_record["finished_utc"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    run_record["total_wall_s"] = round(total_wall, 1)
    run_record["n_ok"] = n_ok
    run_record["n_fail"] = n_fail
    run_record["n_total"] = len(fastas)

    summary_path = out_root / "canary_run_record.json"
    with open(summary_path, "w") as f:
        json.dump(run_record, f, indent=2)

    print(f"\n{'='*60}")
    print(f"CANARY COMPLETE: {n_ok}/{len(fastas)} OK, {n_fail} failed")
    print(f"Total wall: {total_wall:.0f}s ({total_wall/60:.1f} min)")
    print(f"Record: {summary_path}")

    if n_fail > 0:
        print(f"\nCANARY GATE: FAIL — {n_fail}/{len(fastas)} designs failed")
        return 1
    else:
        print(f"\nCANARY GATE: PASS — 6/6 valid outputs")
        return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
