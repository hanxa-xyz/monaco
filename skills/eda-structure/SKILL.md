---
name: eda-structure
description: EDA view: what is the shape of the data — one row = ?, dtypes, nulls, dupes, describe (p25/50/75/99), value_counts, granularity verdicts on candidate keys. Tables only, no charts. Use first on any dataset or when asked for shape/nulls/granularity/averages.
user-invocable: true
---

# /eda-structure

**Question:** what is one row, how big, how clean, what do the columns look like.
**Call:** `structure({'df': df, ...}, keys={'df': [['k1','k2'], ...]})` — pass every table and every candidate key set.
**Read first:** the grain verdicts (`IS the grain` / `NOT the grain`). Every count downstream depends on it.
**Then:** null clusters (>20%), duplicate rows, degenerate categories (n≈1), 'Unknown'-style missingness-as-category (often the interesting segment), long-tailed numerics (p99 ≫ p75).
**Output:** printed tables; 5–10 facts to HANDOFF §3. **Stop** when the grain is stated in one sentence per table.

Shared rules: `/eda` skill (guardrails, inputs, the vocabulary). Code: `src/monaco/eda.py`.
Returns `View(fig, table, note)` — always print the table and the note under the chart. Read the PNG before calling it done.
