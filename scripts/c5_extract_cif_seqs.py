import json, urllib.request, os
SC = os.environ.get("SCRATCHPAD", ".")
key = open(os.path.expanduser("~/.config/japanfold/key")).read().strip()
base = "https://api.japanfold.aiand.com"
AA3 = {"ALA":"A","ARG":"R","ASN":"N","ASP":"D","CYS":"C","GLN":"Q","GLU":"E","GLY":"G",
"HIS":"H","ILE":"I","LEU":"L","LYS":"K","MET":"M","PHE":"F","PRO":"P","SER":"S",
"THR":"T","TRP":"W","TYR":"Y","VAL":"V","MSE":"M"}
def fetch(p, raw=False):
    r = urllib.request.Request(base+p, headers={"Authorization":"Bearer "+key})
    with urllib.request.urlopen(r, timeout=180) as f:
        return f.read().decode("utf8","replace") if raw else json.load(f)

def chains_from_cif(txt):
    lines = txt.splitlines()
    # locate the single _atom_site loop header block directly; other loop_ blocks are ignored
    hdr = [i for i, l in enumerate(lines) if l.strip().startswith("_atom_site.")]
    if not hdr: return {}
    cols = {lines[i].strip(): k for k, i in enumerate(hdr)}
    ci = cols.get("_atom_site.label_asym_id", cols.get("_atom_site.auth_asym_id"))
    ri = cols.get("_atom_site.label_comp_id")
    si = cols.get("_atom_site.label_seq_id", cols.get("_atom_site.auth_seq_id"))
    ai = cols.get("_atom_site.label_atom_id")
    need = max(x for x in (ci, ri, si, ai) if x is not None)
    out, seen = {}, set()
    for i in range(hdr[-1] + 1, len(lines)):
        l = lines[i]
        if not l.strip() or l.startswith(("loop_", "#", "data_", "_")): break
        f = l.split()
        if len(f) <= need: continue
        if f[ai] != "CA": continue
        k = (f[ci], f[si])
        if k in seen: continue
        seen.add(k)
        out.setdefault(f[ci], []).append(AA3.get(f[ri].upper(), "X"))
    return {c: "".join(v) for c, v in out.items()}

HLA12, B2M11 = "MAVMAPRTLLLL"[:12], "MIQRTPKIQVY"[:11]
jobs = json.load(open("/Users/ricardo/dev/adaptyv-c4/scratchpad/r114_rfd4_jobs.json"))
rows = []
for j in jobs:
    res = fetch("/v1/jobs/%s/results" % j["id"])
    for d in res.get("designs", []):
        cif = fetch("/v1/jobs/%s/artifacts/%s" % (j["id"], d["structure"]), raw=True)
        ch = chains_from_cif(cif)
        cand = [(c, s) for c, s in ch.items()
                if len(s) >= 15 and s[:12] != HLA12 and s[:11] != B2M11]
        cand.sort(key=lambda t: -len(t[1]))
        lens = {c: len(s) for c, s in ch.items()}
        if not cand:
            print("WARN %-16s %-9s chains=%s" % (j["tag"], d["id"], lens)); continue
        c, s = cand[0]
        name = "c5_r114_%s_%s" % (j["tag"], d["id"].replace("design_", "d"))
        rows.append({"name": name, "job": j["id"], "tag": j["tag"], "design": d["id"],
                     "chain": c, "len": len(s), "seq": s, "chains": lens})
        print("%-30s chain=%s len=%3d chains=%s" % (name, c, len(s), lens))
json.dump(rows, open(SC + "/rfd4_seqs.json", "w"), indent=1)
print("\nextracted %d designs" % len(rows))
