---
name: eda-trio
description: EDA view: by one dimension, total metric · metric per entity · N — three horizontal panels sharing row order. Use for 'average/total revenue by segment', 'how big is each group', or any magnitude-by-dimension question (this is NOT penetration).
user-invocable: true
---

# /eda-trio

**Question:** by dimension D, how much (total), how much each (per entity), how many (N).
**Call:** `trio(df, dim, metric, entity=None|'entity_col', metric_label=..., entity_label=...)`.
**Inputs:** ONE metric, one dim per call (loop dims in the builder), entity if rows ≠ entities.
**Read:** a group can be big because it is many entities (right panel) or worth more each (middle). Say which.
**Chart rules:** horizontal, rows sorted by total, value + share label on totals, n= in ticks, top-6+Else, pale = n<15.
**Stop:** one trio per dimension (≤3). Ranking questions answered here; rates go to penetration.

Shared rules: `/eda` skill (guardrails, inputs, the vocabulary). Code: `src/monaco/eda.py`.
Returns `View(fig, table, note)` — always print the table and the note under the chart. Read the PNG before calling it done.

## In-place mode (live): `/eda-trio <notebook.ipynb>`
When the user passes a notebook path, do NOT rebuild anything and do NOT write PNG files.
1. If the frame is unfamiliar, run `monaco-nb <nb> --columns` (setup only, saves nothing) and read the dtypes.
2. Ask ONE question — which dimension and which ONE metric — proposing a default from the columns, and end it with "is this right?". Wait for the answer.
3. Run `monaco-nb <nb> trio --dim <D> --metric <M> [--entity <E>] [--metric-label ...]`. It upserts the section tagged `trio:<dim|entity>` (same id = replaced in place, so a re-run with a tweak
   does not duplicate), executes only the setup cell and that cell in a fresh kernel, writes the notebook, and prints the table.
4. Paste the printed table and note verbatim; the chart is in the notebook output. Then stop and let the user narrate.
If the notebook does not exist yet, add `--setup-file <py that defines df>` once; later calls reuse the notebook's setup cell.
Different question, same view → pass `--id trio:<name>` to keep both sections. Code: `src/monaco/nbx.py`.
