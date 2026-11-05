#!/bin/bash
# Stage the N=2 parallel runner + wrapper on the R3 pods, hash-checked.
# READ-ONLY on results; does not stop or start any driver.
# usage: c3_r3_stage_par_20261025.sh p1 [p2 ...]
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1
KEY=$HOME/.ssh/runpod_ed25519
RUNNER=scripts/pod_run_par_20261025.py
WRAPPER=scripts/c3_r3_pod_run_par.sh
LOCAL_R=$(shasum -a 256 "$RUNNER" | cut -d' ' -f1)
LOCAL_W=$(shasum -a 256 "$WRAPPER" | cut -d' ' -f1)
spec_of() { case $1 in p1) echo 63.141.33.138:22113;; p2) echo 194.68.245.32:22065;;
  p3) echo 69.30.85.102:22129;; p4) echo 194.68.245.69:22022;;
  p5) echo 194.68.245.147:22117;; *) return 1;; esac; }
rc=0
for p in "$@"; do
  spec=$(spec_of "$p") || { echo "UNKNOWN_POD $p"; rc=1; continue; }
  host=${spec%%:*}; port=${spec#*:}
  RSYNC=(rsync -az -e "ssh -i $KEY -p $port -o StrictHostKeyChecking=no -o ConnectTimeout=15 -o BatchMode=yes")
  "${RSYNC[@]}" "$RUNNER" root@$host:/workspace/pod_run_par.py || { echo "STAGE_FAIL $p runner_copy"; rc=1; continue; }
  "${RSYNC[@]}" "$WRAPPER" root@$host:/workspace/r3_pod_run_par.sh || { echo "STAGE_FAIL $p wrapper_copy"; rc=1; continue; }
  ssh -n -i "$KEY" -o StrictHostKeyChecking=no -o ConnectTimeout=15 -p "$port" root@$host \
    "chmod +x /workspace/r3_pod_run_par.sh" || { echo "STAGE_FAIL $p chmod"; rc=1; continue; }
  read -r rsha wsha < <(ssh -n -i "$KEY" -o StrictHostKeyChecking=no -o ConnectTimeout=15 -p "$port" root@$host \
    "sha256sum /workspace/pod_run_par.py; sha256sum /workspace/r3_pod_run_par.sh" | awk '{print $1}' | tr '\n' ' ')
  if [ "$rsha" != "$LOCAL_R" ] || [ "$wsha" != "$LOCAL_W" ]; then
    echo "STAGE_SHA_MISMATCH $p runner=$rsha want=$LOCAL_R wrapper=$wsha want=$LOCAL_W"; rc=1; continue
  fi
  # Syntax check inside the pod's own python.
  out=$(ssh -n -i "$KEY" -o StrictHostKeyChecking=no -o ConnectTimeout=15 -p "$port" root@$host \
    "/workspace/af2m/venv/bin/python3.10 -m py_compile /workspace/pod_run_par.py && echo PYC_OK; bash -n /workspace/r3_pod_run_par.sh && echo SH_OK" 2>&1)
  case "$out" in *PYC_OK*SH_OK*) ;; *) echo "STAGE_SYNTAX_FAIL $p $out"; rc=1; continue;; esac
  echo "STAGED_OK $p runner=${rsha:0:12} wrapper=${wsha:0:12}"
done
exit $rc
