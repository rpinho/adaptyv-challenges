#!/bin/bash
# Periodic C5 pod health check — updates the local monitor log
# Pod 1 (ebead5sbejqaf2) STOPPED 2026-10-29 — only checking pod 2

KEY="$HOME/.ssh/runpod_ed25519"
LOG="$HOME/dev/adaptyv-c4/results/c5_pod_monitor.log"
FLAGS="$HOME/dev/adaptyv-c4/results"
TS=$(date -u +%Y-%m-%dT%H:%M:%SZ)

# --- Pod 2: AF2 scoring ---
POD2_SSH="d2y9mmgrtszcrq-644113a0@ssh.runpod.io"
STATUS2=$(expect -c "
set timeout 30
spawn ssh -o StrictHostKeyChecking=no -i $KEY $POD2_SSH
expect {
    \"root@\" {}
    \"#\" {}
    timeout { puts \"SSH_TIMEOUT\"; exit 1 }
}
send \"CF=\\\$(ps aux | grep colabfold | grep -v grep | wc -l); AF2_SCORE=\\\$(test -f /workspace/c5/af2_scoring_done.flag && echo 1 || echo 0); echo CF=\\\$CF AF2_SCORE=\\\$AF2_SCORE; echo __MON__\r\"
expect {
    \"__MON__\" {}
    timeout { puts \"CMD_TIMEOUT\"; exit 1 }
}
send \"exit\r\"
expect eof
" 2>&1 | grep 'CF=')

CLEAN2=$(echo "$STATUS2" | sed 's/\x1b\[[0-9;]*[a-zA-Z]//g' | grep -oE 'CF=[0-9]+ AF2_SCORE=[0-9]+')

if [ -n "$CLEAN2" ]; then
    echo "$TS POD2 $CLEAN2" >> "$LOG"
    if echo "$CLEAN2" | grep -q 'AF2_SCORE=1'; then
        touch "$FLAGS/c5_af2_scoring_done.flag"
    fi
else
    echo "$TS POD2 SSH_FAILED" >> "$LOG"
fi
