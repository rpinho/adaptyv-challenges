#!/usr/bin/env python3
"""Compare AF2M scores produced on RunPod A40 against the same designs scored on Modal.

Reads the Modal table and a pod output root (dir of <name>/scores.json) and prints per-design
deltas plus the verdict rule the C3 gate actually uses (iPTM floor 0.850). Read-only.
"""
import argparse, json, pathlib, sys

FLOOR = 0.850


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--modal", default="results/c3_screen_af2m_scores_20261024.json")
    ap.add_argument("--pod", required=True, help="dir containing <name>/scores.json")
    ap.add_argument("--json-out", default="")
    a = ap.parse_args()

    modal = {r["name"]: r for r in json.load(open(a.modal))}
    rows, fails = [], 0
    for sp in sorted(pathlib.Path(a.pod).glob("*/scores.json")):
        p = json.load(open(sp))
        m = modal.get(p["name"])
        if not m:
            print(f"WARN {p['name']} not in the Modal table; skipped")
            continue
        di = p["iptm"] - m["iptm"]
        dp = p["ptm"] - m["ptm"]
        dl = p["mean_plddt"] - m["mean_plddt"]
        modal_pass, pod_pass = m["iptm"] >= FLOOR, p["iptm"] >= FLOOR
        flip = modal_pass != pod_pass
        fails += flip
        rows.append(dict(name=p["name"], modal_iptm=m["iptm"], pod_iptm=p["iptm"], d_iptm=round(di, 4),
                         modal_ptm=m["ptm"], pod_ptm=p["ptm"], d_ptm=round(dp, 4),
                         modal_plddt=round(m["mean_plddt"], 2), pod_plddt=round(p["mean_plddt"], 2),
                         d_plddt=round(dl, 2), model=p.get("model"),
                         wall_s=p.get("subprocess_wall_s"), verdict_flip=flip))
        print(f"{p['name']:26s} iPTM {m['iptm']:.3f} -> {p['iptm']:.3f} ({di:+.3f})  "
              f"pTM {m['ptm']:.3f} -> {p['ptm']:.3f} ({dp:+.3f})  "
              f"pLDDT {m['mean_plddt']:.2f} -> {p['mean_plddt']:.2f} ({dl:+.2f})  "
              f"{'MODEL-PICK' if p.get('model') else ''}  {'VERDICT FLIP' if flip else ''}")

    n = len(rows)
    exact = sum(1 for r in rows if abs(r["d_iptm"]) < 1e-9)
    print(f"\nsummary: n={n} iptm_exact={exact}/{n} verdict_flips={fails}/{n} "
          f"max|d_iptm|={max((abs(r['d_iptm']) for r in rows), default=0):.4f} "
          f"max|d_ptm|={max((abs(r['d_ptm']) for r in rows), default=0):.4f}")
    ok = fails == 0
    print("PORT ACCEPTED (no verdict flips at iPTM>=" + f"{FLOOR}" + ")" if ok
          else "PORT NOT ACCEPTED (verdict changes)")
    if a.json_out:
        pathlib.Path(a.json_out).write_text(json.dumps({"floor": FLOOR, "rows": rows,
                                                        "verdict_flips": fails,
                                                        "accepted": ok}, indent=2))
    return 0 if ok else 3


if __name__ == "__main__":
    sys.exit(main())
