---
name: eda-mix
description: EDA view: within each group of dimension D1, how does dimension D2 split — 100%-stacked horizontal bars (composition). Use for 'of each age band, what share is in each score band', segment composition, cross-tabs of two categoricals. (Not 'share of wallet'.)
user-invocable: true
---

# /eda-mix

**Question:** within each group of D1, how does D2 split (each row sums to 100%).
**Call:** `mix(df, dim, by, by_k=5, entity=None)`.
**Inputs:** two categoricals; D2 low-cardinality (top-5 + Else). Rows sorted by group size.
**Read:** pick a row, read across; compare rows — a flat picture means D1 and D2 are independent (say so, that is a finding too).
**Chart rules:** HORIZONTAL 100% stacks; BLACK = largest D2 value then the orange ramp, Else palest; in-bar % labels ≥6%; n= in ticks.
**Stop:** ≤ 3 pairs, chosen on purpose. Independence → say it and move on.

Shared rules: `/eda` skill (guardrails, inputs, the vocabulary). Code: `src/monaco/eda.py`.
Returns `View(fig, table, note)` — always print the table and the note under the chart. Read the PNG before calling it done.

## In-place mode (live): `/eda-mix <notebook.ipynb>`
When the user passes a notebook path, do NOT rebuild anything and do NOT write PNG files.
1. If the frame is unfamiliar, run `monaco-nb <nb> --columns` (setup only, saves nothing) and read the dtypes.
2. Ask ONE question — which two dimensions (D1 rows, D2 split) — proposing a default from the columns, and end it with "is this right?". Wait for the answer.
3. Run `monaco-nb <nb> mix --dim <D1> --by <D2> [--entity <E>]`. It upserts the section tagged `mix:<dim|entity>` (same id = replaced in place, so a re-run with a tweak
   does not duplicate), executes only the setup cell and that cell in a fresh kernel, writes the notebook, and prints the table.
4. Paste the printed table and note verbatim; the chart is in the notebook output. Then stop and let the user narrate.
If the notebook does not exist yet, add `--setup-file <py that defines df>` once; later calls reuse the notebook's setup cell.
Different question, same view → pass `--id mix:<name>` to keep both sections. Code: `src/monaco/nbx.py`.
