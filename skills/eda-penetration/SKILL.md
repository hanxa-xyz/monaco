---
name: eda-penetration
description: EDA view: of each group in a dimension, what % has a 0/1 flag — horizontal bars with the overall rate as a reference line. Use for 'what percent of X do Y', adoption/repeat/churn rates by segment. Rates within group; bars do not sum to 100%.
user-invocable: true
---

# /eda-penetration

**Question:** of each group in D, what share has flag F (0/1).
**Call:** `penetration(df, dim, flag, flag_label=..., entity=None|'entity_col')` (with entity, the flag is max over the entity's rows).
**Inputs:** a real 0/1 column (build it in derive_code if needed), one dim per call.
**Read:** it is a rate WITHIN the group; a high rate with a small N is a small share of all flagged units — pair with `/eda-distribution` for the 'of the total' side.
**Chart rules:** HORIZONTAL always; label `N split within group (penetration)`; value label `rate (k/n)`; GRAY dashed overall line; pale = n<15.
**Stop:** one per dimension. Do not turn a multi-valued column into many flags — that is `/eda-mix`.

Shared rules: `/eda` skill (guardrails, inputs, the vocabulary). Code: `src/monaco/eda.py`.
Returns `View(fig, table, note)` — always print the table and the note under the chart. Read the PNG before calling it done.

## In-place mode (live): `/eda-penetration <notebook.ipynb>`
When the user passes a notebook path, do NOT rebuild anything and do NOT write PNG files.
1. If the frame is unfamiliar, run `monaco-nb <nb> --columns` (setup only, saves nothing) and read the dtypes.
2. Ask ONE question — which dimension and which 0/1 flag — proposing a default from the columns, and end it with "is this right?". Wait for the answer.
3. Run `monaco-nb <nb> penetration --dim <D> --flag <F> [--flag-label ...] [--entity <E>]`. It upserts the section tagged `penetration:<dim|entity>` (same id = replaced in place, so a re-run with a tweak
   does not duplicate), executes only the setup cell and that cell in a fresh kernel, writes the notebook, and prints the table.
4. Paste the printed table and note verbatim; the chart is in the notebook output. Then stop and let the user narrate.
If the notebook does not exist yet, add `--setup-file <py that defines df>` once; later calls reuse the notebook's setup cell.
Different question, same view → pass `--id penetration:<name>` to keep both sections. Code: `src/monaco/nbx.py`.
