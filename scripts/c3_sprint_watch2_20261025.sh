#!/bin/zsh
# Sprint watchdog, cycle-2 variant. Detached via nohup + disown; verified by ps AND log growth.
cd /Users/ricardo/dev/adaptyv-c4
L=results/orchestrator_20261025/sprint_watch2.log
S=$HOME/.codex/sessions/2026/10/24
A=$S/rollout-2026-10-24T22-00-04-01a170c9-52f7-79b1-a5cb-8cb0f59d5e8b.jsonl
B=$S/rollout-2026-10-24T22-10-25-01a170d2-cc3f-7aa3-9217-9831e6a39daf.jsonl
for i in {1..40}; do
  {
    echo "===== SNAPSHOT $(date '+%F %T %Z') ====="
    echo "v8: $(shasum -a 256 results/c3_submission_v8_20261025.csv | cut -c1-8) (must be 631ed0bf)"
    echo "v9B: $(shasum -a 256 results/c3_sprint_8h_20261025/c3_candidate_v9_B_20261025.csv | cut -c1-8) (643490da)"
    echo "v9B-plddt: $(shasum -a 256 results/c3_sprint_8h_20261025/c3_candidate_v9_B-plddt_20261025.csv | cut -c1-8) (704988ca)"
    echo "workerA mtime $(stat -f '%Sm' -t '%H:%M:%S' $A)"
    echo "workerB mtime $(stat -f '%Sm' -t '%H:%M:%S' $B)"
    echo "checkpoint 15:30 / GPU-freeze 18:30 / final 19:30 EDT"
    echo "---"
  } >> $L
  sleep 900
done
