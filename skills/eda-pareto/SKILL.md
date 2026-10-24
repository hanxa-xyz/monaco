---
name: eda-pareto
description: EDA view: concentration — cumulative share of value vs share of entities (Lorenz curve, Gini), the smallest set of entities producing 50/80% of value. Use for 'do 20% of customers make 80% of revenue', defining a core tier, value-concentration questions.
user-invocable: true
---

# /eda-pareto

**Question:** how concentrated is value across entities; how many entities make 50/80% of it.
**Call:** `v, tiers = pareto(df, entity, value, label=...)` — `tiers` maps mark → entities needed.
**Read:** the bow of the curve is the concentration; the 80% set is the natural 'core' tier — give it a NEUTRAL name (never pejorative for the rest). Tier interventions belong to `/takehome-sizing`, not here.
**Chart rules:** square axes, BLACK curve from the origin, GRAY diagonal, marks at 50/80 annotated `top k (x%) = y% of value`, Gini in subtitle.
**Stop:** one per (entity, value); ≤ 2. Then define the tier once and reuse its name everywhere.

Shared rules: `/eda` skill (guardrails, inputs, the vocabulary). Code: `src/monaco/eda.py`.
Returns `View(fig, table, note)` — always print the table and the note under the chart. Read the PNG before calling it done.
