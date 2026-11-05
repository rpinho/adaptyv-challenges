#!/usr/bin/env python3
"""Count R3 AF2M DRIVERS on a pod (runs on the pod; reads /proc only).

A shell wrapper and its python child are ONE driver: counting both would report
2 for a healthy pod and hide a real duplicate behind the same number. A bare
python launch (no wrapper) also counts as one.

Prints a single integer. Prints -1 and exits 2 if /proc is unavailable.
"""
import os
import sys

WRAPPERS = {'/workspace/pod_run.sh', '/workspace/r3_pod_run.sh',
            '/workspace/r3_pod_run_par.sh'}
SCRIPTS = {'pod_run_par.py', 'c3_r3_pod_run.py'}
INPUT = '/workspace/r3_screen/input.csv'
INPUT_DIR = '/workspace/r3_screen/'


def is_r3_input(path):
    """Any R3 screen cohort file, not just input.csv.

    A rebalanced remainder (e.g. /workspace/r3_screen/remainder.csv) is the SAME
    frozen cohort folded on a different pod, so it counts as an R3 driver -- an
    exact-match on input.csv silently reported 0 drivers for it.
    """
    return path.startswith(INPUT_DIR) and path.endswith('.csv')


def drivers(procs):
    """procs: {pid: {'args': [...], 'ppid': int}} -> number of distinct drivers."""
    shells, pythons, py_parents = set(), set(), set()
    for pid, rec in procs.items():
        args = rec['args']
        if len(args) < 3:
            continue
        base0 = os.path.basename(args[0])
        if base0 == 'bash':
            if args[1] in WRAPPERS and is_r3_input(args[2]):
                shells.add(pid)
            continue
        if base0.startswith('python'):
            if os.path.basename(args[1]) in SCRIPTS and is_r3_input(args[2]):
                pythons.add(pid)
                py_parents.add(rec.get('ppid'))
    return sum(1 for s in shells if s not in py_parents) + len(pythons)


def read_procs():
    out = {}
    for name in os.listdir('/proc'):
        if not name.isdigit():
            continue
        try:
            args = [x.decode('utf-8', 'replace')
                    for x in open(f'/proc/{name}/cmdline', 'rb').read().split(b'\0') if x]
            ppid = int(open(f'/proc/{name}/stat').read().split()[3])
        except (FileNotFoundError, PermissionError, ProcessLookupError, ValueError,
                IndexError):
            continue
        out[int(name)] = {'args': args, 'ppid': ppid}
    return out


def main():
    if not os.path.isdir('/proc'):
        print(-1)
        return 2
    print(drivers(read_procs()))
    return 0


if __name__ == '__main__':
    sys.exit(main())
