#!/usr/bin/env python3
"""Negative controls for scripts/c3_v8_qc_20261025.py.

The QC script must FAIL on each of these corruptions, otherwise it proves nothing.
Each case copies the whole project evidence tree reference set into a temp "project",
corrupts exactly one thing, and runs the QC against it.
"""
import pathlib
import shutil
import subprocess
import sys
import tempfile
import json

ROOT = pathlib.Path(__file__).resolve().parents[1]
QC = ROOT / "scripts/c3_v8_qc_20261025.py"
FILES = [
    "results/c3_submission_v8_20261025.csv",
    "results/c3_submission_v7_20261025.csv",
    "results/c3_submission_v6_20261023.csv",
]
R2FILES = [
    "e2_manifest_20261025.json",
    "round2_verify_independent.json",
    "structural_checks_20261025.json",
]
results = []


def case(name, cond, extra=""):
    results.append(bool(cond))
    print(("PASS " if cond else "FAIL ") + name + ("" if cond else f"  {extra}"))


def sandbox(tmp):
    t = pathlib.Path(tmp)
    (t / "results/c3_round2_111_20261025").mkdir(parents=True)
    (t / "scripts").mkdir()
    for f in FILES:
        shutil.copy(ROOT / f, t / f)
    for f in R2FILES:
        shutil.copy(ROOT / "results/c3_round2_111_20261025" / f,
                    t / "results/c3_round2_111_20261025" / f)
    shutil.copy(ROOT / "scripts/c3_soluble_filters_20261025.py", t / "scripts/")
    shutil.copy(QC, t / "scripts/")
    return t


def run(t):
    r = subprocess.run([sys.executable, str(t / "scripts" / QC.name)],
                       capture_output=True, text=True)
    return r.returncode, r.stdout + r.stderr


def v8line(t, name):
    p = t / FILES[0]
    lines = p.read_bytes().splitlines(keepends=True)
    for i, ln in enumerate(lines):
        if ln.startswith(name.encode() + b","):
            return p, lines, i
    raise SystemExit(f"{name} not found")


with tempfile.TemporaryDirectory() as tmp:
    t = sandbox(tmp)
    rc, out = run(t)
    case("CONTROL: pristine evidence passes QC (rc=0)", rc == 0, out[-500:])

with tempfile.TemporaryDirectory() as tmp:
    t = sandbox(tmp)
    p, lines, i = v8line(t, "B_26102611_s1")
    parts = lines[i].split(b",")
    parts[1] = parts[1][:-1] + b"A"        # one-residue change
    lines[i] = b",".join(parts)
    p.write_bytes(b"".join(lines))
    rc, out = run(t)
    case("CORRUPTED added sequence is caught", rc != 0 and "binder hash" in out, out[-400:])

with tempfile.TemporaryDirectory() as tmp:
    t = sandbox(tmp)
    p, lines, i = v8line(t, "c3_bc_l65_8f7b63")
    if i is not None:
        lines[i] = lines[i].replace(b"c3_bc_l65_8f7b63", b"c3_bc_l65_8f7b6X")
    p.write_bytes(b"".join(lines))
    rc, out = run(t)
    case("RENAMED retained row is caught", rc != 0, out[-400:])

with tempfile.TemporaryDirectory() as tmp:
    t = sandbox(tmp)
    p = t / FILES[0]
    lines = p.read_bytes().splitlines(keepends=True)
    lines[-1] = lines[-1].replace(b"\r\n", b"\n")
    p.write_bytes(b"".join(lines))
    rc, out = run(t)
    case("BROKEN CRLF is caught", rc != 0 and "CRLF" in out, out[-400:])

with tempfile.TemporaryDirectory() as tmp:
    t = sandbox(tmp)
    p = t / FILES[0]
    lines = p.read_bytes().splitlines(keepends=True)
    lines.append(lines[-1])                 # duplicate a row
    p.write_bytes(b"".join(lines))
    rc, out = run(t)
    case("DUPLICATED row is caught", rc != 0, out[-400:])

with tempfile.TemporaryDirectory() as tmp:
    t = sandbox(tmp)
    p = t / FILES[0]
    lines = p.read_bytes().splitlines(keepends=True)
    v7 = (t / FILES[1]).read_bytes().splitlines(keepends=True)
    old = next(ln for ln in v7 if ln.startswith(b"c3_v_l65_E5Q,"))
    lines = [ln for ln in lines if not ln.startswith(b"B_26102611_s1,")]
    lines.insert(10, lines[5])              # keep 20 rows but drop the real addition
    p.write_bytes(b"".join(lines))
    rc, out = run(t)
    case("MISSING added row is caught", rc != 0, out[-400:])

with tempfile.TemporaryDirectory() as tmp:
    t = sandbox(tmp)
    p = t / FILES[1]                        # tamper with the v7 fallback
    p.write_bytes(p.read_bytes() + b"\r\n")
    rc, out = run(t)
    case("TAMPERED v7 fallback is caught", rc != 0, out[-400:])

with tempfile.TemporaryDirectory() as tmp:
    t = sandbox(tmp)
    p = t / FILES[2]                        # tamper with the v6 fallback
    p.write_bytes(p.read_bytes() + b"\r\n")
    rc, out = run(t)
    case("TAMPERED v6 fallback is caught", rc != 0, out[-400:])

with tempfile.TemporaryDirectory() as tmp:
    t = sandbox(tmp)
    p = t / "results/c3_round2_111_20261025/structural_checks_20261025.json"
    d = json.loads(p.read_text())
    d["B_26102611_s1"]["heavy_atom_pairs_lt2A"] = 2
    p.write_text(json.dumps(d))
    rc, out = run(t)
    case("STRUCTURAL clash injected is caught", rc != 0, out[-400:])

with tempfile.TemporaryDirectory() as tmp:
    t = sandbox(tmp)
    p = t / "results/c3_round2_111_20261025/round2_verify_independent.json"
    d = json.loads(p.read_text())
    for r in d["records"]:
        if r.get("name") == "B_26102611_s1":
            r["status"] = "fail"
    p.write_text(json.dumps(d))
    rc, out = run(t)
    case("FAILED verification status is caught", rc != 0, out[-400:])

n, ok = len(results), sum(results)
print(f"\n{ok}/{n} QC fixtures behaved as specified")
sys.exit(0 if ok == n else 1)
