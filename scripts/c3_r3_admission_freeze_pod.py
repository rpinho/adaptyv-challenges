#!/usr/bin/env python3
"""Stop the R3 driver from admitting a new design at 03:00 ET.

Policy (Kimi/Astra): at 03:00 no new compute is admitted; an already-running
design may finish. The R3 launcher is one of:
  bash /workspace/pod_run.sh /workspace/r3_screen/input.csv ALL /workspace/r3_screen/out
  bash /workspace/r3_pod_run.sh /workspace/r3_screen/input.csv ALL /workspace/r3_screen/out
  bash /workspace/r3_pod_run_par.sh /workspace/r3_screen/input.csv ALL /workspace/r3_screen/out N
and its child python drives one colabfold_batch at a time (serial) or up to N at
a time (parallel). The R3-only wrapper keeps its shell as the parent so that
root remains visible to this script.

Parallel attempt dirs are named /tmp/<batch>-<design>-slot<k>, so the design is
NOT the directory name. It is recovered from the attempt id or, failing that,
from the FASTA's own header, which is the design name.

If no fold is active at the cutoff, the driver is terminated immediately. If a
fold is active, this script waits for that design's scores.json/error.json, then
stops the python driver before its loop can launch the next design. The R3 root
comes from an exact command match, so no sibling lane can be touched.

Usage (on a pod): python3 c3_r3_admission_freeze_pod.py --at EPOCH [--dry-run]
"""
import argparse
import fcntl
import json
import os
import signal
import sys
import time
from pathlib import Path

R3_ROOTS = {'/workspace/pod_run.sh', '/workspace/r3_pod_run.sh',
            '/workspace/r3_pod_run_par.sh'}
R3_PAR_ROOTS = {'/workspace/r3_pod_run_par.sh'}
R3_INPUT = '/workspace/r3_screen/input.csv'
R3_PAR_SCRIPTS = {'/workspace/pod_run_par.py', '/workspace/r3_screen/pod_run_par.py'}
OUT_ROOT = Path('/workspace/r3_screen/out')
LOCK = Path('/tmp/r3_admission_freeze.lock')
_lock_handle = None


def procs():
    out = {}
    for name in os.listdir('/proc'):
        if not name.isdigit():
            continue
        try:
            raw = open(f'/proc/{name}/cmdline', 'rb').read().split(b'\0')
            args = [x.decode('utf-8', 'replace') for x in raw if x]
            stat = open(f'/proc/{name}/stat').read().split()
            out[int(name)] = {'args': args, 'ppid': int(stat[3]), 'pgid': int(stat[4]),
                              'sid': int(stat[5])}
        except (FileNotFoundError, PermissionError, ProcessLookupError, ValueError):
            continue
    return out


def is_root(args):
    return (len(args) >= 3 and os.path.basename(args[0]) == 'bash'
            and args[1] in R3_ROOTS and args[2] == R3_INPUT)


def is_par_root(args):
    """Parallel python driver launched without the shell wrapper."""
    return (len(args) >= 4 and os.path.basename(args[0]).startswith('python')
            and args[1] in R3_PAR_SCRIPTS and args[2] == R3_INPUT)


def design_from_fasta(fa):
    """The FASTA header IS the design name (both serial and parallel runners)."""
    try:
        with open(fa) as fh:
            first = fh.readline().strip()
        return first[1:].strip() or None
    except (OSError, UnicodeDecodeError):
        return None


def design_from_attempt(dirname):
    """batch-<design>-slotK -> <design>; returns None if the shape is unknown."""
    if '-slot' not in dirname:
        return None
    head = dirname.rsplit('-slot', 1)[0]
    if '-' not in head:
        return None
    return head.split('-', 1)[1] or None


def design_of(workdir, fasta=None):
    """Resolve the real design name for a fold's work directory.

    The FASTA header is authoritative because the runner writes it directly
    from the input row. Only if that is unreadable do we parse the attempt id,
    and only then fall back to the directory name (which is never correct for
    a parallel attempt dir, so it is reported as-is rather than guessed).
    """
    if fasta:
        name = design_from_fasta(fasta)
        if name:
            return name
    name = design_from_attempt(workdir)
    if name:
        return name
    return workdir


def children_of(p, table):
    return [pid for pid, rec in table.items() if rec['ppid'] == p]


def tree(roots, table):
    seen, todo = set(roots), list(roots)
    while todo:
        for c in children_of(todo.pop(), table):
            if c not in seen:
                seen.add(c); todo.append(c)
    return seen


def is_python_driver(pid, table, root):
    args = table.get(pid, {}).get('args', [])
    if table.get(pid, {}).get('ppid') != root or len(args) < 3:
        return False
    if not os.path.basename(args[0]).startswith('python'):
        return False
    rest = args[1:]
    if rest and rest[0].endswith('/c3_r3_pod_run.py'):
        rest = rest[1:]
    if rest and rest[0].endswith('/pod_run_par.py'):
        rest = rest[1:]
    if rest and rest[0] == '-':
        rest = rest[1:]
    if rest == [R3_INPUT, 'ALL', '/workspace/r3_screen/out']:
        return True
    # parallel form: <csv> <outdir> <cap> [--limit N]
    return (len(rest) >= 3 and rest[0] == R3_INPUT
            and rest[1] == '/workspace/r3_screen/out'
            and rest[2].isdigit())


