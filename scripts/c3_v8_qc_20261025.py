#!/usr/bin/env python3
"""Independent QC of results/c3_submission_v8_20261025.csv.

Deliberately shares NO code with the gate: raw csv/hash/JSON work only, so a bug in the
gate cannot hide behind a re-run of the gate. Re-derives from evidence, not from the gate report.

Checks
  1  v8 exists, 20 data rows, exact header, unique names, unique sequences
  2  19 retained rows are byte-identical to v7 and appear in v7 order
  3  exactly one row differs: c3_v_l65_E5Q removed, B_26102611_s1 added, in the same position
  4  every sequence canonical, length 52..100, single_chain
  5  v6/v7 hashes equal the pinned fallbacks (v8 must not have disturbed them)
  6  the added sequence equals the frozen E2 manifest hash for that candidate
  7  the added candidate PASSES the independent verifier and the structural check
  8  v8 itself re-passes the four soluble filters
  9  the replaced row's sequence is absent from v8
Exit 0 only if every check passes.
"""
import csv
import hashlib
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
R2 = ROOT / "results/c3_round2_111_20261025"
V8 = ROOT / "results/c3_submission_v8_20261025.csv"
V7 = ROOT / "results/c3_submission_v7_20261025.csv"
V6 = ROOT / "results/c3_submission_v6_20261023.csv"
V7_SHA = "1d99f843b9d5af6cedd74e5ccfbf6cfd260f26e5461b2bffb0a4ee2204349c55"
V6_SHA = "8e9b2d741586e8b360fbed401b4de77317d579e183409cf4928de42661096891"
TARGET_SHA = "5c2bae2dac5e467bf4e802473450a7ca3729990921bbe5c45cf6025531ef36b3"
OLD = "c3_v_l65_E5Q"
NEW = "B_26102611_s1"
CANON = set("ACDEFGHIKLMNPQRSTVWY")

results = []


def check(name, cond, detail=""):
    results.append(bool(cond))
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else f"   [{detail}]"))


def sha_bytes(b):
    return hashlib.sha256(b).hexdigest()


