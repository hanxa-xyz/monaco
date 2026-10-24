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
