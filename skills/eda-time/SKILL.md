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
