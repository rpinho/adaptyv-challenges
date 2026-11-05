#!/usr/bin/env python3
"""Terminate only an R3 AF2M screen driver and its descendants.

The root is identified by one of the exact R3 commands
  bash /workspace/pod_run.sh /workspace/r3_screen/input.csv ...
  bash /workspace/r3_pod_run.sh /workspace/r3_screen/input.csv ...
  bash /workspace/r3_pod_run_par.sh /workspace/r3_screen/input.csv ... N
so sibling lanes are never signalled. The parallel form is matched by its shell
wrapper AND directly by its python driver, so a wrapper-less launch is still
quiesced. Prints one machine-readable line and exits 0
whether or not a root was found. Missing/ambiguous roots are reported, not guessed.
"""
import argparse
import os
import signal
import sys
import time

R3_ROOTS = {'/workspace/pod_run.sh', '/workspace/r3_pod_run.sh',
            '/workspace/r3_pod_run_par.sh'}
R3_PAR_ROOTS = {'/workspace/r3_pod_run_par.sh'}
R3_INPUT = '/workspace/r3_screen/input.csv'
R3_INPUT_DIR = '/workspace/r3_screen/'


def is_r3_input(path):
    """Any R3 screen cohort file (input.csv, remainder.csv, ...)."""
    return path.startswith(R3_INPUT_DIR) and path.endswith('.csv')
R3_PAR_SCRIPTS = {'/workspace/pod_run_par.py', '/workspace/r3_screen/pod_run_par.py'}


def read_procs():
    out = {}
    for name in os.listdir('/proc'):
        if not name.isdigit():
            continue
        try:
            raw = open(f'/proc/{name}/cmdline', 'rb').read().split(b'\0')
            args = [x.decode('utf-8', 'replace') for x in raw if x]
            stat = open(f'/proc/{name}/stat').read().split()
            rec = {'args': args, 'ppid': int(stat[3])}
            out[int(name)] = rec
        except (FileNotFoundError, PermissionError, ProcessLookupError, ValueError,
                IndexError):
            continue
    return out


def is_root(args):
    return (len(args) >= 3 and os.path.basename(args[0]) == 'bash'
            and args[1] in R3_ROOTS and is_r3_input(args[2]))


def is_par_root(args):
    """A parallel python driver started without the shell wrapper."""
    if len(args) < 4:
        return False
    if not os.path.basename(args[0]).startswith('python'):
        return False
    if args[1] not in R3_PAR_SCRIPTS:
        return False
    return is_r3_input(args[2])


def descendants(procs, roots):
    children = {}
    for pid in procs:
        try:
            ppid = int(open(f'/proc/{pid}/stat').read().split()[3])
        except (FileNotFoundError, PermissionError, ProcessLookupError, ValueError):
            continue
        children.setdefault(ppid, []).append(pid)
    found, todo = set(roots), list(roots)
    while todo:
        for child in children.get(todo.pop(), []):
            if child not in found:
                found.add(child)
                todo.append(child)
    return found


def process_group(pid):
    try:
        fields = open(f'/proc/{pid}/stat').read().split()
        return int(fields[4])
    except (FileNotFoundError, PermissionError, ProcessLookupError, ValueError):
        return None


def live_groups_alive(pgid):
    try:
        os.killpg(pgid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--dry-run', action='store_true')
    a = ap.parse_args()
    if not os.path.isdir('/proc'):
        print('QUIESCE_UNSUPPORTED_NO_PROC')
        return 2
    procs_all = read_procs()
    shell_roots = {pid for pid, rec in procs_all.items() if is_root(rec['args'])}
    # A python driver under a matched shell root is the same driver, not a second one.
    py_roots = {pid for pid, rec in procs_all.items()
                if is_par_root(rec['args'])
                and int(procs_all[pid].get('ppid', 0) or 0) not in shell_roots}
    roots = sorted(shell_roots | py_roots)
    if not roots:
        print('QUIESCE_NO_R3_ROOT')
        return 0
    if len(roots) > 1:
        print('QUIESCE_MULTIPLE_R3_ROOTS ' + ','.join(map(str, roots)))
    procs = procs_all
    all_pids = descendants(procs, roots)
    # The launcher is a session leader (pgid == pid). Signalling that group
    # also catches children spawned after the /proc snapshot; if it is not a
    # group leader, fall back to the reviewed descendant set only.
    groups = sorted({g for g in (process_group(p) for p in roots)
                     if g is not None and g in roots})
    if a.dry_run:
        print(f'QUIESCE_DRYRUN roots={roots} pids={sorted(all_pids)} groups={groups}')
        return 0
    frozen = []
    for pid in roots:
        if os.path.exists(f'/proc/{pid}'):
            try:
                os.kill(pid, signal.SIGSTOP)
                frozen.append(pid)
            except ProcessLookupError:
                pass
    if frozen:
        # Re-snapshot the tree now that the roots can no longer spawn.
        all_pids = descendants(read_procs(), roots)
    for sig in (signal.SIGTERM, signal.SIGKILL):
        live = [p for p in all_pids if os.path.exists(f'/proc/{p}')]
        groups_alive = [g for g in groups if os.path.exists(f'/proc/{g}')]
        if not live and not groups_alive:
            break
        for pgid in groups_alive:
            try:
                os.killpg(pgid, sig)
            except ProcessLookupError:
                pass
        for pid in reversed(sorted(live)):
            try:
                os.kill(pid, sig)
            except ProcessLookupError:
                pass
        if sig == signal.SIGTERM:
            time.sleep(5)
    # SIGKILL is not instant: the kernel still has to reap. Counting "remaining"
    # immediately after SIGKILL reports processes that are already dying, which
    # made this script return rc=1 on a pod it had in fact stopped. Wait, then
    # count both the reviewed descendant set AND any surviving colabfold_batch,
    # because an orphaned fold is exactly the failure mode that matters here.
    time.sleep(2)
    remaining = [p for p in all_pids if os.path.exists(f'/proc/{p}')]
    folds = []
    for name in os.listdir('/proc'):
        if not name.isdigit():
            continue
        try:
            raw = open(f'/proc/{name}/cmdline', 'rb').read().split(b'\0')
            args = [x.decode('utf-8', 'replace') for x in raw if x]
            st = open(f'/proc/{name}/stat').read().split()
        except (FileNotFoundError, PermissionError, ProcessLookupError, ValueError,
                IndexError):
            continue
        if len(st) > 2 and st[2] == 'Z':
            continue
        if len(args) >= 2 and os.path.basename(args[0]).startswith('python') \
                and any('colabfold_batch' in os.path.basename(a) for a in args):
            folds.append(int(name))
    live_groups = [g for g in groups if live_groups_alive(g)]
    print(f'QUIESCE_DONE roots={len(roots)} signalled={len(all_pids)} '
          f'groups={groups} remaining={len(remaining)} live_groups={live_groups} '
          f'surviving_folds={len(folds)}')
    return 1 if (remaining or folds or live_groups) else 0


if __name__ == '__main__':
    sys.exit(main())
