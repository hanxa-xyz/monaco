---
name: eda-saturation
description: EDA view: cumulative % of entities with ≤ k of something (orders, offers shown, sessions) — step CDF with the k needed to reach 80/90/95%. Use for 'how many N do we need to cover 90% of users', long-tail sizing, capping decisions.
user-invocable: true
---

# /eda-saturation

**Question:** what k covers 80/90/95% of entities (rows per entity, or a per-entity sum of a count column).
**Call:** `v, ks = saturation(df, entity, count_col=None|'col', label=..., max_k=None)` — `ks` is the dict of k per mark.
**Read:** the flatter the tail past 90%, the more each extra point of coverage costs — that is the argument for a cap or a tiered treatment.
**Chart rules:** step CDF from 0, dashed marks at 80/90/95 with the k annotated, x = k, y = cumulative % of entities.
**Stop:** one per (entity, count) pair; ≤ 2 pairs. Pairing this with `/eda-pareto` (value side) is the standard combo.

Shared rules: `/eda` skill (guardrails, inputs, the vocabulary). Code: `src/monaco/eda.py`.
Returns `View(fig, table, note)` — always print the table and the note under the chart. Read the PNG before calling it done.
