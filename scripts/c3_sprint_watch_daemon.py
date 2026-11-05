#!/usr/bin/env python3
"""Detached sprint watchdog. Uses fork + os.setsid so the process leaves the tool's
process group/session entirely -- nohup+disown was NOT sufficient (two watches died
silently at ~4 min). Verified by: pid file, liveness probe, and log growth."""
import os, sys, time, subprocess, datetime, pathlib

ROOT = pathlib.Path('/Users/ricardo/dev/adaptyv-c4')
LOG = ROOT / 'results/orchestrator_20261025/sprint_watch2.log'
PIDF = ROOT / 'results/orchestrator_20261025/sprint_watch2.pid'
SESS = pathlib.Path.home() / '.codex/sessions/2026/10/24'
A = SESS / 'rollout-2026-10-24T22-00-04-01a170c9-52f7-79b1-a5cb-8cb0f59d5e8b.jsonl'
B = SESS / 'rollout-2026-10-24T22-10-25-01a170d2-cc3f-7aa3-9217-9831e6a39daf.jsonl'
FILES = {
    'v8': (ROOT / 'results/c3_submission_v8_20261025.csv', '631ed0bf'),
    'v9B': (ROOT / 'results/c3_sprint_8h_20261025/c3_candidate_v9_B_20261025.csv', '643490da'),
    'v9B-plddt': (ROOT / 'results/c3_sprint_8h_20261025/c3_candidate_v9_B-plddt_20261025.csv', '704988ca'),
    'v7': (ROOT / 'results/c3_submission_v7_20261025.csv', '1d99f843'),
    'v6': (ROOT / 'results/c3_submission_v6_20261023.csv', '8e9b2d74'),
}

def sha8(p):
    import hashlib
    try: return hashlib.sha256(p.read_bytes()).hexdigest()[:8]
    except Exception: return 'MISSING'

def snap():
    lines = [f"===== SNAPSHOT {datetime.datetime.now():%Y-%m-%d %H:%M:%S} ====="]
    for k, (p, want) in FILES.items():
        got = sha8(p)
        lines.append(f"{k}: {got} {'OK' if got==want else '*** MISMATCH (want '+want+') ***'}")
    for tag, f in (('workerA', A), ('workerB', B)):
        try:
            st = f.stat(); lines.append(f"{tag} mtime {datetime.datetime.fromtimestamp(st.st_mtime):%H:%M:%S}")
        except Exception: lines.append(f"{tag} MISSING")
    lines.append("checkpoints: 15:30 mid / 18:30 GPU-freeze / 19:30 final EDT")
    lines.append('---')
    with open(LOG, 'a') as fh: fh.write('\n'.join(lines) + '\n')

def main():
    # already running?
    if PIDF.exists():
        try:
            pid = int(PIDF.read_text().strip())
            os.kill(pid, 0)
            print(f'already running pid {pid}'); return
        except Exception:
            pass
    snap(); time.sleep(0.1)
    pid = os.fork()
    if pid > 0:
        PIDF.write_text(str(pid))
        print(f'daemon pid {pid}')
        return
    os.setsid()
    pid2 = os.fork()
    if pid2 > 0: os._exit(0)
    # grandchild: fully detached
    devnull = os.open(os.devnull, os.O_RDWR)
    for fd in (0, 1, 2): os.dup2(devnull, fd)
    PIDF.write_text(str(os.getpid()))
    while True:
        time.sleep(900)
        snap()

if __name__ == '__main__':
    main()
