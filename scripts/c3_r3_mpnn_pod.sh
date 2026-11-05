#!/bin/bash
# R3 stage 2: ProteinMPNN 2 designed sequences per admitted backbone, on the same pod
# that generated it. Settings are identical to rounds 2 and E3 (v_48_020, chain A,
# temperature 0.1, seed 20261028, batch 1). Read-only w.r.t. frozen artifacts.
# usage: c3_r3_mpnn_pod.sh <pod>
set -uo pipefail
POD="$1"
R3=/workspace/r3
REC="$R3/logs/mpnn_records.jsonl"
mkdir -p "$R3/pdb" "$R3/mpnn" "$R3/logs"
exec 9>"$R3/lock.$POD.mpnn"
flock -n 9 || { echo "R3_MPNN_ALREADY_RUNNING $POD" >&2; exit 90; }
touch /root/keepalive
[ -x /workspace/mpnn_run.sh ] || { echo "R3_MPNN_RUNNER_MISSING" >&2; exit 91; }
[ -s /workspace/third_party/ProteinMPNN/vanilla_model_weights/v_48_020.pt ] || {
  echo "R3_MPNN_WEIGHTS_MISSING" >&2; exit 92; }
for PDB in "$R3"/pdb/${POD}_*.pdb; do
  [ -e "$PDB" ] || continue
  BB=$(basename "$PDB" .pdb)
  OUT="$R3/mpnn/$BB"
  FA="$OUT/seqs/$BB.fa"
  if [ -s "$FA" ]; then
    echo "$(date -u +%FT%TZ) MPNN_SKIP $BB" >> "$R3/logs/mpnn_${POD}.log"
    continue
  fi
  touch /root/keepalive
  T0=$(date -u +%FT%TZ); S0=$(date +%s)
  timeout 900 bash /workspace/mpnn_run.sh "$PDB" "$OUT" > "$R3/logs/mpnn_${BB}.log" 2>&1
  RC=$?; T1=$(date -u +%FT%TZ); EL=$(( $(date +%s) - S0 ))
  NFA=$(find "$OUT" -name '*.fa' -size +0c 2>/dev/null | wc -l | tr -d ' ')
  FA_SHA=""; [ -s "$FA" ] && FA_SHA=$(sha256sum "$FA" | awk '{print $1}')
  python3 - "$POD" "$BB" "$PDB" "$OUT" "$RC" "$NFA" "$FA_SHA" "$T0" "$T1" "$EL" <<'PY' >> "$REC"
import json,sys
pod,bb,pdb,out,rc,nfa,fasha,t0,t1,el=sys.argv[1:]
print(json.dumps(dict(pod=pod,backbone=bb,backbone_pdb=pdb,output_dir=out,
 exit_status=int(rc),n_fasta=int(nfa),fasta_path=(out+'/seqs/'+bb+'.fa') if int(nfa) else None,
 fasta_sha256=fasha or None,start=t0,end=t1,wall_s=int(el),
 rc_dir='vs_round2_and_e3_v_48_020_temp0.1_seed20261028'),sort_keys=True))
PY
  echo "$(date -u +%FT%TZ) MPNN ${POD} ${BB} rc=${RC} nfa=${NFA}" >> "$R3/logs/mpnn_${POD}.log"
  touch /root/keepalive
done
echo "$(date -u +%FT%TZ) MPNN_DONE ${POD}" >> "$R3/logs/mpnn_${POD}.log"
