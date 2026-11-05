# C4 Boltz-port preflight — FAILS condition 1, so the $0.59 diagnostic does not run

Run 06:58 ET, CPU only, **$0 spent, no pod touched**. This is the preflight that Astra's tiebreak
requires before the bounded port diagnostic may start. It exists so the decision is made on evidence
instead of at 08:00 by whoever is awake.

## Astra's conditions (from `results/decisions/20261025-0650-c4-gpu-tiebreak.md`)
1. Both cached-MSA/pairing inputs must **exist**, carry **provenance** linking them to the compared
   runs, and **hash-match their archived manifests** — "newly hashing an unidentified file is
   insufficient".
2. Pinned software, checkpoint, chain mapping, extraction code, two recorded seeds; online MSA off.
3. Whole experiment frozen to fit the 60-minute / $0.59 cap.

## Measured
| check | result |
|---|---|
| `.a3m`/`.msa` files anywhere in the repo | **0** |
| MSA cache directories | **0** |
| Boltz result records: fields present | `name, sequence, iptm, n_elevated_complex` — **no MSA field, no MSA hash, no config hash** |
| Boltz confidence files: fields present | 11 confidence metrics — **no input provenance, no seed, no config** |
| archived C3 A3Ms (for contrast) | **160** (the C3 arm does archive them) |

**Verdict: condition 1 FAILS.** The Boltz C4 lane recorded neither its MSA inputs nor their hashes, so
a "paired cached-MSA swap" is not constructible from what exists. There is nothing to hash-match and
nothing to swap — exactly the case Astra said must abort.

## Consequence
- **No C4 GPU diagnostic runs.** Not because of the ceiling ($0.59 is trivial) but because the
  experiment cannot be built as specified. Spending the hour would test nothing.
- **C4 stays CPU-only / evidence-only today.** The pH-readout audit that both consultants ranked first
  is unaffected and can proceed for $0.
- **The port's real defect is now named**: it is not just "0.187 vs 0.03", it is that the C4 lane never
  recorded enough to diagnose a mismatch. Any future port must **archive MSA input + hash + config hash
  per run from the first invocation** — the C3 arm already does this, so the pattern exists in-repo.
- No candidate file, no promotion, no gate change, nothing submitted, nobody contacted.

## What this changes in the morning report
"Boltz port failed for an unknown reason" becomes "**the port failed and the lane never recorded its
MSA inputs, so the mismatch was undiagnosable by construction**; the fix is instrumentation, and it is
free to add before the next attempt."
