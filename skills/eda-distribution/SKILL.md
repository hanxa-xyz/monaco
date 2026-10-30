---
name: eda-distribution
description: EDA view: of the total, how it splits across a dimension — vertical bars, share of entities and share of the anchor metric side by side. Use for 'what percent of users are in each segment', 'where does the revenue sit'. Each series sums to 100%.
user-invocable: true
---

# /eda-distribution

**Question:** of the total (entities and metric), how much sits in each group of D.
**Call:** `distribution(df, dim, metric=..., entity=None|'entity_col', metric_label=..., entity_label=...)`.
**Read:** dark bar (share of metric) above light bar (share of entities) = the group punches above its weight per entity. This is the 'of the total' view; penetration is 'of the group'.
**Chart rules:** VERTICAL always; label `share of each population (distribution)`; % labels on every bar; n= in ticks; ordered categoricals keep their order, others sort by N.
**Stop:** one per dimension.

Shared rules: `/eda` skill (guardrails, inputs, the vocabulary). Code: `src/monaco/eda.py`.
Returns `View(fig, table, note)` — always print the table and the note under the chart. Read the PNG before calling it done.

## In-place mode (live): `/eda-distribution <notebook.ipynb>`
When the user passes a notebook path, do NOT rebuild anything and do NOT write PNG files.
1. If the frame is unfamiliar, run `monaco-nb <nb> --columns` (setup only, saves nothing) and read the dtypes.
2. Ask ONE question — which dimension (and the anchor metric) — proposing a default from the columns, and end it with "is this right?". Wait for the answer.
3. Run `monaco-nb <nb> distribution --dim <D> [--metric <M>] [--entity <E>]`. It upserts the section tagged `distribution:<dim|entity>` (same id = replaced in place, so a re-run with a tweak
   does not duplicate), executes only the setup cell and that cell in a fresh kernel, writes the notebook, and prints the table.
4. Paste the printed table and note verbatim; the chart is in the notebook output. Then stop and let the user narrate.
If the notebook does not exist yet, add `--setup-file <py that defines df>` once; later calls reuse the notebook's setup cell.
Different question, same view → pass `--id distribution:<name>` to keep both sections. Code: `src/monaco/nbx.py`.
