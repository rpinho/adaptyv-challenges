#!/bin/bash
# R3-only parallel wrapper (N=2 per Astra/Kimi ruling 2026-10-25).
#
# Mirrors /workspace/r3_pod_run.sh: it never touches the sibling lane's
# /workspace/pod_run.sh, keeps this shell as the parent so the cutoff/quiesce
# helpers can identify a stable root, and sources the AF2M venv (a bare
# `activate` silently no-ops and leaves the pod looking idle).
#
# usage: r3_pod_run_par.sh <csv> <names|ALL> <outdir> <cap>
set -u
CSV=${1:?csv}; NAMES=${2:-ALL}; OUT=${3:?outdir}; CAP=${4:-2}
export TF_FORCE_UNIFIED_MEMORY=1
export XLA_PYTHON_CLIENT_MEM_FRACTION=4.0
export XLA_PYTHON_CLIENT_PREALLOCATE=false
export COLABFOLD_REBUILD=v1
source /workspace/af2m/venv/bin/activate

LOCK=/tmp/r3_pod_run_par.lock
exec 9>"$LOCK"
if ! flock -n 9; then
  echo "PAR_ALREADY_RUNNING lock=$LOCK"
  exit 0
fi
echo "$$" >"$LOCK.pid"

if [ ! -s "$CSV" ]; then echo "PAR_MISSING_CSV $CSV"; exit 4; fi

# Refuse to become a SECOND driver. Another orchestrator launching the same
# screen is the failure that has recurred tonight; a wrapper cannot tell an
# intentional duplicate from a race, so it always refuses and says who is there.
others=$(ps -eo pid=,args= | awk -v me="$$" '
  $1 != me && $1 != "PID" && (
    ($2=="bash" && $3=="/workspace/r3_pod_run_par.sh" && $4=="/workspace/r3_screen/input.csv") ||
    ($2 ~ /python/ && $3 ~ /\/pod_run_par[[:alnum:]_]*\.py$/ && $4=="/workspace/r3_screen/input.csv")
  ) {print $1}' | tr '\n' ' ')
if [ -n "$others" ]; then
  echo "PAR_REFUSED_DRIVER_ALREADY_RUNNING pids=$others"
  exit 3
fi
if ! awk -v c="$CAP" 'BEGIN{exit !(c+0>=1 && c+0<=2)}'; then
  echo "PAR_BAD_CAP $CAP (allowed 1..2)"; exit 4
fi

echo "PAR_START pid=$$ csv=$CSV out=$OUT cap=$CAP $(date -Is)"
python3 /workspace/pod_run_par.py "$CSV" "$OUT" "$CAP"
echo "PAR_EXIT rc=$? $(date -Is)"
