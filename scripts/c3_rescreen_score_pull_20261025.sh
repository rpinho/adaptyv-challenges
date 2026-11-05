#!/bin/bash
# One command: audit a Modal pull, then score it. $0 CPU, read-only on the pull.
# usage: c3_rescreen_score_pull_20261025.sh [PULL_DIR]
# Exits non-zero if the pull contains stale (pre-fix) artifacts; still writes the score table.
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1
PULL=${1:-results/c3_survivor_rescreen_20261025/modal_pull}
S=scripts/c3_survivor_rescreen_clash_score_20261025.py
OUT=results/c3_survivor_rescreen_20261025/clash

[ -d "$PULL" ] || { echo "MISSING_PULL $PULL"; exit 2; }

echo "=== 1. audit (stale pre-fix artifacts) ==="
python3 "$S" --mode audit-pull --root "$PULL"
AUDIT=$?

echo
echo "=== 2. score (min inter-chain heavy-atom distance per ranked model) ==="
python3 "$S" --mode dir --root "$PULL" --json-out "$OUT/clash_scores.json"
SCORE=$?

echo
if [ "$AUDIT" -ne 0 ]; then
  echo "WARNING: pull contains stale rank-001-only artifact(s); see $OUT/pull_audit.json"
  echo "         those designs are INCOMPLETE, not certified."
fi
[ "$SCORE" -eq 0 ] || { echo "SCORE_FAILED rc=$SCORE"; exit 3; }
exit 0
