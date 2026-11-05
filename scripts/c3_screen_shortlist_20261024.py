#!/usr/bin/env python3
"""Select the ~24-design RFD4 shortlist for the authorized C3 AF2-multimer screen.

Local, no GPU. Deterministic. Does NOT generate candidates — it only selects
from the existing RFD4 pool (results/c3_rfd4_sequences.csv, chain A = binder).

Selection (per audit results/c3_improvement_20261024.md §3, §6):
  1. Exclude any pool member already in v6 (by name AND by exact binder sequence).
  2. Keep biophysically plausible, soluble, non-TM binders:
       - max 19-residue Kyte-Doolittle hydrophobic window < 2.0   (non-TM)
       - GRAVY < 0.4                                               (soluble-ish)
       - charged fraction (KRDEH) >= 0.18                          (soluble-ish)
       - 40 <= length <= 100                                       (match v6 range)
       - canonical 20 AAs only
  3. From survivors, greedy max-min k-mer-Jaccard diversity pick of 24, seeded by
     the member most novel vs the current 20, so the shortlist spreads across the
     pool rather than clustering.

Output: results/c3_screen_shortlist_20261024.csv  (name,sequence,molecule_class,...metrics)

Limitations: k-mer Jaccard is an alignment-free sequence proxy, not structural
identity. Groove-relevance is by construction (the whole RFD4 pool was generated
against the ECD groove with the same hotspots); it is NOT re-verified here. No
affinity / agonism is predicted. "Soluble/non-TM" are heuristics, not measurements.
"""
import csv
from pathlib import Path

ROOT = Path("/Users/ricardo/dev/adaptyv-c4")
V6 = ROOT / "results/c3_submission_v6_20261023.csv"
POOL = ROOT / "results/c3_rfd4_sequences.csv"
OUT = ROOT / "results/c3_screen_shortlist_20261024.csv"

N_SELECT = 24
CANON = set("ACDEFGHIKLMNPQRSTVWY")
KD = {'A':1.8,'R':-4.5,'N':-3.5,'D':-3.5,'C':2.5,'Q':-3.5,'E':-3.5,'G':-0.4,
      'H':-3.2,'I':4.5,'L':3.8,'K':-3.9,'M':1.9,'F':2.8,'P':-1.6,'S':-0.8,
      'T':-0.7,'W':-0.9,'Y':-1.3,'V':4.2}


def kmers(seq, k=3):
    return {seq[i:i+k] for i in range(len(seq) - k + 1)}


def jaccard(a, b):
    ka, kb = kmers(a), kmers(b)
    return len(ka & kb) / len(ka | kb) if (ka | kb) else 0.0


def gravy(seq):
    return sum(KD[c] for c in seq) / len(seq)


def max_window_gravy(seq, w=19):
    if len(seq) < w:
        return gravy(seq)
    return max(sum(KD[c] for c in seq[i:i + w]) / w for i in range(len(seq) - w + 1))


def charged_frac(seq):
    return sum(seq.count(x) for x in "KRDEH") / len(seq)


# ---- current 20 (to exclude + measure novelty against) ----
with open(V6) as f:
    cur = [(r["name"], r["sequence"]) for r in csv.DictReader(f)]
cur_names = {n for n, _ in cur}
cur_seqs = {s for _, s in cur}
cur_seq_list = [s for _, s in cur]

# ---- RFD4 pool: chain A binders ----
pool = {}
with open(POOL) as f:
    for r in csv.DictReader(f):
        if r["chain"].strip() == "A":
            pool[r["design"]] = r["sequence"].strip()
print(f"Pool chain-A binders: {len(pool)}")

# ---- filter ----
survivors = []
for name, seq in pool.items():
    if name in cur_names or seq in cur_seqs:
        continue  # already selected in v6
    if not set(seq) <= CANON:
        continue
    L = len(seq)
    if not (40 <= L <= 100):
        continue
    mwg = max_window_gravy(seq)
    g = gravy(seq)
    cf = charged_frac(seq)
    if mwg >= 2.0:       # transmembrane-like hydrophobic stretch
        continue
    if g >= 0.4:         # too hydrophobic overall
        continue
    if cf < 0.18:        # too few charged residues (aggregation risk)
        continue
    novelty = 1.0 - max(jaccard(seq, cs) for cs in cur_seq_list)
    survivors.append({"name": name, "sequence": seq, "length": L,
                      "gravy": round(g, 3), "max_hydro_window": round(mwg, 3),
                      "charged_frac": round(cf, 3), "novelty_vs_v6": round(novelty, 3)})
print(f"Survivors after soluble/non-TM filter: {len(survivors)}")

# ---- greedy max-min diversity selection of N_SELECT ----
# seed with the most novel vs v6, then repeatedly add the survivor that maximizes
# the minimum Jaccard-distance to the already-selected set (spread the shortlist).
survivors.sort(key=lambda d: -d["novelty_vs_v6"])
selected = [survivors[0]]
remaining = survivors[1:]
while len(selected) < min(N_SELECT, len(survivors)):
    best, best_mindist = None, -1.0
    for cand in remaining:
        mindist = min(1.0 - jaccard(cand["sequence"], s["sequence"]) for s in selected)
        if mindist > best_mindist:
            best_mindist, best = mindist, cand
    selected.append(best)
    remaining.remove(best)
    best["min_dist_at_pick"] = round(best_mindist, 3)
selected[0]["min_dist_at_pick"] = 1.0

# ---- write ----
fields = ["name", "sequence", "molecule_class", "length", "gravy",
          "max_hydro_window", "charged_frac", "novelty_vs_v6", "min_dist_at_pick"]
with open(OUT, "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=fields)
    w.writeheader()
    for d in selected:
        d["molecule_class"] = "single_chain"
        w.writerow({k: d.get(k, "") for k in fields})

print(f"\nSelected {len(selected)} → {OUT}")
for d in selected:
    print(f"  {d['name']:<22s} L={d['length']:>3d} gravy={d['gravy']:>6.2f} "
          f"maxhyd={d['max_hydro_window']:>5.2f} nov={d['novelty_vs_v6']:.2f}")
