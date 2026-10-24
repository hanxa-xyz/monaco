-- Partner health inputs, grain = partner x calendar month. Contract for /alpaca-partner-health:
--   partner_id, month, new_accounts, kyc7_n, kyc7_k, fund30_n, fund30_k, funded_new, gross_deposits,
--   withdrawals, net_deposits, trading_accounts, fills, filled_notional [, as_of]
-- Cohort-style rates (kyc7, fund30) are keyed by the account's CREATION month and only count accounts old
-- enough to have had the window (censoring). Flow metrics are keyed by the month they happened.
WITH params AS (
    SELECT (SELECT MAX(transaction_time) FROM activities WHERE activity_type = 'FILL')::TIMESTAMP AS as_of
),
live AS (
    SELECT id AS account_id, correspondent AS partner_id, created_at
    FROM accounts WHERE status <> 'PAPER_ONLY'
),
kyc AS (
    SELECT account_id, MIN("at") AS kyc_at FROM account_status_events
    WHERE status_to IN ('APPROVED', 'ACTIVE') GROUP BY 1
),
fund AS (
    SELECT account_id, MIN(ts) AS funded_at FROM (
        SELECT account_id, updated_at AS ts FROM transfers WHERE status = 'COMPLETE' AND direction = 'INCOMING'
        UNION ALL
        SELECT to_account, created_at FROM journals WHERE entry_type = 'JNLC' AND status IN ('executed', 'activity_created')
    ) GROUP BY 1
),
cohort AS (   -- creation-month cohorts: counts + windowed conversions with censoring
    SELECT l.partner_id, date_trunc('month', l.created_at)::DATE AS month,
           COUNT(*)                                                                   AS new_accounts,
           COUNT(*) FILTER (WHERE l.created_at <= p.as_of - INTERVAL 7 DAY)           AS kyc7_n,
           COUNT(*) FILTER (WHERE l.created_at <= p.as_of - INTERVAL 7 DAY
                              AND k.kyc_at <= l.created_at + INTERVAL 7 DAY)          AS kyc7_k,
           COUNT(*) FILTER (WHERE l.created_at <= p.as_of - INTERVAL 30 DAY)          AS fund30_n,
           COUNT(*) FILTER (WHERE l.created_at <= p.as_of - INTERVAL 30 DAY
                              AND f.funded_at <= l.created_at + INTERVAL 30 DAY)      AS fund30_k
    FROM live l CROSS JOIN params p
    LEFT JOIN kyc k USING (account_id)
    LEFT JOIN fund f USING (account_id)
    GROUP BY 1, 2
),
funded_new AS (
    SELECT l.partner_id, date_trunc('month', f.funded_at)::DATE AS month, COUNT(*) AS funded_new
    FROM fund f JOIN live l USING (account_id) GROUP BY 1, 2
),
money AS (     -- completed transfers by completion month; RETURNED/REJECTED never count
    SELECT l.partner_id, date_trunc('month', t.updated_at)::DATE AS month,
           SUM(t.amount) FILTER (WHERE t.direction = 'INCOMING') AS gross_deposits,
           SUM(t.amount) FILTER (WHERE t.direction = 'OUTGOING') AS withdrawals
    FROM transfers t JOIN live l USING (account_id)
    WHERE t.status = 'COMPLETE'
    GROUP BY 1, 2
),
jnl AS (       -- firm -> user cash journals count as deposits (instant funding, promos)
    SELECT l.partner_id, date_trunc('month', j.created_at)::DATE AS month, SUM(j.net_amount) AS journal_in
    FROM journals j JOIN live l ON l.account_id = j.to_account
    WHERE j.entry_type = 'JNLC' AND j.status IN ('executed', 'activity_created')
    GROUP BY 1, 2
),
trading AS (
    SELECT l.partner_id, date_trunc('month', a.transaction_time)::DATE AS month,
           COUNT(DISTINCT a.account_id) AS trading_accounts,
           COUNT(*)                     AS fills,
           SUM(a.qty * a.price)         AS filled_notional
    FROM activities a JOIN live l USING (account_id)
    WHERE a.activity_type = 'FILL'
    GROUP BY 1, 2
),
spine AS (
    SELECT DISTINCT partner_id, month FROM (
        SELECT partner_id, month FROM cohort UNION ALL SELECT partner_id, month FROM money
        UNION ALL SELECT partner_id, month FROM trading UNION ALL SELECT partner_id, month FROM funded_new
    )
)
SELECT s.partner_id, s.month,
       COALESCE(c.new_accounts, 0)   AS new_accounts,
       COALESCE(c.kyc7_n, 0)         AS kyc7_n,
       COALESCE(c.kyc7_k, 0)         AS kyc7_k,
       COALESCE(c.fund30_n, 0)       AS fund30_n,
       COALESCE(c.fund30_k, 0)       AS fund30_k,
       COALESCE(fn.funded_new, 0)    AS funded_new,
       COALESCE(m.gross_deposits, 0) + COALESCE(j.journal_in, 0)                               AS gross_deposits,
       COALESCE(m.withdrawals, 0)    AS withdrawals,
       COALESCE(m.gross_deposits, 0) + COALESCE(j.journal_in, 0) - COALESCE(m.withdrawals, 0)  AS net_deposits,
       COALESCE(t.trading_accounts, 0) AS trading_accounts,
       COALESCE(t.fills, 0)          AS fills,
       COALESCE(t.filled_notional, 0) AS filled_notional,
       (SELECT as_of FROM params)   AS as_of          -- data cut; the skill uses it to mark the partial month
FROM spine s
LEFT JOIN cohort c     USING (partner_id, month)
LEFT JOIN funded_new fn USING (partner_id, month)
LEFT JOIN money m      USING (partner_id, month)
LEFT JOIN jnl j        USING (partner_id, month)
LEFT JOIN trading t    USING (partner_id, month)
ORDER BY 1, 2
