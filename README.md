# monaco

A data-science toolkit with one house grammar: charts that read the same way every time, a fixed EDA
vocabulary, an exploratory modelling pass with its decisions printed, funnel/cohort and partner-health
analytics on simple column contracts, and readouts that cannot skip the close.

It ships with a set of Claude Code skills (`skills/`) that drive the toolkit, so anyone who clones this repo
gets both the code and the agent workflows in one `git pull`.

## Install

```bash
pip install -e ".[all]"
```

```bash
scripts/install_skills.sh          # symlink skills + agents into ~/.claude for every project
```

Python ≥ 3.9. Core deps: numpy, pandas, matplotlib, duckdb, scipy. Extras: `model` (scikit-learn, xgboost),
`notebook` (nbformat, nbconvert, ipykernel), `dev` (pytest, ruff).

## Try it in 30 seconds

```bash
make demo
```

That builds a synthetic B2B2C brokerage-platform DuckDB (36 partners, ~47k accounts, realistic field names and
enums, four planted partner stories) under `./data`, then runs the two analytics CLIs. Look at:

- `out/funnel/readout.md` + `out/funnel/figs/` — 30-day stage conversion by partner and by cohort, time-to-stage, retention.
- `out/partner_health/readout.md` + `out/partner_health/figs/` — Pareto/HHI concentration, per-partner trends, early-warning flags.
- `monaco-survival` → `out/survival/` — time from funded to first trade with censoring, by partner, log-rank.
- `monaco-did` → `out/did/` — difference-in-differences and event study that recover a planted single-partner drop.

Both readouts end with the five-line close (Headline → Go / No-go → Action → Guardrail → Revisit). Lines
the code drafted from numbers are tagged `[draft]`; finishing them is the analyst's job, and the tag makes
an unfinished one visible.

## Use it on your own data

The analytics read column **contracts**, not schemas. Map whatever your table calls things with `--cols`:

```bash
monaco-funnel --csv events.csv --cols account_id=acct,partner_id=corr,event=stage,ts=event_time --window 30
```

```bash
monaco-partner-health --csv-month partner_month.csv --cols-month partner_id=corr,month=ym --as-of 2026-09-30
```

Or from a warehouse export in DuckDB: `--db my.duckdb --sql my_events.sql`. Everything upstream of the
contract is the SQL file's problem; nothing downstream needs to change.

In a notebook:

```python
from monaco.viz import apply_style
from monaco.eda import structure, trio, penetration, mix, distribution, time_series, saturation, pareto
apply_style(dpi=110)
v = penetration(df, dim='segment', flag='repeat_90d', entity_label='customer')   # -> View(fig, table, note)
v.table
```

## What's in the box

| | |
|---|---|
| `monaco.viz` | palette and chart grammar (`titled`, `apply_style`, `save_fig`/`img`, notebook cell helpers) |
| `monaco.eda` | structure · trio · penetration · mix · distribution · time · saturation · pareto |
| `monaco.eda_build` / `model_build` | SPEC dict → one executed notebook |
| `monaco.modeling` | RandomForest + XGBoost, deterministic decisions, leakage tripwire, PDPs, ranked hypotheses |
| `monaco.funnel` | W-day conversion with Wilson CIs and censoring-aware denominators, cohort lines, time-to-stage CDFs, retention triangle |
| `monaco.partner_health` | Lorenz/Gini/HHI, small-multiple trends with intervals, flags net of the portfolio's own move |
| `monaco.survival` | Kaplan-Meier + Greenwood CI, at-risk row, median/RMST, peak-hazard window, log-rank, naive-vs-KM bias view |
| `monaco.causal` | method ladder, DiD + event study with cluster bootstrap and pre-trend test, CUPED, IPW with overlap/balance, ITS |
| `monaco.readout` | print every table you chart; the readout writer that forces the close |
| `monaco.sandbox` | synthetic platform dataset: partners, accounts, KYC events, transfers, orders, fills |
| `skills/` | `/eda*`, `/model`, `/takehome-*` (kickstart → eda → charts → notebooks → sizing → report → handoff), `/funnel-cohort`, `/partner-health`, `/survival`, `/causal` |
| `docs/contracts.md` | the column contracts and metric definitions the funnel / partner-health modules read |
| `docs/causal.md`, `docs/survival.md` | the method ladder with assumptions; time-to-event with censoring |
| `docs/PLAYBOOK.md` | the full rulebook; `AGENTS.md` is the short form for agents |

## Development

```bash
make test
```

```bash
make lint
```

See [AGENTS.md](AGENTS.md) for the conventions the code enforces and how to add a view or a skill.
