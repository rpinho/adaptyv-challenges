#!/usr/bin/env python3
"""Prepare the continuous AF2M 111-aa target, or verify actual RFD4 CIFs.

Requires Biopython and NumPy. No GPU work or historical-file modification.
"""
import argparse
import csv
import hashlib
import io
import json
from pathlib import Path

import numpy as np
from Bio.PDB import MMCIFIO, PDBParser
from Bio.PDB.MMCIF2Dict import MMCIF2Dict
from Bio.SeqUtils import seq1

ROOT = Path(__file__).resolve().parents[1]
SCREEN = ROOT / 'results/c3_screen_input_20261024.csv'
SOURCE = ROOT / 'results/c3_pod_artifacts_20261025/c3_bc_l57_fbcf76_complex.pdb'
TARGET = ROOT / 'data/c3_ecd111_af2m_target_20261025.cif'
NONBACKBONE_TERMINAL = {'OXT'}
HOTSPOTS = {42: 5, 48: 11, 49: 12, 77: 40, 78: 41, 100: 63, 97: 60, 130: 93}


def expected():
    with SCREEN.open(newline='') as f:
        targets = {r['target'] for r in csv.DictReader(f)}
    assert len(targets) == 1, 'screen contains multiple target sequences'
    s = targets.pop()
    assert len(s) == 111
    return s


def verify(path, geometry=True):
    d = MMCIF2Dict(str(path))
    keys = ['label_asym_id', 'label_seq_id', 'label_comp_id', 'label_atom_id',
            'type_symbol', 'Cartn_x', 'Cartn_y', 'Cartn_z']
    residues = {}
    for ch, rid, name, atom, element, x, y, z in zip(*(d['_atom_site.' + k] for k in keys)):
        if ch != 'F':
            continue
        assert rid.isdigit(), f'{path}: nonpolymer in F'
        r = residues.setdefault(int(rid), {'name': name, 'atoms': {}, 'unplaced': {},
                                           'hydrogen': 0})
        assert r['name'] == name, f'{path}: inconsistent residue name at {rid}'
        if element.upper() == 'H':
            # RFD4 emits hydrogen rows without coordinates; they are not target evidence.
            assert atom not in r['atoms'], f'{path}: hydrogen name collides with heavy atom {atom}'
            r['hydrogen'] += 1
            continue
        assert atom not in r['atoms'] and atom not in r['unplaced'], \
            f'{path}: duplicate/alternate atom {atom} at {rid}'
        coord = np.array([x, y, z], dtype=float)
        if not np.isfinite(coord).all():
            r['unplaced'][atom] = True
            continue
        r['atoms'][atom] = coord
    assert sorted(residues) == list(range(1, 112)), f'{path}: target residue ids/count differ'
    rs = [residues[i] for i in range(1, 112)]
    sequence = ''.join(seq1(r['name']) for r in rs)
    assert sequence.encode('ascii') == expected().encode('ascii'), f'{path}: target mismatch'
    for r in rs:
        assert set(('N', 'CA', 'C', 'O')) <= set(r['atoms']), f'{path}: missing backbone'
        assert not set(r['unplaced']) & set(('N', 'CA', 'C', 'O')), \
            f'{path}: unplaced backbone atom at {r["name"]}'
        assert all(np.isfinite(x).all() for x in r['atoms'].values()), \
            f'{path}: nonfinite heavy-atom coordinates'
    distances = [float(np.linalg.norm(a['atoms']['CA'] - b['atoms']['CA']))
                 for a, b in zip(rs, rs[1:])]
    if geometry:
        assert all(3.5 <= x <= 4.1 for x in distances), f'{path}: broken target backbone'
    # Where sequence metadata exists, it must agree with the coordinate sequence.
    if '_entity_poly_seq.mon_id' in d:
        entity_ids = {e for ch, e in zip(d['_atom_site.label_asym_id'],
                                      d['_atom_site.label_entity_id']) if ch == 'F'}
        assert len(entity_ids) == 1
        eid = entity_ids.pop()
        entity_sequence = ''.join(seq1(n) for e, n in zip(d['_entity_poly_seq.entity_id'],
                                                         d['_entity_poly_seq.mon_id']) if e == eid)
        assert entity_sequence == sequence, f'{path}: entity sequence mismatch'
    unplaced = sorted({f'{i}:{a}' for i, r in residues.items() for a in r['unplaced']})
    assert all(entry.split(':', 1)[1] in NONBACKBONE_TERMINAL for entry in unplaced), \
        f'{path}: unplaced non-terminal heavy atoms {unplaced}'
    return {'file': str(path), 'target_length': len(sequence), 'unplaced_atoms': unplaced,
            'target_sequence_sha256': hashlib.sha256(sequence.encode()).hexdigest(),
            'ca_distance_min': min(distances), 'ca_distance_max': max(distances)}


def write_new(path, content):
    if path.exists():
        assert path.read_text() == content, f'refusing to replace different file: {path}'
    else:
        path.write_text(content)