def folds_for(py, table):
    found = []
    for pid in tree([py], table):
        args = table.get(pid, {}).get('args', [])
        if args and any(os.path.basename(a) == 'colabfold_batch' for a in args[:3]):
            name = None
            fa = None
            for a in args[1:]:
                if a.startswith('/tmp/') and a.endswith('.fasta'):
                    fa = a
                    name = design_of(Path(a).parent.name, a)
                    break
            found.append((pid, name))
    return found


def stop(pid, sig):
    try:
        os.kill(pid, sig)
    except ProcessLookupError:
        pass


def wait_gone(pid, limit=5.0):
    end = time.time() + limit
    while time.time() < end:
        if not Path(f'/proc/{pid}').exists():
            return True
        time.sleep(0.05)
    return not Path(f'/proc/{pid}').exists()


def marker(name):
    d = OUT_ROOT / name
    for f in ('scores.json', 'error.json'):
        p = d / f
        if p.exists() and p.stat().st_size > 0:
            return p
    return None


def freeze(root, py, table, name=None, dry=False):
    folds = folds_for(py, table)
    if dry:
        print(f'FREEZE_DRYRUN root={root} python={py} folds={folds} design={name}')
        return 0
    if name and marker(name):
        # The active design already persisted; no new admission may start.
        stop(py, signal.SIGSTOP)
        time.sleep(0.05)
        stop(py, signal.SIGKILL)
        wait_gone(py)
        stop(root, signal.SIGTERM)
        print(f'FREEZE_DONE reason=marker_present design={name}')
        return 0
    if folds:
        # Under the parallel runner there may be up to N folds in flight. Let
        # every one of them persist, then stop the driver before it can admit
        # another design. Nothing that already started is discarded.
        deadline = time.time() + 900
        finished = {}
        while time.time() < deadline:
            for fpid, fname in folds:
                if fname not in finished and (
                        not Path(f'/proc/{fpid}').exists() or marker(fname)):
                    finished[fname] = bool(marker(fname))
            if len(finished) == len(folds):
                for _ in range(100):  # up to ~2 s for the parent to flush
                    if all(marker(n) for _, n in folds):
                        break
                    time.sleep(0.02)
                stop(py, signal.SIGSTOP)
                time.sleep(0.02)
                stop(py, signal.SIGKILL)
                wait_gone(py)
                stop(root, signal.SIGTERM)
                print(f'FREEZE_DONE reason=inflight_finished folds={len(folds)} '
                      f'designs={sorted(finished)} '
                      f'markers={all(finished.values())}')
                for pid2, name2 in folds_for(py, procs()):
                    stop(pid2, signal.SIGKILL)
                return 0
            time.sleep(0.02)
        print('FREEZE_TIMEOUT hard-stopping R3 group')
        for pid in tree([root], procs()):
            stop(pid, signal.SIGKILL)
        return 1
    # Nothing is in flight: no admission is allowed now.
    stop(py, signal.SIGKILL)
    wait_gone(py)
    stop(root, signal.SIGTERM)
    print('FREEZE_DONE reason=idle')
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--at', type=int, required=True)
    ap.add_argument('--dry-run', action='store_true')
    a = ap.parse_args()
    if not Path('/proc').is_dir():
        print('FREEZE_UNSUPPORTED_NO_PROC')
        return 2
    global _lock_handle
    if not a.dry_run:
        LOCK.parent.mkdir(parents=True, exist_ok=True)
        _lock_handle = open(LOCK, 'w')
        try:
            fcntl.flock(_lock_handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print(f'FREEZE_ALREADY_RUNNING lock={LOCK}')
            return 0
        _lock_handle.write(str(os.getpid()))
        _lock_handle.flush()
    now = int(time.time())
    if not a.dry_run and now < a.at:
        print(f'FREEZE_WAIT until={a.at} now={now}')
        while int(time.time()) < a.at:
            time.sleep(max(0.05, min(1.0, a.at - time.time())))
    table = procs()
    roots = sorted(pid for pid, rec in table.items()
                   if is_root(rec['args']) or is_par_root(rec['args']))

    def driver_of(root):
        """The python driver under a shell root, or the root itself when the
        parallel driver was launched bare (no shell wrapper)."""
        pys = [p for p in children_of(root, table) if is_python_driver(p, table, root)]
        if pys:
            return pys
        if is_par_root(table.get(root, {}).get('args', [])):
            return [root]
        return []

    if a.dry_run:
        print(f'FREEZE_DRYRUN roots={roots}')
        if not roots:
            return 0
        root = roots[0]
        pys = driver_of(root)
        print(f'FREEZE_DRYRUN python_drivers={pys} bare={is_par_root(table[root]["args"])}')
        if pys:
            folds = folds_for(pys[0], table)
            print(f'FREEZE_DRYRUN folds={folds}')
        return 0
    if not roots:
        print('FREEZE_NO_R3_ROOT')
        return 0
    if len(roots) > 1:
        print(f'FREEZE_MULTIPLE_ROOTS {roots}')
    root = roots[0]
    pys = driver_of(root)
    if not pys:
        print('FREEZE_NO_PYTHON_DRIVER')
        stop(root, signal.SIGTERM)
        return 0
    folds = folds_for(pys[0], table)
    name = folds[0][1] if folds else None
    return freeze(root, pys[0], table, name)


if __name__ == '__main__':
    sys.exit(main())
