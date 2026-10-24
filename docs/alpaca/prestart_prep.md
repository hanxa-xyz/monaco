# Pre-start build list — Broker API DS

Build against what is available before day one: the public Broker API object model. Anything built on it
ports to the warehouse by swapping the SQL that produces the contract columns.

## Built (in this repo)
1. **Metric definitions** — `metric_definitions.md`. Partner = customer; funnel = created → KYC approved →
   funded → first trade → active; partner health = funded accounts, net deposits, trade frequency, concentration.
   Written before seeing the company's definitions, so the fuzzy ones stand out.
2. **Funnel + cohort** — `monaco.funnel`, `/alpaca-funnel-cohort`. Contract: `account_id, partner_id, event, ts`.
3. **Partner health scorecard** — `monaco.partner_health`, `/alpaca-partner-health`. Pareto/HHI, trends with
   intervals, flags net of the portfolio move.
4. **Forced close** — `monaco.readout.write_readout`. Headline → Go/No-go → Action → Guardrail → Revisit;
   `[TODO]` / `[draft]` tags make an unfinished readout visible.
5. **Sandbox loader** — `monaco-sandbox`. Synthetic data with real field names and enums; order lifecycle and
   activity types (FILL, JNLC, CSD, DIV, …) in muscle memory before someone explains them.
6. **Data-quality checks** inside the loader report: grain, orphan accounts, fills-per-order.

## Not built yet (deliberately)
- **Experiment readout for partner-level experiments.** Partners are the clusters; small-N and clustered.
  Default to cluster-robust or partner-level aggregation, power/MDE up front. Needs to see how partners roll
  out features first.
- **Warehouse / BI adapters.** Snowflake vs BigQuery, dbt, Looker vs Metabase. Everything is SQL-first and
  pandas-portable; add the adapter in week one.
- **Event taxonomy.** Will be rewritten against the real one anyway.
- **Dashboards.** Nobody remembers a dashboard; they remember the memo.

## Must wait for the real stack
1. Partner key (the API-key owner / correspondent, not a field on the account).
2. Status history (is the Events API stream landed, or only current `accounts.status`?).
3. The "active" definition (needs daily equity history; fallback = ≥ 1 fill in month).
4. Paper vs live account representation.
5. Returned deposits (status log vs current state).
6. **AI-tooling policy.** Find out which tools are permitted and whether an agent may touch warehouse data.
   Everything here runs on synthetic data and emits portable SQL/pandas, so it is useful either way.

## Domain prep (two weeks of evenings)
- Order lifecycle; T+1 settlement; what unsettled cash does to funnel metrics.
- Journals and transfers (JNLC/JNLS, ACH, wire). Funding is the money step.
- Corporate actions (splits, dividends, symbol changes) — they corrupt position and PnL data.
- PFOF, margin basics, FINRA/SEC reporting cadence. Enough to not ask the embarrassing question.
- Read the Broker API docs end to end once. The PMs live in those docs.
