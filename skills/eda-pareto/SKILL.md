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

## In-place mode (live): `/eda-pareto <notebook.ipynb>`
When the user passes a notebook path, do NOT rebuild anything and do NOT write PNG files.
1. If the frame is unfamiliar, run `monaco-nb <nb> --columns` (setup only, saves nothing) and read the dtypes.
2. Ask ONE question — which entity and which value — proposing a default from the columns, and end it with "is this right?". Wait for the answer.
3. Run `monaco-nb <nb> pareto --entity <E> --value <V> [--label ...]`. It upserts the section tagged `pareto:<dim|entity>` (same id = replaced in place, so a re-run with a tweak
   does not duplicate), executes only the setup cell and that cell in a fresh kernel, writes the notebook, and prints the table.
4. Paste the printed table and note verbatim; the chart is in the notebook output. Then stop and let the user narrate.
If the notebook does not exist yet, add `--setup-file <py that defines df>` once; later calls reuse the notebook's setup cell.
Different question, same view → pass `--id pareto:<name>` to keep both sections. Code: `src/monaco/nbx.py`.
