#!/bin/bash
# Pod-side MPNN runner for the sampling-depth arm. Mirrors /workspace/mpnn_run.sh exactly
# (v_48_020, chain A, temp 0.1, batch 1) except: caller supplies the output dir and the seed,
# and num_seq_per_target is 1 (one draw per invocation).
# usage: mpnn_run_sd.sh <pdb> <outdir> <seed>
set -uo pipefail
IN="$1"; OUT="$2"; SEED="$3"
source /workspace/mpnn_env/bin/activate 2>/dev/null || source /workspace/af2m/venv/bin/activate
cd /workspace/third_party/ProteinMPNN || exit 90
mkdir -p "$OUT"
python protein_mpnn_run.py \
  --pdb_path "$IN" \
  --pdb_path_chains A \
  --out_folder "$OUT" \
  --num_seq_per_target 1 \
  --sampling_temp 0.1 \
  --seed "$SEED" \
  --batch_size 1 \
  --model_name v_48_020 \
  --save_score 1
