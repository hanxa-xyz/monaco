-- Account funnel as a long event table: one row per (account, event, ts). Schema-agnostic contract for
-- /funnel-cohort: account_id, partner_id, event, ts. Rewrite this file for the real warehouse;
-- the skill never needs to change. DuckDB dialect; every construct here exists in Snowflake/BigQuery/Postgres.
--
-- Stage definitions (docs/contracts.md):
--   created       accounts.created_at (live accounts only; PAPER_ONLY excluded)
--   kyc_approved  first status transition to APPROVED or ACTIVE (Events API)
--   funded        first COMPLETE INCOMING transfer, or first executed JNLC into the account
--   trade         every FILL activity (the skill derives first_trade = MIN(trade) and monthly activity from it)
WITH live AS (
    SELECT id AS account_id, correspondent AS partner_id, created_at
    FROM accounts
    WHERE status <> 'PAPER_ONLY'
)
SELECT account_id, partner_id, 'created' AS event, created_at AS ts
FROM live

UNION ALL
SELECT e.account_id, l.partner_id, 'kyc_approved', MIN(e."at")
FROM account_status_events e
JOIN live l USING (account_id)
WHERE e.status_to IN ('APPROVED', 'ACTIVE')
GROUP BY 1, 2

UNION ALL
SELECT f.account_id, l.partner_id, 'funded', MIN(f.ts)
FROM (
    SELECT account_id, updated_at AS ts
    FROM transfers
    WHERE status = 'COMPLETE' AND direction = 'INCOMING'
    UNION ALL
    SELECT to_account AS account_id, created_at AS ts
    FROM journals
    WHERE entry_type = 'JNLC' AND status IN ('executed', 'activity_created')
) f
JOIN live l USING (account_id)
GROUP BY 1, 2

UNION ALL
SELECT a.account_id, l.partner_id, 'trade', a.transaction_time
FROM activities a
JOIN live l USING (account_id)
WHERE a.activity_type = 'FILL'
  -- AND a.qty * a.price > 10     -- the "> $10 fill" clause of the proposed active definition
