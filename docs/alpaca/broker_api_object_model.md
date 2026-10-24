# Broker API object model — field names and enums (public docs, pulled 2026-10-23)

Source: docs.alpaca.markets (Broker API reference + guides). This is the subset the sandbox loader
materialises. Strings in the API are decimals-as-strings; the DuckDB schema casts them to DOUBLE.
**Not an API field:** `correspondent` on `accounts`. In the real API the partner is the API key owner
(one key = one correspondent); the sandbox loader stamps it on every row so partner-level SQL works.

## accounts (`GET /v1/accounts`, `GET /v1/accounts/{id}`)
Fields used: `id`, `account_number`, `status`, `crypto_status`, `currency`, `last_equity`, `created_at`,
`account_type`, `enabled_assets`, `kyc_results` (object: `accept` / `indeterminate` / `reject` reason sets,
`summary`). Current status only; history comes from the Events API (`status_from`, `status_to`, `at`).

| status | meaning |
|---|---|
| `ONBOARDING` | created, KYC not yet run (Onfido flow only) |
| `SUBMITTED` | application processing; automatic KYC runs async (transitory) |
| `SUBMISSION_FAILED` | creation failed on Alpaca's side |
| `ACTION_REQUIRED` | user must supply documents; `kyc_results` says why |
| `APPROVAL_PENDING` | failed auto-KYC, manual review by Alpaca |
| `APPROVED` | KYC passed, about to go active (transitory) |
| `ACTIVE` | can trade the enabled asset (the normal resting state) |
| `ACCOUNT_UPDATED` | PII changed, under review, then back to ACTIVE |
| `REJECTED` | terminal, cannot go active |
| `ACCOUNT_CLOSED` | terminal, no trading or funding |
| `INACTIVE` / `PAPER_ONLY` | not enabled for the asset / paper only |

Typical path: `SUBMITTED → (ACTION_REQUIRED | APPROVAL_PENDING)? → APPROVED → ACTIVE`. Fully-disclosed
broker-dealers do their own KYC and start at `APPROVED`.
`account_type`: trading, custodial, donor_advised, ira, trust, omnibus_non_disclosed, omnibus_sub, hsa, joint.

## orders (`GET /v1/trading/accounts/{id}/orders`)
`id`, `client_order_id`, `created_at`, `updated_at`, `submitted_at`, `filled_at`, `expired_at`, `canceled_at`,
`failed_at`, `replaced_at`, `replaced_by`, `replaces`, `asset_id`, `symbol`, `asset_class`, `notional`, `qty`,
`filled_qty`, `filled_avg_price`, `order_class`, `order_type`/`type`, `side`, `time_in_force`, `limit_price`,
`stop_price`, `status`, `extended_hours`, `commission`.

- `status`: new, partially_filled, filled, done_for_day, canceled, expired, replaced, pending_cancel,
  pending_replace, accepted, pending_new, accepted_for_bidding, stopped, rejected, suspended, calculated.
  Terminal: filled, canceled, expired, replaced, rejected. `status` is the CURRENT state, not a log.
- `type`: market, limit, stop, stop_limit, trailing_stop · `side`: buy, sell ·
  `time_in_force`: day, gtc, opg, cls, ioc, fok · `order_class`: simple, bracket, oco, oto, mleg ·
  `asset_class`: us_equity, us_option, crypto, ipo.
- `notional` is the REQUESTED dollar amount (nullable when `qty` is given). Filled dollars = `filled_qty × filled_avg_price`,
  or better, sum the FILL activities.

## positions (`GET /v1/trading/accounts/{id}/positions`) — a snapshot, not history
`asset_id`, `symbol`, `exchange`, `asset_class`, `avg_entry_price`, `qty`, `qty_available`, `side` (long, short),
`market_value`, `cost_basis`, `unrealized_pl`, `unrealized_plpc`, `unrealized_intraday_pl`,
`unrealized_intraday_plpc`, `current_price`, `lastday_price`, `change_today`, `asset_marginable`.

## activities (`GET /v1/accounts/activities[/{type}]`) — the ledger; the best single table for behaviour
Common: `id`, `account_id`, `activity_type`.
Trade activity (FILL): `transaction_time`, `type` (fill, partial_fill), `price`, `qty`, `side` (buy, sell, sell_short),
`symbol`, `leaves_qty`, `cum_qty`, `order_id`, `order_status`.
Non-trade activity: `date`, `net_amount`, `symbol`, `qty`, `per_share_amount`, `description`, `status`
(executed, correct, canceled), `activity_sub_type`, `group_id`, `transfer_id`.

| activity_type | meaning | activity_type | meaning |
|---|---|---|---|
| FILL | order fill (partial or full) | JNLC / JNLS | journal, cash / stock |
| CSD | cash deposit | CSW | cash withdrawal |
| DIV, DIVCGL, DIVCGS, DIVNRA, DIVROC, DIVTXEX | dividend variants | INT | interest (credit or margin) |
| FEE | REG and TAF fees | ACATC / ACATS | ACATS transfer in/out, cash / securities |
| CGD, CIL | cap-gains distribution, cash in lieu | MA, REO, REORG, SPIN, SPLIT | corporate actions |
| OPASN, OPEXP, OPEXC, OPCA, OPCSH, OPTRD | options lifecycle | PTC | pass-thru charge |
| FOPT | free-of-payment transfer | OCT | on-chain (crypto) transaction |

## transfers (`GET /v1/accounts/{id}/transfers`)
`id`, `account_id`, `type` (ach, wire), `status`, `amount`, `direction` (INCOMING = deposit, OUTGOING = withdrawal),
`created_at`, `updated_at`, `expires_at`, `hold_until`, `relationship_id` (ACH), `bank_id` (wire), `fee`,
`fee_payment_method` (user, invoice), `requested_amount`, `instant_amount`, `reason`.
`status`: QUEUED → APPROVAL_PENDING → PENDING → SENT_TO_CLEARING → COMPLETE, or APPROVED; failure/undo:
REJECTED, CANCELED, RETURNED. **"Funded" = first `COMPLETE` INCOMING transfer (or an executed JNLC in).**
A RETURNED transfer after COMPLETE is how a deposit un-happens; count it as negative in net deposits.

## journals (`GET /v1/journals`)
`id`, `from_account`, `to_account`, `entry_type` (JNLC cash, JNLS stock), `status`, `net_amount`, `symbol`, `qty`,
`price`, `description`, `currency`, `settle_date`, `system_date`, `created_at`.
`status`: queued → sent_to_clearing → executed (→ activity_created, JNLC v2); pending (manual review), rejected,
canceled, deleted, correct, refused. Journals only move firm ↔ user, never user ↔ user. Partners use JNLC from a
pre-funded firm account for instant funding and promos; JNLS for share rewards.
