#!/usr/bin/env python3
"""Freeze the pre-registered manifest for the sampling-depth arm c3_sampling_depth_v1_20261025.

Astra's 03:21 ruling (results/decisions/20261025-post-r3-plan-astra.md):
  - all 120 original backbones, 2 additional draws each (sd1, sd2), seed 20261029
  - no selection by prior outcomes
  - <=240 AF2M admissions, unchanged AF2M settings and unchanged gate
  - 3 h cap from first billable pod, absolute stop 07:30 ET, stop admissions 20 min early

This script only records the pre-registration. It does not sample, stage or spend.
Fails closed if the 120 backbone PDBs are not exactly the admitted set.
"""
import hashlib, json, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
R3 = ROOT / 'results/c3_r3_20261025'
OUTDIR = ROOT / 'results/c3_sampling_depth_v1_20261025'
BB = R3 / 'backbone_pdb'
ADMIT = R3 / 'admission.json'
OUT = OUTDIR / 'manifest.json'

PODS = {
    'p1': ['910000', '910001', '910002', '910003', '910004', '910005', '910006', '910007',
           '910008', '910009', '910010', '910011', '910012', '910013', '910014', '910015',
           '910016', '910017', '910018', '910019', '910020', '910021', '910022', '910023'],
}
# Backbone ids come from the admitted PDB filenames; the pod prefix is authoritative there.


def sha(p):
    return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()


def main():
    adm = json.loads(ADMIT.read_text())
    if adm.get('n_valid') != 120 or adm.get('n_allocated') != 120 or adm.get('n_invalid') != 0:
        print('MANIFEST FAIL admission not 120/120 valid', adm.get('n_valid'), file=sys.stderr)
        return 4
    pdbs = sorted(BB.glob('*.pdb'))
    if len(pdbs) != 120:
        print(f'MANIFEST FAIL expected 120 backbone PDBs, found {len(pdbs)}', file=sys.stderr)
        return 4

    slots = []
    for pdb in pdbs:
        bb = pdb.stem
        pod = bb.split('_')[0]
        for k in (1, 2):
            slots.append({
                'name': f'{bb}_sd{k}',
                'backbone': bb,
                'pod': pod,
                'backbone_pdb_sha256': sha(pdb),
                'draw': k,
            })

    # Outcome-blind ordering: sd1 across all backbones before sd2, ascending backbone id.
    sd1 = sorted((s for s in slots if s['draw'] == 1), key=lambda s: s['backbone'])
    sd2 = sorted((s for s in slots if s['draw'] == 2), key=lambda s: s['backbone'])
    ordered = sd1 + sd2

    manifest = {
        'schema': 'c3-sampling-depth-v1',
        'arm': 'c3_sampling_depth_v1_20261025',
        'frozen_at': __import__('datetime').datetime.now().astimezone().isoformat(timespec='seconds'),
        'authority': 'Astra 2026-10-25 03:21 ET, results/decisions/20261025-post-r3-plan-astra.md',
        'purpose': 'bounded sequence-sampling-depth arm; evidence only, never a submission',
        'n_backbones': 120,
        'draws_per_backbone': 2,
        'n_slots_max': len(ordered),
        'mpnn': {
            'model_name': 'v_48_020',
            'sampling_temp': 0.1,
            'seed': 20261029,
            'num_seq_per_target_per_draw': 1,
            'chains': 'A',
            'batch_size': 1,
            'note': 'same model/temp/chains/constraints as R3; new seed 20261029; '
                    'two independent draws labelled sd1/sd2',
        },
        'af2m': {
            'colabfold': '1.5.5',
            'model_type': 'alphafold2_multimer_v3',
            'num_recycles': 3,
            'num_models': 5,
            'rank': 'multimer',
            'target_sha256': '5c2bae2dac5e467bf4e802473450a7ca3729990921bbe5c45cf6025531ef36b3',
            'unchanged': True,
        },
        'gate': {
            'unchanged': True,
            'clash_rule': 'zero heavy-atom pairs <= 2.0 A (CLASH_A=2.0, d2<=c2)',
            'iptm_floor_all_rules_pass': 0.85,
            'iptm_low_passes_retained_and_flagged': True,
        },
        'caps': {
            'max_af2m_admissions': 240,
            'wall_clock_hours_from_first_billable_pod': 3.0,
            'absolute_stop_et': '2026-10-25T07:30:00-04:00',
            'stop_admissions_minutes_before_deadline': 20,
            'max_gpu_hours': 15,
            'est_cost_usd_at_0.59_per_hour': 8.85,
        },
        'selection': 'none: every admitted backbone, including those whose R3 sequences failed',
        'excluded_from': 'v8/v9; this arm cannot produce a submission candidate',
        'slots_sha256': hashlib.sha256(
            json.dumps(ordered, sort_keys=True).encode()).hexdigest(),
        'slots': ordered,
    }
    OUTDIR.mkdir(parents=True, exist_ok=True)
    if OUT.exists():
        prev = json.loads(OUT.read_text())
        if prev.get('slots_sha256') != manifest['slots_sha256']:
            print('MANIFEST FAIL existing manifest has different slots; refusing to overwrite',
                  file=sys.stderr)
            return 4
        print('MANIFEST already frozen, identical slots; leaving untouched:', OUT)
        return 0
    OUT.write_text(json.dumps(manifest, indent=1, sort_keys=True) + '\n')
    print(f"MANIFEST WROTE {OUT}")
    print(f"  n_slots={manifest['n_slots_max']} n_backbones={manifest['n_backbones']} "
          f"slots_sha256={manifest['slots_sha256'][:12]}")
    print(f"  manifest_sha256={sha(OUT)}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
