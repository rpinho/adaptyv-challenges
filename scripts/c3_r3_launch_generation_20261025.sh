#!/bin/bash
# Stage the canonical R3 generation runner/configs and launch the frozen allocation.
# Optional args select a subset of pods, e.g. `p1 p5`; every pod is launched exactly once.
# READ-ONLY w.r.t. v6/v7/v8/E2/E3/R2 artifacts. Existing unproven R3 output is MOVED
# (never deleted) under /workspace/r3/legacy/ so the 120 canonical seeds get real records.
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1
CLI_PODS=("$@")
KEY=$HOME/.ssh/runpod_ed25519
RUNNER=$PWD/scripts/c3_r3_run_pod.sh
CFGDIR=$PWD/configs/rfd4/r3
host_of() { case $1 in p1) echo 63.141.33.138;; p2) echo 194.68.245.32;;
  p3) echo 69.30.85.102;; p4) echo 194.68.245.69;; p5) echo 194.68.245.147;;
  *) return 1;; esac; }
port_of() { case $1 in p1) echo 22113;; p2) echo 22065;; p3) echo 22129;;
  p4) echo 22022;; p5) echo 22117;; *) return 1;; esac; }

pod_ssh() { local p=$1; shift; ssh -n -i "$KEY" -o StrictHostKeyChecking=no \
  -o ConnectTimeout=10 -o BatchMode=yes -p "$(port_of "$p")" root@"$(host_of "$p")" "$@"; }
pod_rsync() { local p=$1 src=$2 dst=$3; rsync -az --timeout=120 \
  -e "ssh -i $KEY -p $(port_of "$p") -o ConnectTimeout=10 -o StrictHostKeyChecking=no -o BatchMode=yes" \
  "$src" "root@$(host_of "$p"):$dst"; }

cmd_for() {  # pod tag config lo hi
  local p=$1 tag=$2 cfg=$3 lo=$4 hi=$5
  local seeds; seeds=$(seq -s ' ' "$lo" "$hi")
  printf 'bash /workspace/r3/run_pod.sh %s %s %s %s\n' "$p" "$tag" "$cfg" "$seeds"
}

launch() {  # pod -> driver body
  local p=$1 body=$2
  pod_ssh "$p" "cat > /workspace/r3/driver_${p}.sh <<'EOS'
#!/bin/bash
$body
EOS
chmod +x /workspace/r3/driver_${p}.sh
setsid nohup /workspace/r3/driver_${p}.sh > /workspace/r3/logs/driver_${p}.out 2>&1 < /dev/null &
echo LAUNCHED_${p}_PID=\$!"
}

# Frozen allocation. Tag format is ARM_BIN; the runner also records tag separately.
SPECS=(
  "p1 H8 H8_52_64 c3_ecd111_r3_h8_52_64.yaml 910000 910023"
  "p2 H8 H8_65_80 c3_ecd111_r3_h8_65_80.yaml 910100 910123"
  "p3 H8 H8_81_100 c3_ecd111_r3_h8_81_100.yaml 910200 910223"
  "p4 H8 H8_52_64 c3_ecd111_r3_h8_52_64.yaml 910024 910031"
  "p4 H8 H8_65_80 c3_ecd111_r3_h8_65_80.yaml 910124 910131"
  "p4 H8 H8_81_100 c3_ecd111_r3_h8_81_100.yaml 910224 910231"
  "p5 H4 H4_52_64 c3_ecd111_r3_h4_52_64.yaml 910300 910307"
  "p5 H4 H4_65_80 c3_ecd111_r3_h4_65_80.yaml 910400 910407"
  "p5 H4 H4_81_100 c3_ecd111_r3_h4_81_100.yaml 910500 910507"
)

# Verify the full allocation exactly as frozen, independent of the selected subset.
total=0
for spec in "${SPECS[@]}"; do
  set -- $spec; p=$1; cfg=$4; lo=$5; hi=$6
  n=$((hi-lo+1)); total=$((total+n))
  [ -s "$CFGDIR/$cfg" ] || { echo "MISSING_LOCAL_CONFIG $CFGDIR/$cfg"; exit 4; }
