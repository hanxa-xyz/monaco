---
name: eda-time
description: EDA view: metric by period, optionally split by one dimension — line chart on a true date axis. Use when the data has a time column and the question is trend/seasonality/level shifts. Skipped automatically when there is no time column.
user-invocable: true
---

# /eda-time

**Question:** how does the metric (or count of entities) move by period, optionally by one dim.
**Call:** `time_series(df, time_col, metric=None|'m', freq='M'|'W'|'D', agg='sum'|'mean', split=None|'dim', entity=None)`.
**Inputs:** a parseable date column; choose freq so there are 8–40 points; ≤5 split lines (top-5+Else).
**Read:** first/last periods are usually partial — say so before reading a trend; look for level shifts and seasonality first, trend last. Cohort/retention curves are NOT this view (→ `/takehome-notebooks` 2).
**Chart rules:** true date axis, BLACK = total/largest series, end-point value labels, y from 0.
**Stop:** one chart for the metric, one split at most.

Shared rules: `/eda` skill (guardrails, inputs, the vocabulary). Code: `src/monaco/eda.py`.
Returns `View(fig, table, note)` — always print the table and the note under the chart. Read the PNG before calling it done.

## In-place mode (live): `/eda-time <notebook.ipynb>`
When the user passes a notebook path, do NOT rebuild anything and do NOT write PNG files.
1. If the frame is unfamiliar, run `monaco-nb <nb> --columns` (setup only, saves nothing) and read the dtypes.
2. Ask ONE question — which date column, which metric, which split — proposing a default from the columns, and end it with "is this right?". Wait for the answer.
3. Run `monaco-nb <nb> time --time-col <T> [--metric <M>] [--freq W|M|D] [--split <D>]`. It upserts the section tagged `time:<dim|entity>` (same id = replaced in place, so a re-run with a tweak
   does not duplicate), executes only the setup cell and that cell in a fresh kernel, writes the notebook, and prints the table.
4. Paste the printed table and note verbatim; the chart is in the notebook output. Then stop and let the user narrate.
If the notebook does not exist yet, add `--setup-file <py that defines df>` once; later calls reuse the notebook's setup cell.
Different question, same view → pass `--id time:<name>` to keep both sections. Code: `src/monaco/nbx.py`.
