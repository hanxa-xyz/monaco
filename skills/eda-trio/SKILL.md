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
