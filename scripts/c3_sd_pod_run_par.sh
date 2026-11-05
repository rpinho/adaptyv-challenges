#!/bin/bash
# Sampling-depth arm parallel wrapper (N=2). Same fold settings and env as the R3 wrapper;
# separate lock, separate csv/out paths, and a cutoff epoch supplied by the caller so the
# arm can never inherit R3's 03:00 boundary or admit past its own cap.
#
# usage: sd_pod_run_par.sh <csv> <names|ALL> <outdir> <cap> <cutoff_epoch>
set -u
CSV=${1:?csv}; NAMES=${2:-ALL}; OUT=${3:?outdir}; CAP=${4:-2}; CUTOFF=${5:?cutoff_epoch}
export TF_FORCE_UNIFIED_MEMORY=1
export XLA_PYTHON_CLIENT_MEM_FRACTION=4.0
export XLA_PYTHON_CLIENT_PREALLOCATE=false
export COLABFOLD_REBUILD=v1
export R3_CUTOFF_EPOCH="$CUTOFF"
source /workspace/af2m/venv/bin/activate

LOCK=/tmp/sd_pod_run_par.lock
exec 9>"$LOCK"
if ! flock -n 9; then
  echo "SD_PAR_ALREADY_RUNNING lock=$LOCK"
  exit 0
fi
echo "$$" >"$LOCK.pid"
[ -s "$CSV" ] || { echo "SD_PAR_MISSING_CSV $CSV"; exit 4; }
mkdir -p "$OUT"

others=$(ps -eo pid=,args= | awk -v me="$$" '
  $1 != me && (
    ($2=="bash" && $3=="/workspace/sd1/sd_pod_run_par.sh") ||
    ($2 ~ /python/ && $3 ~ /\/pod_run_par[[:alnum:]_]*\.py$/ && $4=="/workspace/sd1/input.csv")
  ) {print $1}' | tr '\n' ' ')
if [ -n "$others" ]; then
  echo "SD_PAR_REFUSED_DRIVER_ALREADY_RUNNING pids=$others"
  exit 3
fi
if ! awk -v c="$CAP" 'BEGIN{exit !(c+0>=1 && c+0<=2)}'; then
  echo "SD_PAR_BAD_CAP $CAP (allowed 1..2)"; exit 4
fi
echo "SD_PAR_START pid=$$ csv=$CSV out=$OUT cap=$CAP cutoff=$CUTOFF $(date -Is)"
python3 /workspace/pod_run_par.py "$CSV" "$OUT" "$CAP"
echo "SD_PAR_EXIT rc=$? $(date -Is)"
