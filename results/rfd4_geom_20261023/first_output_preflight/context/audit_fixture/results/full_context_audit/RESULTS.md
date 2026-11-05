# Full resolved receptor context audit

1 source candidates audited; 1 have no restored backbone clashes below 2 Å. 0 clash with protein omitted from the design crop. This is a rigid context-transfer diagnostic, not an experimental failure.

All source receptor Cα atoms in chains A/B are fitted to matched 11QC residue numbers. The binder is transformed by the same rotation/translation. Only atoms of residues absent from the source crop count as restored-context clashes. Backbone-to-backbone distances separate impossible occupancy from rotamers that might repack. No receptor or binder atoms were relaxed. Larger receptor conformational changes require independent refolding. 1 fits are <=2 Å Cα RMSD; all of these fail the backbone occupancy test. One fit exceeds 2 Å and must be interpreted as a failed context transfer, not an equally precise clash measurement.

Do not advance the old numerical pH winners directly to submission. The crop permitted docking into volume occupied by omitted receptor structure. Rebuild generation inputs with the full resolved dimer and test an accessible approach before local switch expansion. Old crop scores remain reproducible but do not validate full-receptor binding.

No new GPU spend from this CPU audit. See results/gpu_campaign/status.json for any separately authorized GPU work.
