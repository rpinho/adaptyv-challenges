#!/bin/zsh
# C3 overnight integrity check. Every 15 min: confirm D is still ba5e3789 and the four frozen
# artifacts are unchanged, and record the guard heartbeat. Read-only; starts/stops nothing.
set -u
cd /Users/ricardo/dev/adaptyv-c4
LOG=results/orchestrator_20261025/post_2025_checks.log
# A log line nobody reads is not an alarm. On any failure we drop a file named ALARM at the
# repo root, which shows up in every `ls` and which the morning card tells Ricardo to check.
# It is deleted only when a full clean run completes.
ALARM=ALARM_INTEGRITY_FAILURE.txt
FAILS=0   # incremented on every failed check; cleared below only if it stays 0
mkdir -p results/orchestrator_20261025
ts(){ date '+%Y-%m-%d %H:%M:%S'; }

check(){
  local f="$1" want="$2"
  if [ ! -f "$f" ]; then
    echo "$(ts) MISSING $f" >> "$LOG"
    echo "$(ts) MISSING $f" >> "$ALARM"
    FAILURES_FILE=$(( ${FAILURES_FILE:-0} + 1 ))
    return
  fi
  local got=$(shasum -a 256 "$f" | cut -d' ' -f1)
  if [ "${got:0:8}" = "$want" ]; then
    echo "$(ts) OK      ${want} $f" >> "$LOG"
  else
    echo "$(ts) CHANGED expected ${want} got ${got:0:8} $f" >> "$LOG"
    echo "$(ts) CHANGED: expected ${want} got ${got:0:8} for $f" >> "$ALARM"
    FAILS=$((FAILS+1))
  fi
}

echo "$(ts) --- check ---" >> "$LOG"
check results/c3_sprint_8h_20261025/c3_candidate_D_swap18_20261025.csv ba5e3789
check results/c3_submission_v8_20261025.csv                           631ed0bf
check results/c3_submission_v7_20261025.csv                           1d99f843
check results/c3_submission_v6_20261023.csv                           8e9b2d74
check results/submission_v9.csv                                       31d98a41
echo "$(ts) guard: $(tail -1 results/orchestrator_20261025/gpu_freeze_guard.log)" >> "$LOG"
# Backups exist so a corrupted candidate is recoverable. A backup that has itself drifted is worse
# than no backup, because it looks safe. Check both copies every run.
check "$HOME/adaptyv_c3_backup_D_swap18_ba5e3789.csv" ba5e3789
check results/c3_sprint_8h_20261025/backup/c3_candidate_D_swap18_BACKUP.csv ba5e3789
# Row order is a scored input (FAQ5). Check it separately so a spreadsheet re-save is caught even if
# the content looks fine. Note: order lives inside the hash, so a reorder also trips the hash check --
# this makes the FAILURE REASON explicit instead of a bare hash mismatch at 06:30.
if /Applications/Xcode-26.6.0.app/Contents/Developer/usr/bin/python3 scripts/c3_check_row_order_20261025.py >> "$LOG" 2>&1; then
  :
else
  echo "$(ts) ALERT row order FAILED - see above" >> "$LOG"
  echo "$(ts) ROW ORDER FAILED - see above" >> "$ALARM"
fi

# Clear a stale alarm ONLY when this run recorded zero failures.
# History, because both earlier versions were wrong and both were caught by testing the transition:
#   v1 `[ -s "$ALARM" ] || rm -f "$ALARM"` -> `-s` is true when content exists, so never cleared.
#   v2 `rm -f "$ALARM"` unconditionally       -> deleted the alarm it had just written.
# Now the condition is explicit state, not a guess from the filesystem.
if [ "${FAILS:-0}" -eq 0 ] && [ "${FAILURES_FILE:-0}" -eq 0 ]; then
  rm -f "$ALARM" 2>/dev/null || true
else
  echo "$(ts) ALARM ACTIVE - integrity check failed this run" >> "$LOG"
fi
