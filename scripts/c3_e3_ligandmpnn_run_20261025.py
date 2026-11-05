#!/usr/bin/env python3
"""LigandMPNN side-chain-context clash pilot -- GPU runner (executed ON the pod).

Astra spec (results/decisions/20261025-e3-next-work-astra.md Q1):
  - <=12 clashing E3 parents with iPTM >= 0.850
  - freeze target seq+coords; redesign ONLY binder residues within 8 A of target
  - model_type ligand_mpnn, temperature 0.1, recorded seeds
  - 1 sequence per parent per condition: use_side_chain_context 1 vs 0
  - <=24 sequences total; else identical settings

Emits one FASTA per (parent, condition) and a hashed run record TSV.
"""
import argparse
import hashlib
import json
import pathlib
import subprocess
import sys
import time

LMPNN = pathlib.Path('/workspace/third_party/LigandMPNN')
PY = '/workspace/af2m/venv/bin/python'
CKPT = 'model_params/ligandmpnn_v_32_010_25.pt'
SEED = 20261029
TEMP = '0.1'


def sha(path):
    h = hashlib.sha256()
    with open(path, 'rb') as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b''):
            h.update(chunk)
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--parents', required=True)
    ap.add_argument('--pdbdir', required=True)
    ap.add_argument('--out', required=True)
    ap.add_argument('--record', required=True)
    ap.add_argument('--only', default='')
    a = ap.parse_args()

    parents = json.loads(pathlib.Path(a.parents).read_text())
    if a.only:
        keep = set(a.only.split(','))
        parents = [p for p in parents if p['name'] in keep]
    out = pathlib.Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    rec = pathlib.Path(a.record)
    new = not rec.exists()
    rows = []
    for p in parents:
        name = p['name']
        pdb = pathlib.Path(a.pdbdir) / (name + '.pdb')
        if not pdb.exists():
            rows.append([name, 'NA', 'MISSING_PDB', '', '', '', ''])
            continue
        fixed = ' '.join('A%d' % i for i in p['fixed_binder_residues'])
        for cond in ('0', '1'):
            dst = out / ('%s__sc%s' % (name, cond))
            if dst.exists():
                rows.append([name, cond, 'SKIP_EXISTS', '', '', '', ''])
                continue
            cmd = [PY, 'run.py', '--model_type', 'ligand_mpnn',
                   '--checkpoint_ligand_mpnn', CKPT,
                   '--pdb_path', str(pdb), '--out_folder', str(dst),
                   '--seed', str(SEED), '--temperature', TEMP,
                   '--number_of_batches', '1', '--batch_size', '1',
                   '--chains_to_design', 'A',
                   '--ligand_mpnn_use_side_chain_context', cond,
                   '--fixed_residues', fixed, '--verbose', '0']
            t0 = time.time()
            r = subprocess.run(cmd, cwd=LMPNN, capture_output=True, text=True)
            wall = round(time.time() - t0, 2)
            fa = dst / 'seqs' / (name + '.fa')
            if r.returncode != 0 or not fa.exists():
                rows.append([name, cond, 'FAIL_rc%d' % r.returncode, '', '', str(wall),
                             (r.stderr or '')[-300:].replace('\t', ' ')])
                continue
            # entry 0 is the native/parent sequence (same convention as MPNN); the
            # design is the last entry.
            lines = [l.strip() for l in fa.read_text().splitlines() if l.strip()]
            seqs = [l for l in lines if not l.startswith('>')]
            rows.append([name, cond, 'OK', sha(fa)[:16], sha(pdb)[:16], str(wall),
                         seqs[-1] if seqs else 'NO_SEQ'])
    hdr = ['parent', 'side_chain_context', 'status', 'fasta_sha16', 'pdb_sha16',
           'wall_s', 'sequence']
    with rec.open('a') as fh:
        if new:
            fh.write('\t'.join(hdr) + '\n')
        for row in rows:
            fh.write('\t'.join(str(x) for x in row) + '\n')
    ok = sum(1 for r in rows if r[2] == 'OK')
    print('PILOT_DONE ok=%d rows=%d' % (ok, len(rows)))


if __name__ == '__main__':
    sys.exit(main())
