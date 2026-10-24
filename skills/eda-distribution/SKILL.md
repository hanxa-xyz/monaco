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
