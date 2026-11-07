# adaptyv-c4

Track 3 entry for **Challenge 4** of the
[Anthropic × Adaptyv Protein Design Competition](https://proteinbase.com/competitions/anthropic-adaptyv-2026).

**Target:** human transferrin receptor 1 (TfR1, UniProt P02786) — a pH-sensitive
conditional binder for blood–brain barrier transcytosis.

**Design criteria** (from the challenge specification):
- Bind at pH 7.4, no detectable binding at pH 6.0
- Mouse TfR1 (Q62351) cross-reactivity preferred
- Single-chain, 10–250 amino acids

## Method

Proton-coupled two-state binder design using RFdiffusion-Proteina
with histidine-enriched sequence conditioning, scored by Wyman linkage
analysis (PROPKA3 pKa shifts across pH). Candidates are screened through
a multi-stage pipeline: geometric metrics at generation time, structural
novelty via Foldseek/TM-align against PDB + patent databases, restored-context
clash audit against the full receptor, and mouse epitope conservation analysis.

See [METHOD.md](METHOD.md) for the full technical description with calibration
tables and scoring details.

## Running

```bash
python -m venv .venv && source .venv/bin/activate
pip install -e ".[all-cuda13]"  # or .[all-cpu] for local work

# CPU dry run (validates the spec, costs cents)
python modal_rfd4.py dry_run

# Generate 200 designs with inline geometric metrics
modal run modal_rfd4.py::generate --num-replicates 200 --batch-size 8 \
    --out-name tfr1_run --metrics geom

# CPU novelty screen
python scripts/run_cpu_novelty.py input.csv --databases databases.json \
    --structures structures.json
```

Requires a [Modal](https://modal.com) account for GPU generation and a local
install of [Foldseek](https://github.com/steineggerlab/foldseek) for structural
novelty screening.

## References

Every component of the pipeline is someone else's tool or model:

- [RFD4-Proteina](https://github.com/RosettaCommons/RFD4-Proteina) (Baker Lab x NVIDIA GenAIR) — backbone generation under histidine-enriched conditioning; it descends from [RFdiffusion](https://github.com/RosettaCommons/RFdiffusion) ([Watson et al. 2023](https://doi.org/10.1038/s41586-023-06415-8)).
- [ProteinMPNN](https://github.com/dauparas/ProteinMPNN) and [LigandMPNN](https://github.com/dauparas/LigandMPNN) ([Dauparas et al. 2022](https://doi.org/10.1126/science.add2187)) — sequence design on the generated backbones.
- [AlphaFold2-multimer](https://github.com/google-deepmind/alphafold) ([Jumper et al. 2021](https://doi.org/10.1038/s41586-021-03819-2)) via [ColabFold](https://github.com/sokrypton/ColabFold) ([Mirdita et al. 2022](https://doi.org/10.1038/s41592-022-01488-1)), [ESMFold](https://github.com/facebookresearch/esm) and [Boltz-2](https://github.com/jwohlwend/boltz) — complex prediction and the confidence scores the designs are screened on.
- [PROPKA3](https://github.com/jensengroup/propka) ([Olsson et al. 2011](https://doi.org/10.1021/ct100578z)) — the pKa shifts behind every pH claim; [PDB2PQR](https://pdb2pqr.readthedocs.io/en/stable/using/index.html) for structure preparation.
- Wyman linkage ([Wyman 1964](https://doi.org/10.1016/S0065-3233(08)60190-4)) — how pKa shifts become a pH-conditional binding score.
- [Foldseek](https://github.com/steineggerlab/foldseek) and [TM-align](https://zhanggroup.org/TM-align/) — structural novelty screening against the [PDB](https://www.rcsb.org/) and patent structures.
- [Modal](https://modal.com) — the GPU compute generation and folding run on. Target sequences from [UniProt](https://www.uniprot.org/).
- The challenge specifications, targets and criteria: the [Anthropic x Adaptyv protein design competition](https://proteinbase.com/competitions/anthropic-adaptyv-2026).

## Disclaimer

This is an independent entry. It is not affiliated with, endorsed by, or
sponsored by Adaptyv Bio, Anthropic, or any competition organiser. All designs
are original work by [Ricardo Pinho](https://github.com/rpinho).

## License

Code in this repository is provided for reference. Designed sequences submitted
to the competition are governed by the
[competition terms](https://proteinbase.com/competitions/anthropic-adaptyv-2026).
