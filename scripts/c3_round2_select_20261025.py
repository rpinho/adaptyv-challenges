#!/usr/bin/env python3
"""72 -> 24 selection, exactly Kimi round-2 plan §4.

Eligible = refold pass (mean pLDDT>=80, frac70>=0.90, CA RMSD<=3.0) — computed by
c3_round2_refold_merge_20261025.py — AND the pre-registered soluble/non-TM filters
(canonical AAs, max-19 GRAVY<2.0, overall GRAVY<0.4, KRDEH>=0.18). Rank lexicographically: RMSD asc, mean pLDDT desc,
frac70 desc, sequence id asc. Clusters are on DESIGNED BACKBONES (clusters_20261025.json);
both sequences of a backbone inherit its cluster. Selection: order clusters by best
eligible sequence, take best from each cluster, then a second pass taking each cluster's
second-best, stop at 24. Require 24 unique, <=2 per cluster, >=8 clusters, all eligible.
"""
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from c3_soluble_filters_20261025 import failures as filter_failures  # noqa: E402
sys.path.insert(0, str(ROOT / "scripts"))
import c3_soluble_filters_20261025 as soluble  # noqa: E402
R2 = ROOT / 'results/c3_round2_111_20261025'


OUT_NAME = None

# Thresholds, unchanged from the round-2 plan. Exposed so tests can assert the boundaries.
MIN_PLDDT, MIN_FRAC70, MAX_RMSD = 80.0, 0.90, 3.0
MIN_SELECTED, MAX_PER_CLUSTER, MIN_CLUSTERS = 24, 2, 8
_RANK_FIELDS = ("rmsd", "mean_plddt", "frac70", "seq_id")


class SelectionError(RuntimeError):
    """The pool cannot satisfy the selection contract. Always stops, never backfills."""


def eligible(rec):
    """True iff a record passes every refold threshold (inclusive at the boundaries)."""
    try:
        return (bool(rec.get("refold_ok"))
                and float(rec["mean_plddt"]) >= MIN_PLDDT
                and float(rec["frac70"]) >= MIN_FRAC70
                and float(rec["rmsd"]) <= MAX_RMSD)
    except (KeyError, TypeError, ValueError):
        return False


def rank_key(rec):
    """Lexicographic ranking: RMSD asc, pLDDT desc, frac70 desc, id asc."""
    return (float(rec["rmsd"]), -float(rec["mean_plddt"]), -float(rec["frac70"]),
            str(rec.get("seq_id") or rec.get("name")))


def select(recs, cluster_of):
    """Take the best eligible sequence per cluster, then a second pass, stop at 24.

    Raises SelectionError instead of asserting, so callers fail closed with a usable message.
    Returns (chosen, report). Never mutates ``recs``.
    """
    ids = [str(r.get("seq_id") or r.get("name")) for r in recs]
    if len(set(ids)) != len(ids):
        raise SelectionError("duplicate ids in the candidate pool")
    unknown = sorted({r.get("backbone") for r in recs} - set(cluster_of))
    if unknown:
        raise SelectionError(f"unknown backbone(s) with no cluster: {unknown[:4]}")
    pool = []
    for r in recs:
        if not eligible(r):
            continue
        e = dict(r)
        e["seq_id"] = str(r.get("seq_id") or r.get("name"))
        e["cluster"] = cluster_of[r["backbone"]]
        pool.append(e)
    if not pool:
        raise SelectionError("no eligible sequence in the pool")
    pool.sort(key=rank_key)
    by_cluster = {}
    for e in pool:
        by_cluster.setdefault(e["cluster"], []).append(e)
    order = sorted(by_cluster, key=lambda c: rank_key(by_cluster[c][0]))
    chosen, count = [], {}
    for pass_i in (1, 2):
        for c in order:
            if len(chosen) >= MIN_SELECTED:
                break
            if len(by_cluster[c]) < pass_i:
                continue
            chosen.append(by_cluster[c][pass_i - 1])
            count[c] = count.get(c, 0) + 1
        if len(chosen) >= MIN_SELECTED:
            break
    if len(chosen) < MIN_SELECTED:
        raise SelectionError(f"insufficient pool: only {len(chosen)} selectable, need {MIN_SELECTED}")
    if len(count) < MIN_CLUSTERS:
        raise SelectionError(f"too few clusters: {len(count)} < {MIN_CLUSTERS}")
    if max(count.values()) > MAX_PER_CLUSTER:
        raise SelectionError(f"cluster cap violated: {count}")
    if len({e["seq_id"] for e in chosen}) != MIN_SELECTED:
        raise SelectionError("duplicate names among selected")
    if len({e["sequence"] for e in chosen}) != MIN_SELECTED:
        raise SelectionError("duplicate sequences among selected")
    return chosen, {"n_selected": len(chosen), "n_clusters": len(count),
                    "max_per_cluster": max(count.values()), "per_cluster": count}


