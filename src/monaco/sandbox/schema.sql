-- Alpaca Broker API object model as a DuckDB schema. Real field names and enum values
-- (docs/broker_api_object_model.md). Enums are enforced with DuckDB ENUM types so a bad
-- value fails at load, not in a chart.

CREATE TYPE account_status AS ENUM ('INACTIVE','PAPER_ONLY','ONBOARDING','SUBMITTED','SUBMISSION_FAILED',
    'ACTION_REQUIRED','ACCOUNT_UPDATED','APPROVAL_PENDING','APPROVED','REJECTED','ACTIVE','ACCOUNT_CLOSED');
CREATE TYPE account_type AS ENUM ('trading','custodial','donor_advised','ira','trust','omnibus_non_disclosed',
    'omnibus_sub','hsa','joint');
CREATE TYPE order_status AS ENUM ('new','partially_filled','filled','done_for_day','canceled','expired','replaced',
    'pending_cancel','pending_replace','accepted','pending_new','accepted_for_bidding','stopped','rejected',
    'suspended','calculated');
CREATE TYPE order_type AS ENUM ('market','limit','stop','stop_limit','trailing_stop');
CREATE TYPE order_side AS ENUM ('buy','sell');
CREATE TYPE time_in_force AS ENUM ('day','gtc','opg','cls','ioc','fok');
CREATE TYPE order_class AS ENUM ('simple','bracket','oco','oto','mleg');
CREATE TYPE asset_class AS ENUM ('us_equity','us_option','crypto','ipo');
CREATE TYPE position_side AS ENUM ('long','short');
CREATE TYPE activity_type AS ENUM ('FILL','ACATC','ACATS','CGD','CIL','CSD','CSW','DIV','DIVCGL','DIVCGS','DIVNRA',
    'DIVROC','DIVTXEX','FEE','INT','JNLC','JNLS','MA','OPASN','OPCA','OPCSH','OPEXC','OPEXP','OPTRD','PTC','REO',
    'REORG','SPIN','SPLIT','FOPT','OCT');
CREATE TYPE fill_type AS ENUM ('fill','partial_fill');
CREATE TYPE nta_status AS ENUM ('executed','correct','canceled');
CREATE TYPE transfer_type AS ENUM ('ach','wire');
CREATE TYPE transfer_direction AS ENUM ('INCOMING','OUTGOING');
CREATE TYPE transfer_status AS ENUM ('QUEUED','APPROVAL_PENDING','PENDING','SENT_TO_CLEARING','REJECTED','CANCELED',
    'APPROVED','COMPLETE','RETURNED');
CREATE TYPE journal_entry_type AS ENUM ('JNLC','JNLS');
CREATE TYPE journal_status AS ENUM ('pending','canceled','executed','activity_created','queued','rejected','deleted',
    'refused','sent_to_clearing','correct');

-- Partners are NOT an API object: one API key = one correspondent. Synthetic table for partner-level work.
CREATE TABLE partners (
    correspondent   VARCHAR PRIMARY KEY,           -- 4-letter correspondent code
    partner_name    VARCHAR,
    partner_type    VARCHAR,                        -- fintech | neobank | ria | bd | crypto_exchange
    country         VARCHAR,
    onboarded_at    DATE,
    kyc_flow        VARCHAR,                        -- alpaca_kyc | fully_disclosed_bd (own KYC, starts APPROVED)
    instant_funding BOOLEAN                         -- funds users via JNLC from a firm account
);

CREATE TABLE accounts (
    id              UUID PRIMARY KEY,
    account_number  VARCHAR,
    correspondent   VARCHAR,                        -- not an API field; see above
    status          account_status,
    crypto_status   account_status,
    currency        VARCHAR,
    last_equity     DOUBLE,
    created_at      TIMESTAMP,
    account_type    account_type,
    enabled_assets  VARCHAR[],
    kyc_summary     VARCHAR                         -- kyc_results.summary: pass | fail | NULL
);

-- Events API: account status transitions (the account object only holds the current status).
CREATE TABLE account_status_events (
    event_id        BIGINT,
    account_id      UUID,
    account_number  VARCHAR,
    "at"            TIMESTAMP,
    status_from     account_status,
    status_to       account_status,
    reason          VARCHAR
);

CREATE TABLE orders (
    id                  UUID PRIMARY KEY,
    client_order_id     VARCHAR,
    account_id          UUID,
    created_at          TIMESTAMP,
    updated_at          TIMESTAMP,
    submitted_at        TIMESTAMP,
    filled_at           TIMESTAMP,
    expired_at          TIMESTAMP,
    canceled_at         TIMESTAMP,
    failed_at           TIMESTAMP,
    asset_id            UUID,
    symbol              VARCHAR,
    asset_class         asset_class,
    notional            DOUBLE,                     -- REQUESTED dollars (null when qty given)
    qty                 DOUBLE,                     -- requested qty (null when notional given)
    filled_qty          DOUBLE,
    filled_avg_price    DOUBLE,
    order_class         order_class,
    type                order_type,
    side                order_side,
    time_in_force       time_in_force,
    limit_price         DOUBLE,
    stop_price          DOUBLE,
    status              order_status,
    extended_hours      BOOLEAN,
    commission          DOUBLE
);

CREATE TABLE positions (                            -- snapshot as of the load timestamp
    account_id              UUID,
    asset_id                UUID,
    symbol                  VARCHAR,
    exchange                VARCHAR,
    asset_class             asset_class,
    avg_entry_price         DOUBLE,
    qty                     DOUBLE,
    qty_available           DOUBLE,
    side                    position_side,
    market_value            DOUBLE,
    cost_basis              DOUBLE,
    unrealized_pl           DOUBLE,
    unrealized_plpc         DOUBLE,
    current_price           DOUBLE,
    lastday_price           DOUBLE,
    change_today            DOUBLE,
    asset_marginable        BOOLEAN
);

-- Trade (FILL) and non-trade activities share one table, as /v1/accounts/activities returns them.
CREATE TABLE activities (
    id                  VARCHAR PRIMARY KEY,
    account_id          UUID,
    activity_type       activity_type,
    -- trade activity fields
    transaction_time    TIMESTAMP,
    type                fill_type,
    price               DOUBLE,
    qty                 DOUBLE,
    side                VARCHAR,                    -- buy | sell | sell_short
    symbol              VARCHAR,
    leaves_qty          DOUBLE,
    cum_qty             DOUBLE,
    order_id            UUID,
    order_status        order_status,
    -- non-trade activity fields
    date                DATE,
    net_amount          DOUBLE,
    per_share_amount    DOUBLE,
    description         VARCHAR,
    status              nta_status,
    activity_sub_type   VARCHAR,
    transfer_id         UUID
);

CREATE TABLE transfers (
    id              UUID PRIMARY KEY,
    account_id      UUID,
    relationship_id UUID,
    type            transfer_type,
    status          transfer_status,
    amount          DOUBLE,
    direction       transfer_direction,
    created_at      TIMESTAMP,
    updated_at      TIMESTAMP,
    expires_at      TIMESTAMP,
    hold_until      TIMESTAMP,
    instant_amount  DOUBLE,
    reason          VARCHAR
);

CREATE TABLE journals (
    id              UUID PRIMARY KEY,
    from_account    UUID,
    to_account      UUID,
    entry_type      journal_entry_type,
    status          journal_status,
    net_amount      DOUBLE,
    symbol          VARCHAR,
    qty             DOUBLE,
    price           DOUBLE,
    description     VARCHAR,
    currency        VARCHAR,
    settle_date     DATE,
    system_date     DATE,
    created_at      TIMESTAMP
);
