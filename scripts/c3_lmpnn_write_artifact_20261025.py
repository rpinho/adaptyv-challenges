#!/usr/bin/env python3
"""Write Astra's required completion artifact: clash_context_pilot.tsv
(parent, condition, sequence, every gate, clash atom identities, runtime, failed/unrun status)."""
import csv, json, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
OUT = ROOT / 'results/c3_e3_ligandmpnn_20261025'
PILOT = OUT / 'pilot'

def main():
    ev = json.loads((PILOT / 'evaluation_20261025.json').read_text())
    rederived = {l.split('\t')[0] + '|' + l.split('\t')[1]: l.split('\t')
                 for l in (PILOT / 'rederived.tsv').read_text().splitlines()[1:] if l.strip()}
    rec = {l.split('\t')[0] + '|' + l.split('\t')[1]: l.split('\t')
           for l in (PILOT / 'pilot_record.tsv').read_text().splitlines()[1:] if l.strip()}
    clashes = {}
    cp = OUT / 'clash_atoms_pilot_20261025.json'
    if cp.exists():
        clashes = json.loads(cp.read_text())
    rows = []
    for r in ev['rows']:
        key = f"{r['parent']}|{r['condition']}"
        seq = (rederived.get(key) or ['']*7)[4]
        wall = (rec.get(key) or ['']*7)[5] if rec.get(key) else ''
        cl = clashes.get(r['name'], {})
        pairs = cl.get('pairs', [])
        atom_ids = ';'.join(f"{p.get('binder_res')}:{p.get('binder_atom')}-{p.get('target_res')}:{p.get('target_atom')}"
                            for p in pairs[:6])
        gates = {
            'scored': r['status'] == 'SCORED',
            'iptm': r['iptm'], 'ptm': r['ptm'], 'mean_plddt': r['mean_plddt'],
            'binder_mean_plddt': r['binder_mean_plddt'],
            'groove_residues_contacted': r['groove'],
            'target_binder_contacts_le5A': r['contacts'],
            'clash_pairs_lt2A': r['clashes'],
            'chain_integrity': r['fail'] if r['fail'] and 'CA-CA' in str(r['fail']) else '',
            'eligible': r['eligible'],
        }
        if r['status'] != 'SCORED':
            status = r['status']
        elif r['eligible']:
            status = 'PASS'
        else:
            status = 'FAIL'
        rows.append({
            'parent': r['parent'], 'condition': r['condition'], 'name': r['name'],
            'status': status,
            'sequence': seq,
            'binder_len': len(seq.split(':')[0]) if ':' in seq else '',
            'scored': gates['scored'], 'iptm': gates['iptm'], 'ptm': gates['ptm'],
            'mean_complex_plddt': gates['mean_plddt'],
            'binder_mean_plddt': gates['binder_mean_plddt'],
            'groove_residues_contacted': gates['groove_residues_contacted'],
            'contacts_le5A': gates['target_binder_contacts_le5A'],
            'clash_pairs_lt2A': gates['clash_pairs_lt2A'],
            'chain_integrity_problem': gates['chain_integrity'],
            'eligible': gates['eligible'],
            'clash_atom_ids': atom_ids,
            'ligandmpnn_wall_s': wall,
        })
    dst = PILOT / 'clash_context_pilot.tsv'
    with dst.open('w', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0]), delimiter='\t')
        w.writeheader(); w.writerows(rows)
    print(f'{len(rows)} rows -> {dst}')
    print('status:', {s: sum(1 for r in rows if r['status'] == s) for s in {r['status'] for r in rows}})
    return 0

if __name__ == '__main__':
    sys.exit(main())
