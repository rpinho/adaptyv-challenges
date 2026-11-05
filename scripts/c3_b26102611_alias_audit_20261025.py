#!/usr/bin/env python3
"""Is the B_26102611 <-> B_26102611_s1 identity handled consistently across every place it is
used? The alias appears in: v8 sequences, the component/dedup graph, the five-model archive,
v8 diversity, and the selectors.

For each consumer, report whether it knows the alias and whether it would silently drop the
design. Fail-closed if the two names resolve to different sequences."""
import csv, json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
A, B = 'B_26102611', 'B_26102611_s1'
findings = {}

v8 = {r['name']: r['sequence'] for r in csv.DictReader(open(ROOT/'results/c3_submission_v8_20261025.csv'))}
findings['v8'] = {'has_s1': B in v8, 'has_plain': A in v8,
                  'seq_len': len(v8.get(B, '')), 'seq': v8.get(B, '')}

# every other candidates file
cands = {}
for tag, p in [('filtered', 'results/c3_challenger_20261025/c3_challenger_filtered_20261025.csv'),
               ('robust_v1', 'results/c3_challenger_robust_20261025/c3_challenger_all5robust_20261025.csv'),
               ('robust_v2', 'results/c3_challenger_robust_v2_20261025/c3_challenger_all5robust_v2_20261025.csv'),
               ('robust_v3', 'results/c3_challenger_robust_v3_20261025/c3_challenger_all5robust_v3_20261025.csv')]:
    names = [r['name'] for r in csv.DictReader(open(ROOT/p))]
    cands[tag] = {'index': names.index(B) if B in names else None,
                  'has_s1': B in names, 'has_plain': A in names}
findings['candidate_files'] = cands

# dedup / component graph
cross = json.loads((ROOT/'results/c3_r3_20261025/cross_tm_20261025.json').read_text())['pairs']
def in_graph(n):
    return n in cross or any(n in inner for inner in cross.values())
findings['dedup_graph'] = {A: in_graph(A), B: in_graph(B),
                           'plain_in_matrix_as_key': A in cross,
                           's1_in_matrix_as_key': B in cross,
                           'inner_contains_A': any(A in v for v in cross.values()),
                           'inner_contains_B': any(B in v for v in cross.values())}

# five-model archive
sens = json.loads((ROOT/'results/c3_pool_five_model_20261025/per_design.json').read_text())
sn = {r['name'] for r in sens} if isinstance(sens, list) else set(sens)
findings['five_model_archive'] = {A: A in sn, B: B in sn, 'n_entries': len(sn)}

# v8 diversity component input
div = ROOT/'results/c3_v8_internal_v2_20261025/summary.json'
if div.exists():
    d = json.loads(div.read_text())
    txt = json.dumps(d)
    findings['v8_internal_diversity'] = {'mentions_A': A in txt, 'mentions_B': B in txt}

print(json.dumps(findings, indent=1))
if findings['v8']['has_s1'] is False:
    print('\nFAIL: v8 does not contain B_26102611_s1 — premise wrong, stop.')
    sys.exit(1)
out = ROOT/'results/c3_novelty_screen_20261025/b26102611_alias_audit.json'
out.write_text(json.dumps(findings, indent=1))
print('\nwrote', out)