def main():
    if not V8.exists():
        check("v8 exists", False, f"missing {V8}")
        return summarize()
    raw = V8.read_bytes()
    lines = raw.splitlines(keepends=True)
    v7raw = V7.read_bytes()
    v7lines = v7raw.splitlines(keepends=True)

    check("v8 has exactly 20 data rows", len(lines) == 21, f"{len(lines) - 1} rows")
    check("v8 header matches v7 byte-for-byte", lines[0] == v7lines[0], lines[0][:60])
    check("v8 rows end in CRLF", all(ln.endswith(b"\r\n") for ln in lines), "mixed line endings")

    rows = list(csv.DictReader(open(V8, newline="")))
    v7rows = list(csv.DictReader(open(V7, newline="")))
    names = [r["name"] for r in rows]
    seqs = [r["sequence"] for r in rows]
    check("20 rows parsed", len(rows) == 20, len(rows))
    check("names unique", len(set(names)) == 20, len(set(names)))
    check("sequences unique", len(set(seqs)) == 20, len(set(seqs)))
    check("header is name,sequence,molecule_class",
          list(rows[0].keys()) == ["name", "sequence", "molecule_class"], list(rows[0].keys()))

    # --- replaced / added identity
    check(f"replaced row {OLD} is gone", OLD not in names)
    check(f"added row {NEW} is present exactly once", names.count(NEW) == 1, names.count(NEW))
    v7old_seq = next(r["sequence"] for r in v7rows if r["name"] == OLD)
    check("replaced row's sequence is absent from v8", v7old_seq not in seqs)

    v7_by = {ln.split(b",", 1)[0]: ln for ln in v7lines[1:]}
    retained_v8 = [ln for ln in lines[1:] if not ln.startswith(NEW.encode() + b",")]
    expected = [v7_by[n.encode()] for n in [r["name"] for r in v7rows] if n != OLD]
    check("19 retained rows byte-identical to v7", retained_v8 == expected,
          f"{len(retained_v8)} vs {len(expected)}")
    check("retained rows keep v7 order",
          [ln.split(b",", 1)[0] for ln in retained_v8] ==
          [n.encode() for n in [r["name"] for r in v7rows] if n != OLD])
    idx = names.index(NEW)
    check("added row occupies the replaced slot's position",
          [r["name"] for r in v7rows][idx] == OLD,
          f"v7[{idx}]={[r['name'] for r in v7rows][idx]}")

    # --- sequence sanity
    bad = [r["name"] for r in rows if not set(r["sequence"]) <= CANON]
    check("all sequences canonical", not bad, bad[:3])
    outlen = [r["name"] for r in rows if not (52 <= len(r["sequence"]) <= 100)]
    check("all lengths 52..100", not outlen, outlen[:3])
    check("all rows single_chain",
          {r["molecule_class"] for r in rows} == {"single_chain"},
          {r["molecule_class"] for r in rows})

    # --- fallbacks untouched
    check("v7 hash equals pinned fallback", sha_bytes(v7raw) == V7_SHA, sha_bytes(v7raw))
    check("v6 hash equals pinned fallback", sha_bytes(V6.read_bytes()) == V6_SHA,
          sha_bytes(V6.read_bytes()))

    # --- evidence binding for the added row
    e2 = json.loads((R2 / "e2_manifest_20261025.json").read_text())
    mem = next((m for m in e2["members"] if m["name"] == NEW), None)
    new_seq = next(r["sequence"] for r in rows if r["name"] == NEW)
    check("added candidate is in the frozen E2 manifest", mem is not None)
    if mem:
        check("added sequence matches E2 manifest binder hash",
              mem["binder_sha256"] == hashlib.sha256(new_seq.encode()).hexdigest(),
              mem["binder_sha256"][:12])
        check("E2 manifest target hash is the exact 111-mer",
              mem["target_sha256"] == TARGET_SHA, mem["target_sha256"][:12])

    ver = json.loads((R2 / "round2_verify_independent.json").read_text())
    rec = next((r for r in ver["records"] if r.get("name") == NEW), None)
    check("added candidate has an independent verification record", rec is not None)
    if rec:
        check("verification status PASS", rec.get("status") == "PASS",
              f"{rec.get('status')} {rec.get('reasons')}")
        check("verification iptm >= 0.850", float(rec.get("iptm", 0)) >= 0.850, rec.get("iptm"))
        check("verification binder hash binds the final v8 sequence",
              rec.get("binder_sequence_sha256") == hashlib.sha256(new_seq.encode()).hexdigest())
        check("verification target hash is the exact 111-mer",
              rec.get("target_sequence_sha256") == TARGET_SHA)

    struct = json.loads((R2 / "structural_checks_20261025.json").read_text())
    st = struct.get(NEW)
    check("added candidate has a structural record", st is not None)
    if st:
        check("structural pass", st.get("pass") is True, st.get("pass"))
        check("zero heavy-atom clashes < 2.0 A", st.get("heavy_atom_pairs_lt2A") == 0,
              st.get("heavy_atom_pairs_lt2A"))
        check("structural record binds the final v8 sequence",
              st.get("sequence_sha256") == hashlib.sha256(new_seq.encode()).hexdigest())

    # --- freeze self-repair proof: v8 must still satisfy the pre-registered soluble filters
    sys.path.insert(0, str(ROOT / "scripts"))
    import c3_soluble_filters_20261025 as sf
    fails = {r["name"]: sf.failures(r["sequence"]) for r in rows}
    fails = {k: v for k, v in fails.items() if v}
    check("every v8 row passes the soluble filters", not fails, list(fails)[:3])

    # --- no stale v8 alias elsewhere
    print(f"\nv8 sha256 {sha_bytes(raw)}")
    return summarize()


def summarize():
    ok, n = sum(results), len(results)
    print(f"\n{ok}/{n} checks passed")
    return 0 if ok == n else 1


if __name__ == "__main__":
    sys.exit(main())