def prepare():
    structure = PDBParser(QUIET=True).get_structure('c3_ecd111', str(SOURCE))
    assert len(structure) == 1
    chains = [c for c in structure[0]
              if ''.join(seq1(r.resname) for r in c) == expected()]
    assert len(chains) == 1
    chain = chains[0].copy()
    chain.detach_parent()
    chain.id = 'F'
    for i, residue in enumerate(chain, 1):
        assert residue.id == (' ', i, ' '), 'unexpected source numbering'
    deposited = MMCIF2Dict(str(ROOT / 'data/6x18.cif'))
    entity = deposited['_struct_asym.entity_id'][deposited['_struct_asym.id'].index('F')]
    original = deposited['_entity_poly.pdbx_seq_one_letter_code_can'][
        deposited['_entity_poly.entity_id'].index(entity)].replace('\n', '')
    assert original[138:144] == 'KRGERS'
    assert original[37:138] + original[144:154] == expected()
    for old, new in HOTSPOTS.items():
        assert original[old - 1] == expected()[new - 1]
    hotspot_atoms = {5: ('CE2', 'NE1'), 11: ('CE2', 'NE1'), 12: ('NH1', 'NH2'),
                     40: ('OE1', 'OE2'), 41: ('OH',), 63: ('CE2', 'NE1'),
                     60: ('OH',), 93: ('NH1', 'NH2')}
    for pos, atoms in hotspot_atoms.items():
        assert all(atom in chain[pos] for atom in atoms), f'missing hotspot atoms at {pos}'
    writer = MMCIFIO()
    writer.set_structure(chain)
    buffer = io.StringIO()
    writer.save(buffer)
    d = MMCIF2Dict(io.StringIO(buffer.getvalue()))
    n = len(d['_atom_site.id'])
    d['_atom_site.label_asym_id'] = ['F'] * n
    d['_atom_site.auth_asym_id'] = ['F'] * n
    d['_atom_site.label_entity_id'] = ['1'] * n
    d['_entity.id'] = ['1']
    d['_entity.type'] = ['polymer']
    d['_struct_asym.id'] = ['F']
    d['_struct_asym.entity_id'] = ['1']
    d['_entity_poly.entity_id'] = ['1']
    d['_entity_poly.type'] = ['polypeptide(L)']
    d['_entity_poly.pdbx_strand_id'] = ['F']
    d['_entity_poly.pdbx_seq_one_letter_code'] = [expected()]
    d['_entity_poly.pdbx_seq_one_letter_code_can'] = [expected()]
    d['_entity_poly_seq.entity_id'] = ['1'] * 111
    d['_entity_poly_seq.num'] = list(map(str, range(1, 112)))
    d['_entity_poly_seq.mon_id'] = [r.resname for r in chain]
    d['_entity_poly_seq.hetero'] = ['n'] * 111
    writer.set_dict(d)
    buffer = io.StringIO()
    writer.save(buffer)
    write_new(TARGET, buffer.getvalue())
    audit = verify(TARGET)
    base = (ROOT / 'configs/rfd4/c3_glp1r_ecd.yaml').read_text()
    specs = []
    for lo, hi in ((52, 64), (65, 80), (81, 100)):
        text = base.replace('c3_glp1r_ecd:', f'c3_ecd111_r2_{lo}_{hi}:', 1)
        text = text.replace('input: 6x18.cif', 'input: ../../data/' + TARGET.name)
        text = text.replace('45-100, /0, F38-154', f'{lo}-{hi}, /0, F1-111')
        text = text.replace('F/*/[38-154]', 'F/*/[1-111]')
        for old, new in HOTSPOTS.items():
            text = text.replace(f'F/*/{old}/', f'F/*/{new}/')
        path = ROOT / f'configs/rfd4/c3_ecd111_r2_{lo}_{hi}.yaml'
        write_new(path, text)
        specs.append(str(path.relative_to(ROOT)))
    audit.update(source=str(SOURCE.relative_to(ROOT)),
                 source_sha256=hashlib.sha256(SOURCE.read_bytes()).hexdigest(),
                 target_file_sha256=hashlib.sha256(TARGET.read_bytes()).hexdigest(),
                 provenance='AF2M predicted target only; no binder coordinates retained',
                 old_label_to_new_hotspots=HOTSPOTS, specs=specs)
    output = ROOT / 'results/c3_round2_20261025/construct111_audit.json'
    write_new(output, json.dumps(audit, indent=2) + '\n')
    print(json.dumps(audit, indent=2))


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('mode', choices=['prepare', 'verify'])
    p.add_argument('cifs', nargs='*', type=Path)
    args = p.parse_args()
    if args.mode == 'prepare':
        assert not args.cifs
        prepare()
    else:
        assert args.cifs, 'supply actual full-complex CIF paths'
        for path in args.cifs:
            print(json.dumps(verify(path)))
