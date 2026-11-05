#!/bin/bash
# R3-only wrapper. It never touches the sibling lane's /workspace/pod_run.sh.
set -u
export TF_FORCE_UNIFIED_MEMORY=1
export XLA_PYTHON_CLIENT_MEM_FRACTION=4.0
export XLA_PYTHON_CLIENT_PREALLOCATE=false
export COLABFOLD_REBUILD=v1
source /workspace/af2m/venv/bin/activate
# Keep this shell as the parent. The cutoff/quiesce helpers identify the R3
# driver by its exact command, and `exec` would erase that stable root.
python3 /workspace/r3_screen/c3_r3_pod_run.py "$@"
