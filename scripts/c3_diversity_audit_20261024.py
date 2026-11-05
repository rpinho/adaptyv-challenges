#!/usr/bin/env python3
"""C3 portfolio diversity audit (local, no GPU).

Reads the v6 submission and the RFD4 pool, quantifies:
  1. Independent-backbone structure of the current 20 (k-mer Jaccard clustering).
  2. Which unselected RFD4 pool members are (a) biophysically plausible soluble
     binders and (b) maximally novel vs. the current selection -> ranked
     candidate additions.

No affinity/agonism is predicted. k-mer Jaccard is an alignment-free sequence
diversity proxy, not a structural identity.
"""
import csv, sys, itertools
from pathlib import Path

ROOT = Path("/Users/ricardo/dev/adaptyv-c4")
V6 = ROOT / "results/c3_submission_v6_20261023.csv"
POOL = ROOT / "results/c3_rfd4_sequences.csv"

KD = {  # Kyte-Doolittle
 'A':1.8,'R':-4.5,'N':-3.5,'D':-3.5,'C':2.5,'Q':-3.5,'E':-3.5,'G':-0.4,
 'H':-3.2,'I':4.5,'L':3.8,'K':-3.9,'M':1.9,'F':2.8,'P':-1.6,'S':-0.8,
 'T':-0.7,'W':-0.9,'Y':-1.3,'V':4.2}

def kmers(seq, k=3):
    return {seq[i:i+k] for i in range(len(seq)-k+1)}

def jaccard(a, b):
    ka, kb = kmers(a), kmers(b)
    return len(ka & kb) / len(ka | kb) if (ka | kb) else 0.0

def charge_KRDE(seq):
    return sum(seq.count(x) for x in "KR") - sum(seq.count(x) for x in "DE")

def charged_frac(seq):
    return sum(seq.count(x) for x in "KRDEH") / len(seq)

def gravy(seq):
    return sum(KD[c] for c in seq) / len(seq)

def max_window_gravy(seq, w=19):
    if len(seq) < w: return gravy(seq)
    return max(sum(KD[c] for c in seq[i:i+w])/w for i in range(len(seq)-w+1))

def wy_pct(seq):
    return 100*(seq.count("W")+seq.count("Y"))/len(seq)

def load_csv(path):
    with open(path) as f:
        return list(csv.DictReader(f))

# ---- current 20 ----
cur = [(r["name"], r["sequence"]) for r in load_csv(V6)]
print(f"Current submission: {len(cur)} designs\n")

# cluster by k-mer Jaccard >= 0.4 (greedy single-linkage)
names = [n for n,_ in cur]
seqs  = dict(cur)
THR = 0.40
clusters = []
for n in names:
    placed = False
    for cl in clusters:
        if any(jaccard(seqs[n], seqs[m]) >= THR for m in cl):
            cl.append(n); placed = True; break
    if not placed:
        clusters.append([n])
print(f"Independent backbone clusters (Jaccard>={THR}): {len(clusters)}")
for i, cl in enumerate(clusters):
    tag = "  <-- REDUNDANT" if len(cl) > 1 else ""
    print(f"  cluster {i+1} (n={len(cl)}): {', '.join(cl)}{tag}")

# ---- RFD4 pool: binder chains (chain A) ----
pool_rows = [r for r in load_csv(POOL) if r["chain"] == "A"]
cur_seqs = list(seqs.values())
cur_names_set = set(seqs.values())

cands = []
for r in pool_rows:
    s = r["sequence"]
    if s in cur_names_set:  # already selected
        continue
    if any(c not in KD for c in s):
        continue
    mw = max_window_gravy(s)
    cf = charged_frac(s)
    # stated C3 filters: non-TM (max19 window GRAVY < 1.6) and soluble (charged frac > 0.15)
    tm_like = mw >= 1.6
    soluble = cf > 0.15
    novelty = 1.0 - max(jaccard(s, cs) for cs in cur_seqs)  # 1 = most novel
    cands.append({
        "name": r["design"], "len": len(s), "charge": charge_KRDE(s),
        "gravy": round(gravy(s),2), "max19": round(mw,2), "cf": round(cf,2),
        "wy": round(wy_pct(s),1), "tm_like": tm_like, "soluble": soluble,
        "novelty": round(novelty,3), "seq": s})

passing = [c for c in cands if not c["tm_like"] and c["soluble"]]
passing.sort(key=lambda c: c["novelty"], reverse=True)
print(f"\nRFD4 pool binder candidates: {len(cands)} unselected; "
      f"{len(passing)} pass non-TM + soluble filters")
print("\nTop 15 most-novel passing candidates (vs. current 20):")
print(f"{'name':28} {'len':>3} {'chg':>4} {'gravy':>6} {'max19':>6} {'cf':>5} {'wy%':>5} {'novelty':>8}")
for c in passing[:15]:
    print(f"{c['name']:28} {c['len']:>3} {c['charge']:>4} {c['gravy']:>6} "
          f"{c['max19']:>6} {c['cf']:>5} {c['wy']:>5} {c['novelty']:>8}")

# novelty of the 5 RFD4 picks already in v6, for calibration
print("\nNovelty of RFD4 designs already selected (for calibration):")
sel = ["c3_glp1r_ecd_172","c3_glp1r_ecd_171","c3_glp1r_ecd_29","c3_glp1r_ecd_12","c3_glp1r_ecd_151"]
byname = {r["design"]: r["sequence"] for r in pool_rows}
for nm in sel:
    s = byname[nm]
    others = [cs for cs in cur_seqs if cs != s]
    nov = round(1.0 - max(jaccard(s, cs) for cs in others), 3)
    print(f"  {nm:24} novelty={nov}")
