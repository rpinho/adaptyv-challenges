#!/bin/bash
# Sampling-depth arm c3_sampling_depth_v1_20261025, stage 1: ProteinMPNN on the pod's own
# 24 admitted backbones, two extra draws (sd1, sd2), seed 20261029.
# Settings identical to R3/E3/round 2 (v_48_020, chain A, temp 0.1, batch 1) except the seed
# and 1 sequence per draw, per Astra's 03:21 ruling. Does NOT touch /workspace/mpnn_run.sh,
# /workspace/r3, or any frozen artifact.
# usage: c3_sd_mpnn_pod_20261025.sh <pod>
set -uo pipefail
POD="$1"
SD=/workspace/sd1
REC="$SD/logs/mpnn_records_${POD}.jsonl"
mkdir -p "$SD/pdb" "$SD/mpnn" "$SD/logs"
exec 9>"$SD/lock.$POD.mpnn"
flock -n 9 || { echo "SD_MPNN_ALREADY_RUNNING $POD" >&2; exit 90; }
touch /root/keepalive
[ -s /workspace/third_party/ProteinMPNN/vanilla_model_weights/v_48_020.pt ] || {
  echo "SD_MPNN_WEIGHTS_MISSING" >&2; exit 92; }
SEED=20261029
for DRAW in 1 2; do
  for PDB in "$SD"/pdb/${POD}_*.pdb; do
    [ -e "$PDB" ] || continue
    BB=$(basename "$PDB" .pdb)
    OUT="$SD/mpnn/$BB/sd$DRAW"
    FA="$OUT/seqs/$BB.fa"
    if [ -s "$FA" ]; then
      echo "$(date -u +%FT%TZ) SD_MPNN_SKIP $BB sd$DRAW" >> "$SD/logs/mpnn_${POD}.log"
      continue
    fi
    touch /root/keepalive
    T0=$(date -u +%FT%TZ); S0=$(date +%s)
    timeout 900 bash /workspace/sd1/mpnn_run_sd.sh "$PDB" "$OUT" "$((SEED + DRAW - 1))" \
      > "$SD/logs/mpnn_${BB}_sd${DRAW}.log" 2>&1
    RC=$?; T1=$(date -u +%FT%TZ); EL=$(( $(date +%s) - S0 ))
    NFA=$(find "$OUT" -name '*.fa' -size +0c 2>/dev/null | wc -l | tr -d ' ')
    FA_SHA=""; [ -s "$FA" ] && FA_SHA=$(sha256sum "$FA" | awk '{print $1}')
    python3 - "$POD" "$BB" "$DRAW" "$SEED" "$PDB" "$OUT" "$RC" "$NFA" "$FA_SHA" "$T0" "$T1" "$EL" <<'PY' >> "$REC"
import json,sys
pod,bb,draw,seed,pdb,out,rc,nfa,fasha,t0,t1,el=sys.argv[1:]
print(json.dumps(dict(pod=pod,backbone=bb,draw=int(draw),arm='c3_sampling_depth_v1_20261025',
 seed_base=int(seed),seed_used=int(seed)+int(draw)-1,backbone_pdb=pdb,output_dir=out,
 exit_status=int(rc),n_fasta=int(nfa),
 fasta_path=(out+'/seqs/'+bb+'.fa') if int(nfa) else None,fasta_sha256=fasha or None,
 start=t0,end=t1,wall_s=int(el),rc_dir='vs_round2_r3_e3_v_48_020_temp0.1'),sort_keys=True))
PY
    echo "$(date -u +%FT%TZ) SD_MPNN ${POD} ${BB} sd${DRAW} rc=${RC} nfa=${NFA}" >> "$SD/logs/mpnn_${POD}.log"
    touch /root/keepalive
  done
done
echo "$(date -u +%FT%TZ) SD_MPNN_DONE ${POD}" >> "$SD/logs/mpnn_${POD}.log"
