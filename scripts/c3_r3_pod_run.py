#!/usr/bin/env python3
"""R3-specific AF2M runner with a hard no-new-admission boundary.

Identical colabfold settings and output shape to /workspace/pod_run.sh, but for
the frozen R3 input only. Before each design it checks the cutoff epoch; once
reached it exits without creating the next output directory. This avoids
modifying the shared pod_run.sh used by the sibling LigandMPNN lane.
"""
import csv
import glob
import json
import os
import pathlib
import shutil
import subprocess
import sys
import time

CUTOFF_ET = 1792911600  # 2026-10-25 03:00 America/New_York


def admit(now, cutoff=CUTOFF_ET):
    return now < cutoff


def main():
    csv_path, names, out_root = sys.argv[1], sys.argv[2], pathlib.Path(sys.argv[3])
    rows = list(csv.DictReader(open(csv_path)))
    want = None if names == 'ALL' else set(names.split(','))
    rows = [r for r in rows if want is None or r['name'] in want]
    print(f'running {len(rows)} design(s)', flush=True)
    for r in rows:
        name = r['name']
        od = out_root / name
        sp = od / 'scores.json'
        ep = od / 'error.json'
        if sp.exists():
            try:
                d = json.load(open(sp))
                if isinstance(d.get('iptm'), (int, float)):
                    print(f'skip {name} (already scored)', flush=True)
                    continue
            except Exception:
                pass
        if ep.exists() and ep.stat().st_size > 0:
            print(f'skip {name} (terminal error.json)', flush=True)
            continue
        if not admit(int(time.time())):
            print(f'CUTOFF_NO_NEW_ADMISSION {name}', flush=True)
            break
        od.mkdir(parents=True, exist_ok=True)
        work = pathlib.Path(f'/tmp/{name}')
        work.mkdir(parents=True, exist_ok=True)
        fa = work / f'{name}.fasta'
        fa.write_text(f'>{name}\n{r["binder"]}:{r["target"]}\n')
        cf = work / 'out'
        cf.mkdir(exist_ok=True)
        cmd = ['colabfold_batch', str(fa), str(cf),
               '--model-type', 'alphafold2_multimer_v3', '--num-recycle', '3',
               '--num-models', '5', '--rank', 'multimer',
               '--msa-mode', 'mmseqs2_uniref_env']
        t0 = time.time()
        p = subprocess.run(cmd, capture_output=True, text=True)
        sub = time.time() - t0
        sc = sorted(glob.glob(str(cf / '*_scores_rank_001_*.json')))
        pdb = sorted(glob.glob(str(cf / '*_rank_001_*.pdb')))
        if p.returncode != 0 or not sc:
            print(f'[{name}] FAILED rc={p.returncode} tail={p.stderr[-400:]}', flush=True)
            json.dump({'name': name, 'error': (p.stderr[-300:] or 'no rank_001 scores'),
                       'subprocess_wall_s': round(sub, 1)},
                      open(od / 'error.json', 'w'), indent=2)
            continue
        d = json.load(open(sc[0]))
        pl = d.get('plddt', [])
        res = {'name': name, 'source': r['source'],
               'binder_len': len(r['binder']), 'target_len': len(r['target']),
               'iptm': d.get('iptm'), 'ptm': d.get('ptm'),
               'mean_plddt': sum(pl) / len(pl) if pl else None,
               'model': os.path.basename(sc[0]),
               'predictor': 'colabfold_alphafold2_multimer_v3',
               'num_recycle': 3, 'num_models': 5,
               'subprocess_wall_s': round(sub, 1),
               'gpu': os.environ.get('RUNPOD_GPU_NAME', 'A40'),
               'run_host': 'runpod'}
        shutil.copy2(sc[0], od / 'scores_rank_001.json')
        if pdb:
            shutil.copy2(pdb[0], od / 'complex_rank_001.pdb')
        json.dump(res, open(sp, 'w'), indent=2)
        print(f'[{name}] iptm={res["iptm"]:.3f} ptm={res["ptm"]:.3f} '
              f'plddt={res["mean_plddt"]:.1f} sub={sub:.0f}s', flush=True)
    print('ALL_DONE', flush=True)


if __name__ == '__main__':
    main()
