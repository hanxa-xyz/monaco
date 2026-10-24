-- Partner x account roll-up for concentration views. Grain = one row per live account.
-- Contract: account_id, partner_id, funded (0/1), net_deposits, fills, filled_notional
WITH live AS (
    SELECT id AS account_id, correspondent AS partner_id FROM accounts WHERE status <> 'PAPER_ONLY'
),
money AS (
    SELECT account_id,
           SUM(CASE WHEN direction = 'INCOMING' THEN amount ELSE -amount END) AS net_deposits
    FROM transfers WHERE status = 'COMPLETE' GROUP BY 1
),
jnl AS (
    SELECT to_account AS account_id, SUM(net_amount) AS journal_in
    FROM journals WHERE entry_type = 'JNLC' AND status IN ('executed', 'activity_created') GROUP BY 1
),
trading AS (
    SELECT account_id, COUNT(*) AS fills, SUM(qty * price) AS filled_notional
    FROM activities WHERE activity_type = 'FILL' GROUP BY 1
)
SELECT l.account_id, l.partner_id,
       CASE WHEN COALESCE(m.net_deposits, 0) + COALESCE(j.journal_in, 0) > 0 OR m.account_id IS NOT NULL OR j.account_id IS NOT NULL THEN 1 ELSE 0 END AS funded,
       COALESCE(m.net_deposits, 0) + COALESCE(j.journal_in, 0) AS net_deposits,
       COALESCE(t.fills, 0)           AS fills,
       COALESCE(t.filled_notional, 0) AS filled_notional
FROM live l
LEFT JOIN money m   USING (account_id)
LEFT JOIN jnl j     USING (account_id)
LEFT JOIN trading t USING (account_id)
