#!/usr/bin/env python3
"""READ-ONLY: does an alternate AF2 model pick change the gate verdict?

For each of the 16 R3 designs with recovered five-model sets, recompute the pipeline's
own structural metrics on ALL FIVE archived models and ask:
  - does rank-001 clash / fail?
  - does any non-rank-001 model pass the structural gate?
  - how much does the metric spread across models?

It imports the frozen verifier's own primitives (parse_pdb/seq_of/contacts/chain_integrity,
CLASH_A, GROOVE_CONTACT_A, FLOOR) so the rule cannot drift. It writes a report only:
no CSV, no gate change, no admission, no promotion.
"""
import csv, json, pathlib, sys, hashlib, re

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import c3_round2_verify_20261025 as V  # frozen verifier primitives

REC = ROOT / "results/c3_r3_20261025/five_model_recovery"
INPUT = ROOT / "results/c3_r3_20261025/screen_input_20261025.csv"
GROOVE = ROOT / "results/c3_groove_reference_20261025.json"
OUT = ROOT / "results/c3_five_model_pick_20261025"
TARGET_SHA = V.TARGET_SHA

def find_models(d):
    """Map rank -> (score_json, pdb) using ColabFold's filenames."""
    out = {}
    for p in sorted(d.glob("*scores_rank_*_alphafold2_multimer_v3_*.json")):
        m = re.search(r"scores_rank_(\d+)_", p.name)
        if not m: continue
        rank = int(m.group(1))
        # matching pdb shares the prefix up to _scores_ / _unrelaxed_
        stem = p.name.split("_scores_rank_")[0]
        cands = sorted(d.glob(f"{stem}_unrelaxed_rank_{rank:03d}_*.pdb"))
        if not cands:
            cands = sorted(d.glob(f"{stem}_rank_{rank:03d}_*.pdb"))
        out[rank] = (p, cands[0] if cands else None)
    return out

def metric_one(name, binder_expect, target_expect, scorep, pdbp, groove_set):
    r = {"name": name, "score_file": scorep.name if scorep else None,
         "pdb_file": pdbp.name if pdbp else None}
    if scorep is None or pdbp is None:
        r["status"] = "incomplete"; return r
    try:
        s = json.loads(scorep.read_text())
    except Exception as e:
        r["status"] = "bad_evidence"; r["error"] = str(e); return r
    r["iptm"] = s.get("iptm"); r["ptm"] = s.get("ptm")
    chains = V.parse_pdb(pdbp)
    if len(chains) != 2:
        r["status"] = "fail"; r["reasons"] = [f"expected 2 chains, found {sorted(chains)}"]; return r
    by_seq = {c: V.seq_of(chains[c]) for c in chains}
    bids = [c for c,q in by_seq.items() if q == binder_expect]
    tids = [c for c,q in by_seq.items() if q == target_expect]
    if len(bids)!=1 or len(tids)!=1 or bids[0]==tids[0]:
        r["status"] = "fail"; r["reasons"] = ["chain assignment ambiguous"]; return r
    binder, target = chains[bids[0]], chains[tids[0]]
    r["binder_len"] = len(binder); r["target_len"] = len(target)
    r["sequence_bound"] = (V.seq_of(binder)==binder_expect and V.seq_of(target)==target_expect)
    r["target_sha_ok"] = V.sha(V.seq_of(target)).startswith(TARGET_SHA)
    bf = [b for res in binder for b in res["bfac"].values()]
    r["binder_mean_plddt"] = round(sum(bf)/len(bf),2) if bf else 0.0
    ncon, pairs = V.contacts(binder, target, V.GROOVE_CONTACT_A)
    hits = sorted({ti+1 for _,ti in pairs} & groove_set)
    nclash, cpairs = V.contacts(binder, target, V.CLASH_A)
    r.update({"contacts_le5A": ncon, "groove_residues_contacted": len(hits),
              "clashes_lt2A": nclash, "chain_integrity_problems": V.chain_integrity(binder)[:3]})
    why = []
    if not r["sequence_bound"]: why.append("sequence mismatch")
    if not r["target_sha_ok"]: why.append("target sha mismatch")
    if r["binder_mean_plddt"] < V.BINDER_PLDDT_MIN: why.append(f"pLDDT {r['binder_mean_plddt']}")
    if len(hits) < V.MIN_GROOVE: why.append(f"groove {len(hits)}")
    if ncon < V.MIN_CONTACTS: why.append(f"contacts {ncon}")
    if nclash: why.append(f"clashes {nclash}")
    if r["chain_integrity_problems"]: why.append("chain integrity")
    # structural-only verdict; iPTM reported separately so both questions are visible
    r["structural_pass"] = not why
    r["structural_reasons"] = why
    r["iptm_ok"] = isinstance(r["iptm"],(int,float)) and r["iptm"] >= V.FLOOR
    r["all_structural_gates_pass"] = bool(r["structural_pass"] and r["iptm_ok"])
    return r

def main():
    inp = {r["name"]: r for r in csv.DictReader(open(INPUT))}
    groove_set = set(json.loads(GROOVE.read_text())["groove_residues_1based"])
    inv = json.loads((REC/"inventory_20261025.json").read_text())["designs"]
    rows = []
    for name, meta in sorted(inv.items()):
        d = REC/meta["pod"]/name
        models = find_models(d)
        row = inp.get(name)
        if not row:
            rows.append({"name": name, "status": "no_input_row"}); continue
        per = [metric_one(name, row["binder"].strip(), row["target"].strip(),
                          models.get(k,(None,None))[0], models.get(k,(None,None))[1], groove_set)
               for k in sorted(models)]
        r1 = next((m for m in per if m["score_file"] and "rank_001" in m["score_file"]), None)
        rescued = [m for m in per if m.get("all_structural_gates_pass") and m is not r1]
        rows.append({"name": name, "n_models": len(per), "rank1": r1, "per_model": per,
                     "rank1_gate_pass": bool(r1 and r1.get("all_structural_gates_pass")),
                     "rescued_by_alternate_model": bool(rescued),
                     "rescuing_ranks": [m["score_file"] for m in rescued]})
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT/"per_model_metrics.json").write_text(json.dumps(rows, indent=1))
    # summary
    n = len([r for r in rows if r.get("n_models")])
    r1pass = [r for r in rows if r.get("rank1_gate_pass")]
    rescued = [r for r in rows if r.get("rescued_by_alternate_model")]
    print(f"designs analysed: {n}")
    print(f"rank-001 all-gates PASS: {len(r1pass)}/{n}")
    print(f"rescued by an alternate model pick: {len(rescued)}/{n}")
    for r in rows:
        r1 = r.get("rank1") or {}
        spread = [m.get("iptm") for m in r.get("per_model",[]) if isinstance(m.get("iptm"),(int,float))]
        print(f"  {r['name']:<30} rank1 iPTM={r1.get('iptm')} clash={r1.get('clashes_lt2A')} "
              f"structPASS={r1.get('structural_pass')} allPASS={r.get('rank1_gate_pass')} "
              f"rescued={r.get('rescued_by_alternate_model')} iPTMspread={min(spread) if spread else None}-{max(spread) if spread else None}")
    summary = {"designs": n, "rank1_all_gates_pass": len(r1pass),
               "rescued_by_alternate_model": len(rescued),
               "rescuing": [r["name"] for r in rescued]}
    (OUT/"summary.json").write_text(json.dumps(summary, indent=1))

if __name__ == "__main__":
    main()
