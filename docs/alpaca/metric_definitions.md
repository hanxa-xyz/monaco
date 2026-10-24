# Broker API metric glossary (one page, my words)

**Partner = customer.** A partner (correspondent, one API key) is the fintech / RIA / broker-dealer that
embeds Alpaca. End users are the partner's customers; we see their brokerage events, never their logins.
Every metric below says its grain out loud. The trap in this business is mixing grains: a partner can be
100k accounts, an account is not a human, an order is not a fill.

**Live only.** Paper accounts (`PAPER_ONLY`) never enter a funnel or a health metric.

## The account funnel (grain: one row per live account, timestamps nullable)

| stage | definition (first time it happens) | source |
|---|---|---|
| **created** | account object exists | `accounts.created_at` |
| **KYC approved** | first transition to `APPROVED` or `ACTIVE` | `account_status_events.status_to` (`MIN(at)`) |
| **funded** | first `COMPLETE` `INCOMING` transfer, or first `executed` `JNLC` into the account | `transfers`, `journals` |
| **first trade** | first `FILL` activity (not first order: submitting is not filling) | `activities.activity_type = 'FILL'` |
| **active** | see below | `activities` |

Rates are always **of accounts created in the window**, with the step-conditional rate alongside
(funded given KYC, traded given funded). Every rate carries a window (1 / 7 / 30 / 90 days from creation)
and the denominator only holds accounts old enough to have had the window. An unwindowed "activation
rate" is a mix of cohort ages and I do not report one.

**Proposed "active" (account-month):** in trailing 30 days, **≥ 1 FILL with notional > $10, OR average
daily equity ≥ $1,000**. Traders and holders both pay (order flow / spread on one side, cash interest
on the other), so "active" = the account made money for someone this month. Report the two components
(Traders / Holders / Both) next to the headline. Tiny-fill rate and deposit round-trips are the gaming
guardrails. Until equity history exists in the warehouse, fall back to **≥ 1 FILL in the month**.

**Retention (grain: funded cohort month × age in months):** active in month k after funding, cohort =
calendar month of `funded_at`. Read rows (life of a cohort), then columns (cohort quality), then
diagonals (calendar events) before comparing anything.

**Time to stage (grain: account):** hours from the earlier stage to the later one, reported as p25 / p50 /
p75 plus the share that never arrived. Never a mean: accounts that fund and sit in cash wreck it.

## Partner health (grain: one row per partner × month unless stated)

| metric | definition | grain |
|---|---|---|
| **new accounts** | live accounts created in the month | partner × month |
| **KYC approval rate** | approved within 7d / created, accounts old enough | partner × cohort month |
| **funded accounts** | accounts whose first funding was in the month (new) and cumulative ever-funded (stock) | partner × month |
| **funded rate** | funded within 30d / created, accounts old enough | partner × cohort month |
| **gross deposits** | `SUM(amount)` of `COMPLETE INCOMING` transfers + executed `JNLC` in, by completion month | partner × month |
| **net deposits** | gross deposits − `COMPLETE OUTGOING` withdrawals − `RETURNED` deposits − `JNLC` out | partner × month |
| **trading accounts** | distinct accounts with ≥ 1 FILL in the month | partner × month |
| **fills / trading account** | FILL count ÷ trading accounts (trade frequency; median per account alongside) | partner × month |
| **filled notional** | `SUM(qty × price)` over FILL activities (never `orders.notional`, which is requested) | partner × month |
| **active accounts** | per the active definition above | partner × month |
| **concentration** | partner's share of accounts / net deposits / notional; Gini and "partners for 50 / 80%" | portfolio × month |

**Early-warning flags (grain: partner × metric × test; baseline = the 3 months before the tested block):**
two tests, acute (last complete month) and sustained (last 2 months pooled, which catches a shift that
began last month). Flag when the value sits outside the baseline's 95% interval AND the move **net of the
portfolio's own move over the same months** is ≥ 5 pp for rates or ≥ 20% relative for counts and dollars,
AND the partner is big enough to matter (≥ 100 accounts of basis). Net-of-portfolio is the mix guard: a
seasonal month moves everyone, and that is not a partner story. Two consecutive months of negative net
deposits is its own flag (contraction); any partner above 25% of a portfolio total is a standing
concentration flag regardless of trend.

## Things I will not do
- Quote a rate without its window and its denominator.
- Account-weight a portfolio metric when one partner is 40% of accounts without also showing it
  partner-weighted (or excluding that partner). Mix shifts look like product regressions.
- Join `orders` to count trades. Fills live in `activities`; `orders.status` is a current state, not a log.
- Call an A/B test at the account level inside one partner's app without saying the unit of
  randomization and the cluster. Partners are the clusters; often there are too few of them.

## Close template for any readout (forced, because my closes run thin)
**Headline** (one number with its window) → **Go / No-go** (or: ship / hold / investigate) →
**Action** (who does what by when) → **Guardrail** (the metric that would make us reverse) →
**Revisit** (date, and what maturity the cohorts will have by then).