def main():
    refold = json.loads((R2 / 'refold_checks_20261025.json').read_text())
    clusters = json.loads((R2 / 'clusters_20261025.json').read_text())['cluster_of']
    seqs = json.loads((R2 / 'mpnn_sequences_20261025.json').read_text())

    eligible = []
    for s in seqs:
        if s['sample'] == 0:
            continue
        name = f"{s['backbone']}_s{s['sample']}"
        rec = refold.get(name)
        if not rec or not rec['pass']:
            continue
        # Kimi plan §2 step 3: the four soluble/non-TM filters are hard eligibility
        # conditions, so they must be applied BEFORE selection, not after screening.
        if filter_failures(s['seq']):
            continue
        # Kimi 2026-10-25 plan §2 step 3: soluble / non-TM filters are ELIGIBILITY
        # conditions, not ranking preferences. Applied before clustering.
        if not soluble.passes(s['seq']):
            continue
        eligible.append({'name': name, 'backbone': s['backbone'],
                         'cluster': clusters[s['backbone']], 'sequence': s['seq'],
                         'length': s['len'],
                         'rmsd': rec['ca_rmsd_vs_designed_backbone'],
                         'mean_plddt': rec['refold_mean_plddt'],
                         'frac70': rec['refold_frac_residues_plddt_ge70']})
    eligible.sort(key=lambda r: (r['rmsd'], -r['mean_plddt'], -r['frac70'], r['name']))
    print(f'eligible: {len(eligible)} of {len(seqs) - len([s for s in seqs if not s["sample"]])}')

    by_cluster = {}
    for e in eligible:
        by_cluster.setdefault(e['cluster'], []).append(e)
    order = sorted(by_cluster, key=lambda c: (by_cluster[c][0]['rmsd'],
                                              -by_cluster[c][0]['mean_plddt'],
                                              -by_cluster[c][0]['frac70'],
                                              by_cluster[c][0]['name']))
    picked, count = [], {}
    for pass_i in (1, 2):
        for c in order:
            if len(picked) >= 24:
                break
            members = by_cluster[c]
            if len(members) < pass_i:
                continue
            e = members[pass_i - 1]
            picked.append(e)
            count[c] = count.get(c, 0) + 1
        if len(picked) >= 24:
            break

    assert len(picked) == 24, f'only {len(picked)} selected'
    assert len({e['name'] for e in picked}) == 24, 'duplicate names'
    assert len({e['sequence'] for e in picked}) == 24, 'duplicate sequences'
    assert max(count.values()) <= 2, f'cluster cap violated: {count}'
    assert len(count) >= 8, f'only {len(count)} clusters represented'
    assert all(e['rmsd'] is not None and e['rmsd'] <= 3.0 for e in picked)
    print(f'selected 24 across {len(count)} clusters; max/cluster {max(count.values())}')
    (R2 / 'selected24_filtered_20261025.json').write_text(json.dumps(picked, indent=1) + '\n')
    print('sequence lengths', sorted({e['length'] for e in picked}))
    print('rmsd range', min(e['rmsd'] for e in picked), max(e['rmsd'] for e in picked))


if __name__ == '__main__':
    main()
