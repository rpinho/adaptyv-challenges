#!/bin/bash
# R3 per-pod downstream stage: MPNN on every admitted backbone generated on this pod.
# ESMFold and AF2M are driven centrally after the refold/queue artifacts exist.
# Refuses any new backbone after the 03:00 ET admission cutoff (07:00Z).
# usage: c3_r3_stage_pod.sh <pod>
set -uo pipefail
POD="$1"
R3=/workspace/r3
CUTOFF_ET=1792911600
mkdir -p "$R3/logs"
log() { echo "$(date -u +%FT%TZ) $*" >> "$R3/logs/stage_${POD}.log"; }
if [ "$(date +%s)" -ge "$CUTOFF_ET" ]; then log "CUTOFF_NO_STAGE"; exit 0; fi
touch /root/keepalive
bash /workspace/r3/mpnn_pod.sh "$POD" >> "$R3/logs/stage_${POD}.log" 2>&1
RC=$?
log "MPNN_STAGE_DONE rc=$RC"
exit "$RC"