done
[ "$total" -eq 120 ] || { echo "ALLOCATION_FAIL total=$total"; exit 4; }
count_for_pod() { local want=$1 n=0; for spec in "${SPECS[@]}"; do
  set -- $spec; [ "$1" = "$want" ] && n=$((n + $6 - $5 + 1)); done; echo "$n"; }
for p in p1 p2 p3 p4 p5; do n=$(count_for_pod "$p");
  [ "$n" -eq 24 ] || { echo "POD_ALLOC_FAIL $p=$n"; exit 4; }; done

PODS=("${CLI_PODS[@]}"); [ ${#PODS[@]} -gt 0 ] || PODS=(p1 p2 p3 p4 p5)
for p in "${PODS[@]}"; do
  host_of "$p" >/dev/null || { echo "UNKNOWN_POD $p"; exit 4; }
done

for p in "${PODS[@]}"; do
  echo "=== staging $p ($(host_of "$p"):$(port_of "$p")) ==="
  pod_ssh "$p" 'mkdir -p /workspace/r3/{out,logs,legacy/out,legacy/logs} /workspace/c3/configs/rfd4' || exit 5
  pod_rsync "$p" "$RUNNER" /workspace/r3/run_pod.sh || exit 5
  local_runner_sha=$(sha256sum "$RUNNER" | awk '{print $1}')
  remote_runner_sha=$(pod_ssh "$p" 'sha256sum /workspace/r3/run_pod.sh | awk "{print \$1}"') || exit 5
  [ "$local_runner_sha" = "$remote_runner_sha" ] || { echo "RUNNER_SHA_MISMATCH $p"; exit 5; }
  # Quarantine pre-canonical output/logs only once; after the marker exists, never move live work.
  if ! pod_ssh "$p" 'test -e /workspace/r3/CANONICAL_STARTED'; then
    pod_ssh "$p" 'bash -c '"'"'cd /workspace/r3 || exit 5; for d in out/*; do [ -e "$d" ] && mv "$d" legacy/out/"$(basename "$d")"; done; for f in logs/* records_*.jsonl; do [ -e "$f" ] && mv "$f" legacy/logs/"$(basename "$f")"; done; touch CANONICAL_STARTED'"'"'' || exit 5
  fi
  # Copy every config needed by this pod and verify bytes; p1 already has them.
  for spec in "${SPECS[@]}"; do
    set -- $spec; sp=$1; cfg=$4
    [ "$sp" = "$p" ] || continue
    pod_rsync "$p" "$CFGDIR/$cfg" /workspace/c3/configs/rfd4/ || exit 5
  done
  for spec in "${SPECS[@]}"; do
    set -- $spec; sp=$1; cfg=$4
    [ "$sp" = "$p" ] || continue
    lsha=$(sha256sum "$CFGDIR/$cfg" | awk '{print $1}')
    rsha=$(pod_ssh "$p" "sha256sum /workspace/c3/configs/rfd4/$cfg | awk '{print \$1}'") || exit 5
    [ "$lsha" = "$rsha" ] || { echo "CONFIG_SHA_MISMATCH $p $cfg"; exit 5; }
  done
  pod_ssh "$p" '/workspace/rfd4/venv/bin/python -c "import torch; print(\"RF_OK\",torch.__version__,torch.cuda.is_available())" 2>&1 | tail -1' || exit 5
done

for p in "${PODS[@]}"; do
  body=""
  for spec in "${SPECS[@]}"; do
    set -- $spec; sp=$1; tag=$3; cfg=$4; lo=$5; hi=$6
    [ "$sp" = "$p" ] || continue
    body+="$(cmd_for "$p" "$tag" "/workspace/c3/configs/rfd4/$cfg" "$lo" "$hi")"$'\n'
  done
  launch "$p" "$body"
done

sleep 5
for p in "${PODS[@]}"; do
  printf '%s ' "$p"
  pod_ssh "$p" 'pgrep -af "run_pod.sh|driver_" | head -3 | tr "\n" "|"; echo; find /workspace/r3/out -name "*_generated.cif" 2>/dev/null | wc -l; tail -2 /workspace/r3/logs/manifest.txt 2>/dev/null'
done
