# Contracts and metric definitions

The analytics modules read **column contracts**, not schemas. Whatever the warehouse calls things, the SQL
(or `--cols`) maps it onto these names and nothing downstream changes. Every metric states its grain, because
the trap in any platform business is mixing grains: a partner can be 100k accounts, an account is not a human,
a submitted order is not a trade.

## Funnel contract — `monaco.funnel`, `/funnel-cohort`

One long event table, one row per (entity, event, timestamp):

| column | meaning |
|---|---|
| `account_id` | the entity moving through the funnel (an account, a user, a shop…) |
| `partner_id` | the group the entity belongs to (a partner, a channel, a region…) |
| `event` | stage name, or a repeated activity event (`trade`, `order`, `session`…) |
| `ts` | when it happened |

Stages are an ordered list (default `created → kyc_approved → funded → first_trade`); the last may be
`first_<activity>`, derived as `MIN(ts)` of the activity event when not present. `MIN` per stage collapses
retries.

**Conversion** is always *of entities that entered the first stage within the window*, with the denominator
holding only entities old enough to have had the window (censoring). Pooled (entity-weighted) and
group-weighted rates are reported together; a gap between them is a mix story, not a product story.
Wilson intervals on every rate.

**Retention** (grain: anchor-cohort month × age in months): share with ≥ 1 activity event in month *k* after
the anchor stage. Ages beyond the last complete month are `NaN`, never zero. Read rows (life of a cohort),
then columns (cohort quality), then diagonals (calendar events).

**Time to stage** (grain: entity): days between consecutive stages, p50 / p75 / p90 among arrivers plus the
share that never arrived. Never a mean.

## Partner-health contract — `monaco.partner_health`, `/partner-health`

A partner × calendar-month table:

| column | definition | kind |
|---|---|---|
| `partner_id`, `month` | the grain | |
| `new_accounts` | entities created in the month | count |
| `kyc7_n`, `kyc7_k` | created ≥ 7 days ago / of those, approved within 7 days | rate (cohort-keyed) |
| `fund30_n`, `fund30_k` | created ≥ 30 days ago / of those, funded within 30 days | rate (cohort-keyed) |
| `funded_new` | entities whose first funding fell in the month | count |
| `gross_deposits`, `withdrawals`, `net_deposits` | money in, money out, the difference, by the month it completed | sum |
| `trading_accounts` | distinct entities with ≥ 1 activity in the month | count |
| `fills` | activity count in the month | count |
| `filled_notional` | value of the activity (executed, not requested) | sum |

Optional partner × entity roll-up (`account_id, partner_id, funded, net_deposits, fills, filled_notional`)
feeds the concentration views.

**Early-warning flags** (grain: partner × metric × test; baseline = the trailing 3 months before the tested
block). Two tests: *acute* (last complete month) and *sustained* (last two months pooled). Flag when the value
sits outside the baseline's 95% interval **and** the move net of the portfolio's own move is ≥ 5 pp for rates
or ≥ 20% relative for counts and sums **and** the partner has enough basis (default ≥ 100 entities). Net-of-
portfolio is the mix guard: a seasonal month moves everyone, and that is not a partner story. Two consecutive
months of negative net deposits is a *contraction* flag; any partner above 25% of a portfolio total is a
standing *concentration* flag regardless of trend. Thin partners are listed, never flagged.

## The sandbox mapping (what the shipped SQL does)

`src/monaco/sandbox/sql/*.sql` map the synthetic brokerage-platform tables onto the contracts above:
created = `accounts.created_at` (live accounts only); KYC approved = first status transition to
`APPROVED`/`ACTIVE`; funded = first `COMPLETE INCOMING` transfer or first executed journal in; trade = every
`FILL` activity (never an order); notional = `SUM(qty × price)` over fills. Rewrite those three files for a
real warehouse; the modules and skills do not change.

## Things the modules will not do
- Quote a rate without its window and its denominator.
- Entity-weight a portfolio metric when one group is 40% of entities without also showing it group-weighted.
- Count submitted orders as trades, or treat a current-state status column as an event log.
- Use causal language. A cohort step is a hypothesis; a DiD against unexposed groups is the next notebook.

## The close (every readout, in this order)
**Headline** (one number with its window) → **Go / No-go** (ship / hold / investigate) → **Action** (who does
what by when) → **Guardrail** (the metric that would make us reverse) → **Revisit** (date, and what maturity
the cohorts will have by then). `write_readout()` writes `[TODO]` for a missing line; CLIs tag code-drafted
lines `[draft]`. Either tag means the readout is not done.
