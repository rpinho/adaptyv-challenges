#!/bin/bash
# Pull finished round-2 AF2M artifacts from the 5 pods, then re-run the independent verifier.
# Read-only on the pods (rsync pulls only); never launches or stops compute; never writes a CSV.
# Log: results/c3_round2_pull_verify.log   Results: results/c3_round2_111_20261025/screen24/<shard>/<name>/
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1
R2=results/c3_round2_111_20261025
KEY=$HOME/.ssh/runpod_ed25519
LOG=$R2/pull_verify.log
mkdir -p "$R2/screen24"
echo "=== $(date '+%F %T %Z') pull start" >>"$LOG"
for spec in "63.141.33.138:22113:a" "194.68.245.32:22065:b" "69.30.85.102:22129:c" \
            "194.68.245.69:22022:d" "194.68.245.147:22117:e"; do
  host=${spec%%:*}; rest=${spec#*:}; port=${rest%%:*}; shard=${rest##*:}
  mkdir -p "$R2/screen24/$shard"
  # NOTE: no `timeout` wrapper — it is a GNU coreutils binary absent from launchd's PATH.
  # rsync --timeout and ssh ConnectTimeout already bound each transfer.
  rsync -az --timeout=30 \
    -e "ssh -i $KEY -p $port -o ConnectTimeout=10 -o StrictHostKeyChecking=no -o BatchMode=yes" \
    "root@$host:/workspace/screen24/$shard/" "$R2/screen24/$shard/" >>"$LOG" 2>&1
  rc=$?
  # keep only complete unit dirs (scores.json + complex present everywhere)
  echo "  shard=$shard host=$host rsync_rc=$rc units=$(find "$R2/screen24/$shard" -name scores.json 2>/dev/null | wc -l | tr -d ' ')" >>"$LOG"
done

# The two filter-clean replacements were launched by the C3 lane into a separate `rep/`
# directory on pod e. Pull that directory explicitly; otherwise those results are never
# verified and E2 can never be complete.
mkdir -p "$R2/screen24/rep"
rsync -az --timeout=30 \
  -e "ssh -i $KEY -p 22117 -o ConnectTimeout=10 -o StrictHostKeyChecking=no -o BatchMode=yes" \
  "root@194.68.245.147:/workspace/screen24/rep/" "$R2/screen24/rep/" >>"$LOG" 2>&1
rc=$?
echo "  shard=rep host=194.68.245.147 rsync_rc=$rc units=$(find "$R2/screen24/rep" -name scores.json 2>/dev/null | wc -l | tr -d ' ')" >>"$LOG"

python3 scripts/c3_round2_verify_20261025.py --dir "$R2/screen24" >>"$LOG" 2>&1
echo "=== $(date '+%F %T %Z') pull done" >>"$LOG"
