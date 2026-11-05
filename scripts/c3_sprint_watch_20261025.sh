#!/bin/zsh
# Sprint snapshot loop. Survives shell exit (script file + nohup + disown).
cd /Users/ricardo/dev/adaptyv-c4
L=results/orchestrator_20261025/sprint_watch.log
S=~/.codex/sessions/2026/10/24
A=$S/rollout-2026-10-24T22-00-04-01a170c9-52f7-79b1-a5cb-8cb0f59d5e8b.jsonl
B=$S/rollout-2026-10-24T22-10-25-01a170d2-cc3f-7aa3-9217-9831e6a39daf.jsonl
for i in {1..24}; do
  {
    echo "===== SPRINT SNAPSHOT $(date '+%F %T %Z') ====="
    codex-lanes adaptyv 2>&1 | sed -n '5p;10p'
    echo "v8 sha: $(shasum -a 256 results/c3_submission_v8_20261025.csv | cut -c1-8) (must be 631ed0bf)"
    echo "monitor 84622: $(ps -p 84622 -o etime= 2>/dev/null | tr -d ' ' || echo GONE)"
    echo "worker A: mtime $(stat -f '%Sm' -t '%H:%M:%S' $A), $(stat -f '%z' $A) bytes"
    echo "worker B: mtime $(stat -f '%Sm' -t '%H:%M:%S' $B), $(stat -f '%z' $B) bytes"
    echo "---"
  } >> $L
  sleep 1500
done
