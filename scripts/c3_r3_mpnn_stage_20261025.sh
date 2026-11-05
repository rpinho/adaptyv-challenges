#!/bin/bash
# R3 stage 2: distribute admitted backbone PDBs to their generating pod and run MPNN.
# Uses the unchanged ProteinMPNN settings, runner and weights validated by a known-answer
# control on all five pods (FASTA sha256 b3203ea9... on every pod).
# usage: c3_r3_mpnn_stage_20261025.sh [p1 ... p5]
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1
KEY=$HOME/.ssh/runpod_ed25519
R3=results/c3_r3_20261025
MPNN_SCRIPT=$PWD/scripts/c3_r3_mpnn_pod.sh
spec_of() { case $1 in p1) echo 63.141.33.138:22113;; p2) echo 194.68.245.32:22065;;
  p3) echo 69.30.85.102:22129;; p4) echo 194.68.245.69:22022;;
  p5) echo 194.68.245.147:22117;; *) return 1;; esac; }
pods=("$@"); [ ${#pods[@]} -gt 0 ] || pods=(p1 p2 p3 p4 p5)
[ -s "$MPNN_SCRIPT" ] || { echo MISSING_MPNN_SCRIPT; exit 4; }
mpnn_sha=$(sha256sum "$MPNN_SCRIPT" | awk '{print $1}')
for p in "${pods[@]}"; do
  spec=$(spec_of "$p") || { echo "UNKNOWN_POD $p"; exit 4; }
  host=${spec%%:*}; port=${spec#*:}
  ssh -n -i "$KEY" -o StrictHostKeyChecking=no -o ConnectTimeout=15 -p "$port" root@$host \
    'mkdir -p /workspace/r3/pdb /workspace/r3/mpnn /workspace/r3/logs' || exit 5
  rsync -az -e "ssh -i $KEY -p $port -o StrictHostKeyChecking=no -o ConnectTimeout=15 -o BatchMode=yes" \
    "$MPNN_SCRIPT" root@$host:/workspace/r3/mpnn_pod.sh || exit 5
  rsha=$(ssh -n -i "$KEY" -o StrictHostKeyChecking=no -o ConnectTimeout=15 -p "$port" root@$host \
    'sha256sum /workspace/r3/mpnn_pod.sh | awk "{print \$1}"') || exit 5
  [ "$rsha" = "$mpnn_sha" ] || { echo "MPNN_SCRIPT_SHA_MISMATCH $p"; exit 5; }
  shopt -s nullglob
  files=("$R3"/backbone_pdb/${p}_*.pdb)
  shopt -u nullglob
  if [ ${#files[@]} -eq 0 ]; then echo "$p NO_ADMITTED_PDBS"; continue; fi
  rsync -az -e "ssh -i $KEY -p $port -o StrictHostKeyChecking=no -o ConnectTimeout=15 -o BatchMode=yes" \
    "${files[@]}" root@$host:/workspace/r3/pdb/ || exit 5
  echo "$p staged=${#files[@]}"
done
for p in "${pods[@]}"; do
  spec=$(spec_of "$p"); host=${spec%%:*}; port=${spec#*:}
  # Match only the exact worker argv. The enclosing `ssh ... bash -c` wrapper also
  # contains this path text, so a substring/pgrep guard self-matches and falsely
  # reports ALREADY_RUNNING (observed twice on 2026-10-25).
  ssh -n -i "$KEY" -o StrictHostKeyChecking=no -o ConnectTimeout=15 -p "$port" root@$host \
    "if ps -eo pid=,args= | awk -v p='$p' '\$2==\"bash\" && \$3==\"/workspace/r3/mpnn_pod.sh\" && \$4==p {found=1} END{exit !found}'; then echo MPNN_ALREADY_RUNNING_$p; else setsid nohup bash /workspace/r3/mpnn_pod.sh $p > /workspace/r3/logs/mpnn_${p}.out 2>&1 < /dev/null & echo LAUNCHED_MPNN_${p}_PID=\$!; fi"
done
