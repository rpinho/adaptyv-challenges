#!/bin/bash
# R3 generation runner — Kimi ruling 20261025-v8-unit-and-r3-queue-kimi.md §Q4.
# usage: c3_r3_run_pod.sh <pod> <tag> <config> <seed> [seed...]
# Every attempt writes one JSONL record. Failures are terminal (no retry, no replacement).
set -uo pipefail
POD="$1"; TAG="$2"; CFG="$3"; shift 3
ROOT=/workspace/r3
CFGHASH=$(sha256sum "$CFG" | awk '{print $1}')
ARM=${TAG%%_*}
BIN=${TAG#*_}
mkdir -p "$ROOT/logs" "$ROOT/out"
# Match the validated R2 runner's working directory so module/asset resolution is identical.
cd /workspace/rfd4_src || { echo "R3_NO_RFD4_SRC" >&2; exit 91; }
exec 9>"$ROOT/lock.$POD"
flock -n 9 || { echo "R3_ALREADY_RUNNING $POD" >&2; exit 90; }
touch /root/keepalive
# The pods run UTC. 2026-10-25 03:00 America/New_York == 07:00:00Z.
# Hard-coding the epoch (computed offline with zoneinfo) avoids a silent timezone
# mistake: a naive `date -d 03:00` on a UTC pod would cut off at 23:00 ET.
CUTOFF_ET=1792911600
for SEED in "$@"; do
  OUT="$ROOT/out/${POD}_${TAG}_${SEED}"
  LOG="$ROOT/logs/${POD}_${TAG}_${SEED}.log"
  REC="$ROOT/logs/records.jsonl"
  # Resume only from a real backbone: exit-0 + nonempty generated CIF. A stale directory
  # with no CIF is NOT a completed seed and must be rerun.
  EXISTING=$(find "$OUT" -name '*_generated.cif' -size +0c 2>/dev/null | head -1)
  if [ -n "$EXISTING" ]; then
    # A resume must still yield a durable provenance record for this seed.
    OUTSHA=$(sha256sum "$EXISTING" | awk '{print $1}')
    printf '%s\n' "$(python3 - "$POD" "$TAG" "$ARM" "$BIN" "$CFG" "$CFGHASH" "$SEED" "$EXISTING" "$OUTSHA" <<'PY'
import json,sys
pod,tag,arm,bin_,cfg,cfghash,seed,cif,outsha=sys.argv[1:]
print(json.dumps(dict(pod=pod,arm=arm,bin=bin_,tag=tag,config_path=cfg,config_sha256=cfghash,seed=int(seed),
 status="skipped_existing",output_path=cif,backbone_path=cif,
 output_sha256=outsha,backbone_valid=True),sort_keys=True))
PY
)" >> "$REC"
    echo "$(date -u +%FT%TZ) SKIP ${POD} ${TAG} ${SEED} existing=${OUTSHA}" >> "$ROOT/logs/manifest.txt"
    continue
  fi
  if [ "$(date +%s)" -ge "$CUTOFF_ET" ]; then
    echo "$(date -u +%FT%TZ) CUTOFF_NOT_STARTED ${POD} ${TAG} ${SEED}" >> "$ROOT/logs/manifest.txt"
    continue
  fi
  CMD=(/workspace/rfd4/venv/bin/rfd4-generate "inputs=$CFG" \
       recycle_strategy=medium/front_loaded num_replicates=1 batch_size=1 \
       seed="$SEED" save_chain_of_interest=true prevalidate_inputs=true '~metrics' \
       "out_dir=$OUT")
  START=$(date -u +%FT%TZ); T0=$(date +%s)
  timeout --signal=TERM --kill-after=60s 3600s "${CMD[@]}" >"$LOG" 2>&1
  RC=$?; END=$(date -u +%FT%TZ); ELAPSED=$(( $(date +%s) - T0 ))
  CIF=$(find "$OUT" -name '*_generated.cif' 2>/dev/null | head -1)
  OUTSHA=""; VALID=false
  if [ "$RC" -eq 0 ] && [ -n "$CIF" ] && [ -s "$CIF" ] && grep -q '^ATOM' "$CIF"; then
    OUTSHA=$(sha256sum "$CIF" | awk '{print $1}'); VALID=true
  fi
  printf '%s\n' "$(python3 - "$POD" "$TAG" "$ARM" "$BIN" "$CFG" "$CFGHASH" "$SEED" "$START" "$END" "$RC" "$OUT" "$CIF" "$OUTSHA" "$VALID" "$ELAPSED" "${CMD[*]}" <<'PY'
import json,sys
pod,tag,arm,bin_,cfg,cfghash,seed,start,end,rc,out,cif,outsha,valid,elapsed,cmd=sys.argv[1:]
print(json.dumps(dict(pod=pod,arm=arm,bin=bin_,tag=tag,config_path=cfg,config_sha256=cfghash,seed=int(seed),
 start=start,end=end,exit_status=int(rc),output_path=out,backbone_path=cif or None,
 output_sha256=outsha or None,backbone_valid=(valid=='true'),wall_s=int(elapsed),
 command=cmd),sort_keys=True))
PY
)" >> "$REC"
  echo "$(date -u +%FT%TZ) ${POD} ${TAG} seed=${SEED} rc=${RC} valid=${VALID}" >> "$ROOT/logs/manifest.txt"
  touch /root/keepalive
done
echo "$(date -u +%FT%TZ) RUNNER_DONE ${POD} ${TAG}" >> "$ROOT/logs/manifest.txt"
