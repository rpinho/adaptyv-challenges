#!/usr/bin/env python3
"""R3 admission: verify every generated backbone, emit the 120-seed provenance/validity report.

Reads the per-pod R3 generation records and CIFs. Reuses the round-2 construct verifier
(imported, never reimplemented), so R3 admissions use the exact same 111-mer target and
C-alpha geometry gate as rounds 1-2 and E3.

Writes only results/c3_r3_20261025/:
  admission.json       one record per allocated seed (valid/invalid/missing + why)
  records.jsonl        the merged 120-seed attempt record (real pod records only)
  backbone_pdb/        heavy-atom PDBs for admitted backbones (MPNN input)
  seed_manifest.json   hash of the allocation and of every input record

Never touches v6/v7/v8, E2, E3, or the R2 evidence.
"""
import argparse
import hashlib
import json
import pathlib
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import c3_r3_queue_20261025 as Q  # ALLOC is the single frozen allocation
import c3_round2_construct_20261025 as construct

R3 = ROOT / 'results/c3_r3_20261025'


def sha(path):
    return hashlib.sha256(pathlib.Path(path).read_bytes()).hexdigest()


def pod_specs():
    return {'p1': ('63.141.33.138', 22113), 'p2': ('194.68.245.32', 22065),
            'p3': ('69.30.85.102', 22129), 'p4': ('194.68.245.69', 22022),
            'p5': ('194.68.245.147', 22117)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--pull', action='store_true', help='rsync /workspace/r3 from every pod first')
    ap.add_argument('--json', default=str(R3 / 'admission.json'))
    a = ap.parse_args()
    if a.pull:
        key = pathlib.Path.home() / '.ssh/runpod_ed25519'
        for pod, (host, port) in pod_specs().items():
            dst = R3 / 'pods' / pod
            dst.mkdir(parents=True, exist_ok=True)
            for sub in ('out', 'logs'):
                subprocess.run(['rsync', '-az', '--timeout=120', '-e',
                                f'ssh -i {key} -p {port} -o ConnectTimeout=10 '
                                f'-o StrictHostKeyChecking=no -o BatchMode=yes',
                                f'root@{host}:/workspace/r3/{sub}/', str(dst / (sub + '/'))],
                               check=False)

    alloc = Q.allocation_map()
    records, seen = [], {}
    for pod in pod_specs():
        rec = R3 / 'pods' / pod / 'logs' / 'records.jsonl'
        if not rec.exists():
            continue
        for line in rec.read_text().splitlines():
            if not line.strip():
                continue
            try:
                d = json.loads(line)
            except Exception as ex:
                print(f'BAD_RECORD {pod}: {ex}', file=sys.stderr)
                continue
            key = (d.get('pod'), int(d.get('seed', -1)))
            if key in seen:
                # Keep the first real attempt; duplicates are counted, never hidden.
                seen[key]['duplicate_records'] = seen[key].get('duplicate_records', 0) + 1
                continue
            seen[key] = d

    rows = []
    for bb, meta in sorted(alloc.items(), key=lambda kv: (kv[1]['pod'], kv[1]['seed'])):
        pod, seed = meta['pod'], meta['seed']
        r = dict(meta, backbone=bb)
        rec = seen.get((pod, seed))
        r['record_present'] = bool(rec)
        if rec:
            r['record_status'] = rec.get('status')
            r['record'] = rec
        cand = sorted((R3 / 'pods' / pod / 'out' / bb).rglob('*_generated.cif')) \
            if (R3 / 'pods' / pod / 'out' / bb).exists() else []
        r['n_cifs'] = len(cand)
        if len(cand) != 1:
            r['valid'] = False
            r['reason'] = 'missing output' if not cand else f'{len(cand)} CIFs in one seed dir'
            rows.append(r)
            continue
        cif = cand[0]
        try:
            v = construct.verify(cif)
        except Exception as ex:
            r['valid'] = False
            r['reason'] = f'construct: {ex}'
            r['cif'] = str(cif.relative_to(ROOT))
            rows.append(r)
            continue
        r.update({'valid': True, 'cif': str(cif.relative_to(ROOT)),
                  'cif_sha256': sha(cif),
                  'target_length': v['target_length'],
                  'target_sequence_sha256': v['target_sequence_sha256'],
                  'ca_distance_min': v['ca_distance_min'],
                  'ca_distance_max': v['ca_distance_max'],
                  'intended_len': None})
        pdb = R3 / 'backbone_pdb' / f'{bb}.pdb'
        pdb.parent.mkdir(parents=True, exist_ok=True)
        rc = subprocess.run([sys.executable, str(ROOT / 'scripts/cif_to_pdb_20261025.py'),
                             str(cif), str(pdb)], capture_output=True, text=True)
        if rc.returncode != 0:
            r['valid'] = False
            r['reason'] = f'cif_to_pdb failed: {rc.stderr[-300:]}'
        else:
            r['pdb'] = str(pdb.relative_to(ROOT))
        rows.append(r)

    n_valid = sum(r.get('valid', False) for r in rows)
    n_records = sum(r.get('record_present', False) for r in rows)
    allocation = {pod: [[tag, b, [int(s) for s in seeds]] for tag, b, seeds in jobs]
                  for pod, jobs in Q.ALLOC.items()}
    out = {'allocation': allocation, 'n_allocated': len(rows), 'n_records': n_records,
           'n_valid': n_valid, 'n_invalid': len(rows) - n_valid,
           'records_sha256': {p: sha(R3 / 'pods' / p / 'logs' / 'records.jsonl')
                              for p in pod_specs()
                              if (R3 / 'pods' / p / 'logs' / 'records.jsonl').exists()},
           'records': rows}
    pathlib.Path(a.json).write_text(json.dumps(out, indent=1) + '\n')
    with (R3 / 'records.jsonl').open('w') as fh:
        for r in rows:
            rec = r.get('record') or {}
            fh.write(json.dumps({'backbone': r['backbone'], 'pod': r['pod'],
                                 'arm': r['arm'], 'bin': r['bin'], 'seed': r['seed'],
                                 'record': rec, 'valid': r.get('valid', False),
                                 'reason': r.get('reason'),
                                 'cif': r.get('cif'), 'cif_sha256': r.get('cif_sha256')},
                                sort_keys=True) + '\n')
    print(f'R3 admission: {n_records}/120 attempt records, {n_valid}/120 valid backbones')
    for r in rows:
        if not r.get('valid'):
            print(f"  INVALID {r['backbone']}: {r.get('reason')}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
