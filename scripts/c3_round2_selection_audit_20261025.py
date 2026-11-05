#!/usr/bin/env python3
"""Independent audit of the round-2 24-design selection against Kimi's pre-registered rules.

Read-only. Does not import the selecting script. Re-derives from the raw selection,
MPNN and clustering artifacts:
  * exactly 24 designs
  * every selected sequence exists verbatim in the MPNN output (no invented sequences)
  * each selected name's backbone matches the MPNN record
  * <= 2 designs per cluster
  * >= 8 distinct clusters
  * all 24 sequences are unique
  * refold gate (mean pLDDT >= 80, frac>=70 >= 0.90, RMSD <= 3.0) holds for every selected one
Exit 0 = all pass, 1 = violations.
"""
import json, pathlib, sys
from collections import Counter

ROOT = pathlib.Path(__file__).resolve().parents[1]
R2 = ROOT / "results" / "c3_round2_111_20261025"
SEL = R2 / "selected24_filtered_20261025.json"
MPNN = R2 / "mpnn_sequences_20261025.json"
CLUSTERS = R2 / "clusters_20261025.json"
REFOLD = R2 / "refold_checks_20261025.json"


def main():
    sel = json.load(open(SEL))
    mpnn = json.load(open(MPNN))
    clu = json.load(open(CLUSTERS))
    refold = json.load(open(REFOLD))
    errs, info = [], []

    if len(sel) != 24:
        errs.append(f"selection has {len(sel)} designs, expected exactly 24")

    # MPNN records may be a list or a dict keyed by name
    def norm(x):
        if isinstance(x, dict):
            return {k: v for k, v in x.items() if isinstance(v, dict)}
        return {r.get("name"): r for r in x if isinstance(r, dict)}
    # MPNN records are a list of {backbone, sample, seq, len}. sample=0 is the NATIVE sequence;
    # the designed samples are 1 and 2 and the screen names them "<backbone>_s<sample>".
    # (Deriving s<sample+1> is an off-by-one that silently shifts every design by one sample.)
    recs = mpnn if isinstance(mpnn, list) else list(mpnn.values())
    mp = {}
    for v in recs:
        if not isinstance(v, dict):
            continue
        s_ = v.get("seq") or v.get("sequence")
        if not s_:
            continue
        sample = int(v.get("sample", 0))
        if sample == 0:
            continue  # native, not a design
        nm = v.get("name") or f"{v.get('backbone')}_s{sample}"
        mp[nm] = dict(v, sequence=s_)
    by_seq = {}
    for k, v in mp.items():
        by_seq.setdefault(v["sequence"], []).append(k)

    names = [d["name"] for d in sel]
    if len(set(names)) != len(names):
        errs.append("duplicate design names in selection")
    seqs = [d["sequence"] for d in sel]
    if len(set(seqs)) != len(seqs):
        errs.append("duplicate sequences in selection")

    for d in sel:
        n, s = d["name"], d["sequence"]
        if s not in by_seq:
            errs.append(f"{n}: sequence not found verbatim in MPNN output")
            continue
        owners = by_seq[s]
        if n not in owners:
            info.append(f"{n}: sequence also owned by {owners} (identical sequence in MPNN)")
        rec = mp.get(n)
        if rec and rec.get("backbone") and rec["backbone"] != d.get("backbone"):
            errs.append(f"{n}: backbone {d.get('backbone')} != MPNN record {rec['backbone']}")

    # cluster rules
    cluster_of = clu.get("cluster_of", {})
    clusters = clu.get("clusters", {})
    def cluster_for(backbone):
        if backbone in cluster_of:
            return cluster_of[backbone]
        for cid, members in clusters.items():
            if backbone in members:
                return cid
        return None
    assigned = [cluster_for(d["backbone"]) for d in sel]
    if any(a is None for a in assigned):
        errs.append(f"{sum(a is None for a in assigned)} designs have no cluster assignment")
    cnt = Counter(a for a in assigned if a is not None)
    over = {c: n for c, n in cnt.items() if n > 2}
    if over:
        errs.append(f"more than 2 designs per cluster: {over}")
    if len(cnt) < 8:
        errs.append(f"only {len(cnt)} distinct clusters, need >= 8")
    info.append(f"clusters used: {len(cnt)}; max per cluster: {max(cnt.values()) if cnt else 0}")

    # refold gate
    def refold_for(name):
        r = refold.get(name)
        if r is None:
            # controls / alternate keys
            r = next((v for k, v in refold.items() if k.startswith(name)), None)
        return r
    missing = 0
    for d in sel:
        r = refold_for(d["name"])
        if not isinstance(r, dict):
            missing += 1
            continue
        pl = r.get("refold_mean_plddt")
        f70 = r.get("refold_frac_residues_plddt_ge70", r.get("frac70"))
        rms = r.get("ca_rmsd_vs_designed_backbone",
                    r.get("ca_rmsd_vs_af2m_binder", r.get("rmsd")))
        if pl is None or pl < 80:
            errs.append(f"{d['name']}: refold pLDDT {pl} < 80")
        if f70 is None or f70 < 0.90:
            errs.append(f"{d['name']}: refold frac>=70 {f70} < 0.90")
        if rms is None or rms > 3.0:
            errs.append(f"{d['name']}: refold RMSD {rms} > 3.0")
    if missing:
        errs.append(f"{missing} selected designs have no refold record")

    for i in info:
        print("info ", i)
    for e in errs:
        print("FAIL ", e)
    print(f"\n{'PASS' if not errs else 'FAIL'} — 24-selection audit: {len(errs)} violation(s)")
    return 0 if not errs else 1


if __name__ == "__main__":
    sys.exit(main())
