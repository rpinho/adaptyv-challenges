#!/usr/bin/env python3
"""Score an arbitrary list of binder sequences against the G12D / WT pMHC pair.

Phases 4-6 of c5_round.py, split out so designs that did not come from BoltzGen can be
scored by the same path. Written 2026-11-07 for the RFD4-Proteina designs, whose results
carry no `designed_sequence` field at all (only a structure CIF per design), so the
sequences have to be read out of the structures first and then arrive here as JSON.

Input: a JSON list of {"name": str, "seq": str} (extra keys are carried through).
Output: <outdir>/<tag>_sel_jobs.json, <outdir>/<tag>_seqs.csv, and a ranked report.
"""
import argparse, csv, json, os, sys, time, urllib.error, urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from c5_target import MAX_LEN, MIN_LEN, TARGETS, fasta, verify

BASE = "https://api.japanfold.aiand.com"

_bad = verify()
if _bad:
    sys.exit("c5_target.py failed verification, refusing to score:\n  " + "\n  ".join(_bad))


def get_key():
    return open(os.path.expanduser("~/.config/japanfold/key")).read().strip()


def api(key, path, data=None, retries=3):
    body = json.dumps(data).encode() if data is not None else None
    hdr = {"Authorization": "Bearer " + key}
    if body:
        hdr["Content-Type"] = "application/json"
    for attempt in range(retries):
        try:
            r = urllib.request.Request(BASE + path, data=body, headers=hdr)
            with urllib.request.urlopen(r, timeout=120) as f:
                return json.load(f)
        except urllib.error.HTTPError as e:
            if e.code < 500 or attempt == retries - 1:
                print("  HTTP %s %s: %s" % (e.code, path, e.read()[:200].decode("utf8", "replace")))
                return None
        except Exception as e:
            if attempt == retries - 1:
                print("  ERR %s: %r" % (path, e))
                return None
        time.sleep(5 * (attempt + 1))
    return None


def main():
    ap = argparse.ArgumentParser(description="Score binder sequences on the G12D/WT pair")
    ap.add_argument("--seqs", required=True, help="JSON list of {name, seq}")
    ap.add_argument("--tag", required=True, help="output basename, e.g. r114_rfd4")
    ap.add_argument("--outdir", default="results/japanfold_pilot")
    ap.add_argument("--model", default="opendde-abag")
    ap.add_argument("--min-len", type=int, default=MIN_LEN)
    ap.add_argument("--max-len", type=int, default=MAX_LEN,
                    help="skip designs above the official submission cap")
    ap.add_argument("--targets", default="g12d,wt",
                    help="comma-separated subset of %s; peptide_free is ranking step 2"
                         % ",".join(TARGETS))
    ap.add_argument("--polls", type=int, default=60)
    args = ap.parse_args()

    targets = [t.strip() for t in args.targets.split(",") if t.strip()]
    bad = [t for t in targets if t not in TARGETS]
    if bad:
        sys.exit("unknown target(s): %s" % ", ".join(bad))

    key = get_key()
    os.makedirs(args.outdir, exist_ok=True)
    allseqs = json.load(open(args.seqs))
    designs = [d for d in allseqs
               if d.get("seq") and args.min_len <= len(d["seq"]) <= args.max_len]
    skipped = len(allseqs) - len(designs)
    if not designs:
        sys.exit("no eligible sequences in %s" % args.seqs)
    if skipped:
        print("skipped %d design(s) outside %d-%daa" % (skipped, args.min_len, args.max_len))
    print("=== %s: %d designs x %d targets = %d scoring jobs ==="
          % (args.tag, len(designs), len(targets), len(designs) * len(targets)))

    with open("%s/%s_seqs.csv" % (args.outdir, args.tag), "w") as f:
        w = csv.writer(f)
        w.writerow(["name", "sequence", "molecule_class"])
        for d in designs:
            w.writerow([d["name"], d["seq"], "single_chain"])

    out = "%s/%s_sel_jobs.json" % (args.outdir, args.tag)
    tracker = []
    for i, d in enumerate(designs):
        rec = dict(d)
        rec["length"] = len(d["seq"])
        for t in targets:
            r = api(key, "/v1/predictions", {"model": args.model,
                                             "name": "%s_%s" % (d["name"], t),
                                             "input": fasta(d["seq"], t)})
            rec[t + "_job_id"] = (r or {}).get("id", "")
            rec[t + "_conf"] = 0.0
        rec["delta"] = 0.0
        tracker.append(rec)
        if (i + 1) % 10 == 0:
            print("  submitted %d/%d" % (i + 1, len(designs)))
    json.dump(tracker, open(out, "w"), indent=2)

    def complete(t):
        return all(t.get(k + "_conf", 0) > 0 for k in targets)

    print("=== %s: harvesting ===" % args.tag)
    for poll in range(args.polls):
        done = 0
        for t in tracker:
            if complete(t):
                done += 1
                continue
            for k in targets:
                jid = t.get(k + "_job_id", "")
                if not jid or t.get(k + "_conf", 0) > 0:
                    continue
                res = api(key, "/v1/jobs/%s/results" % jid)
                if res and res.get("ready") and res.get("rows"):
                    t[k + "_conf"] = float(res["rows"][0].get("confidence_score") or 0)
            if complete(t):
                done += 1
        for t in tracker:
            if t.get("g12d_conf", 0) > 0 and t.get("wt_conf", 0) > 0:
                t["delta"] = t["g12d_conf"] - t["wt_conf"]
            if t.get("g12d_conf", 0) > 0 and t.get("peptide_free_conf", 0) > 0:
                # ranking step 2: a binder that reads the groove or B2M scores high here too
                t["delta_pf"] = t["g12d_conf"] - t["peptide_free_conf"]
        print("  poll %d: %d/%d scored" % (poll + 1, done, len(tracker)))
        json.dump(tracker, open(out, "w"), indent=2)
        if done >= len(tracker):
            break
        time.sleep(45)

    scored = [t for t in tracker if complete(t)]
    print("\n=== %s results (target: official A*11:01) ===" % args.tag)
    print("scored: %d/%d" % (len(scored), len(tracker)))
    if not scored:
        print("  nothing scored — check the job ids in %s" % out)
        return
    has_pf = "peptide_free" in targets
    key_fn = (lambda x: -min(x.get("delta", -9), x.get("delta_pf", -9))) if has_pf \
        else (lambda x: -x.get("delta", -9))
    hdr = "  %-34s %8s %7s %7s" % ("design", "delta", "g12d", "wt")
    print(hdr + ("%10s %8s" % ("pep-free", "delta_pf") if has_pf else "") + "   len")
    for t in sorted(scored, key=key_fn)[:15]:
        line = "  %-34s %+8.3f %7.3f %7.3f" % (t["name"], t.get("delta", 0),
                                               t.get("g12d_conf", 0), t.get("wt_conf", 0))
        if has_pf:
            line += "%10.3f %+8.3f" % (t.get("peptide_free_conf", 0), t.get("delta_pf", 0))
        print(line + "  %4d" % t["length"])
    print("\nwrote %s" % out)


if __name__ == "__main__":
    main()
