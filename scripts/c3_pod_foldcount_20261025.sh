#!/bin/bash
while read -r name ip port; do
  n=$(ssh -n -o ConnectTimeout=8 -o BatchMode=yes -i ~/.ssh/runpod_ed25519 -p "$port" root@"$ip" "python3 -c \"
import os,re
pids=[p for p in os.listdir('/proc') if p.isdigit()]
n=0
for p in pids:
    try:
        c=open(f'/proc/{p}/cmdline','rb').read().decode('utf8','replace')
        st=open(f'/proc/{p}/stat').read().split()[2]
    except Exception: continue
    if 'af2m/venv/bin/colabfold_batch' in c and st!='Z' and 'python3 -c' not in c: n+=1
print(n)\"" 2>/dev/null)
  echo "$name folds=$n"
done <<'L'
p1 63.141.33.138 22113
p2 194.68.245.32 22065
p3 69.30.85.102 22129
p4 194.68.245.69 22022
p5 194.68.245.147 22117
L
