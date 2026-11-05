#!/bin/bash
# Seed-replication parallel wrapper (N=2). Same environment as the sampling-depth wrapper, but
# a separate lock, separate csv/out paths, and this arm's own 07:00 ET cutoff.
# usage: seedrep_pod_run.sh <csv> <names|ALL> <outdir> <cap> <cutoff_epoch>
set -u
CSV=${1:?csv}; NAMES=${2:-ALL}; OUT=${3:?outdir}; CAP=${4:-2}; CUTOFF=${5:?cutoff_epoch}
export TF_FORCE_UNIFIED_MEMORY=1
export XLA_PYTHON_CLIENT_MEM_FRACTION=4.0
export XLA_PYTHON_CLIENT_PREALLOCATE=false
export COLABFOLD_REBUILD=v1
export R3_CUTOFF_EPOCH="$CUTOFF"
source /workspace/af2m/venv/bin/activate
LOCK=/tmp/seedrep_pod_run.lock
exec 9>"$LOCK"
if ! flock -n 9; then echo "SEEDREP_ALREADY_RUNNING lock=$LOCK"; exit 0; fi
echo "$$" >"$LOCK.pid"
[ -s "$CSV" ] || { echo "SEEDREP_MISSING_CSV $CSV"; exit 4; }
mkdir -p "$OUT"
others=$(ps -eo pid=,args= | awk -v me="$$" '
  $1 != me && (
    ($2=="bash" && $3=="/workspace/seedrep/seedrep_pod_run.sh") ||
    ($2 ~ /python/ && $3 ~ /\/pod_run_seed\.py$/ && $4=="/workspace/seedrep/input.csv")
  ) {print $1}' | tr '\n' ' ')
if [ -n "$others" ]; then echo "SEEDREP_REFUSED_DRIVER_ALREADY_RUNNING pids=$others"; exit 3; fi
if ! awk -v c="$CAP" 'BEGIN{exit !(c+0>=1 && c+0<=2)}'; then echo "SEEDREP_BAD_CAP $CAP (allowed 1..2)"; exit 4; fi
echo "SEEDREP_START pid=$$ csv=$CSV out=$OUT cap=$CAP cutoff=$CUTOFF $(date -Is)"
python3 /workspace/pod_run_seed.py "$CSV" "$OUT" "$CAP"
rc=$?
echo "SEEDREP_EXIT rc=$rc $(date -Is)"
exit $rc
