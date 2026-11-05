#!/usr/bin/env bash
# Repo-resident setup for an AF2m (ColabFold) pod used by C4 apical trials.
# Idempotent: safe to re-run. Container disks are wiped on pod restart, so this
# must exist in the repo -- the previous C3 run relied on an unversioned
# /workspace/pod_run.sh, which is exactly the gap this closes.
#
# Usage (on the pod):  bash c4_pod_setup.sh [/opt/localcolabfold]
set -euo pipefail

DEST="${1:-/opt/localcolabfold}"
COLABFOLD_REPO="https://raw.githubusercontent.com/YoshitakaMo/localcolabfold/main/install_colabbatch_linux.sh"

echo "=== [1/4] environment ==="
nvidia-smi --query-gpu=name,memory.total --format=csv,noheader || echo "WARN: nvidia-smi absent"
python3 -V
df -h / | tail -1

echo "=== [2/4] localcolabfold -> ${DEST} ==="
if [ -x "${DEST}/bin/colabfold_batch" ]; then
  echo "already installed at ${DEST}; skipping"
else
  export PATH="/usr/local/bin:$PATH"
  curl -fsSL "$COLABFOLD_REPO" -o /tmp/install_colabbatch_linux.sh
  bash /tmp/install_colabbatch_linux.sh "$DEST"
fi

echo "=== [3/4] weights + MSA databases (large; ~3-4 GB) ==="
# setup_databases downloads both the model params and the search DBs.
if [ -d "${DEST}/colabfold" ] && [ -n "$(ls -A "${DEST}/colabfold" 2>/dev/null)" ]; then
  echo "colabfold data dir non-empty; skipping"
else
  "${DEST}/bin/setup_databases.sh" "${DEST}" || echo "WARN: setup_databases returned nonzero"
fi

echo "=== [4/4] verify ==="
"${DEST}/bin/colabfold_batch" --help >/dev/null && echo "colabfold_batch OK"
ls -la "${DEST}" | head
echo "SETUP_DONE"
