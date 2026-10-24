"""load_sandbox — materialise the synthetic B2B2C brokerage-platform dataset into a local DuckDB file.

    monaco-sandbox                                            # default: 36 partners, ~47k accounts
    monaco-sandbox --seed 11 --accounts 20000 --out /tmp/x.duckdb

Tables (schema.sql; enum values enforced with DuckDB ENUM types): partners, accounts, account_status_events, orders,
positions, activities, transfers, journals. The shape is a generic embedded-brokerage platform: partners embed
trading for their end users, accounts go through KYC, fund by transfer or journal, and trade (orders -> FILL
activities). Four partner stories are planted so the analytics have something to find (see synth.py). Everything is
synthetic; nothing here reads from or writes to any external system.
"""
from __future__ import annotations

import argparse
import time
from pathlib import Path

import duckdb
import pandas as pd

from monaco.paths import SCHEMA_SQL, default_db
from monaco.sandbox import synth

HERE = Path(__file__).resolve().parent
TABLE_ORDER = ['partners', 'accounts', 'account_status_events', 'orders', 'positions', 'activities', 'transfers', 'journals']


# ------------------------------------------------------------------ load
def load(frames, db_path, schema_path=SCHEMA_SQL):
    db_path = Path(db_path)
    if db_path.exists():
        db_path.unlink()
    con = duckdb.connect(str(db_path))
    con.execute(schema_path.read_text())
    for t in TABLE_ORDER:
        df = frames[t]
        desc = con.execute(f'DESCRIBE {t}').fetchall()
        cols, types = [r[0] for r in desc], {r[0]: r[1] for r in desc}
        df = df.reindex(columns=cols).copy()                                    # missing columns -> NULL, extras dropped
        for c in df.columns:
            if types[c] in ('TIMESTAMP', 'DATE'):                               # strings / mixed NaT -> datetime
                df[c] = pd.to_datetime(df[c], errors='coerce', utc=True).dt.tz_localize(None)
            elif types[c] == 'DOUBLE':
                df[c] = pd.to_numeric(df[c], errors='coerce')
            elif df[c].dtype == object:                                         # numpy NaT/NaN -> None so DuckDB casts cleanly
                df[c] = df[c].where(pd.notna(df[c]), None)
        con.register('src', df)
        con.execute(f'INSERT INTO {t} BY NAME SELECT * FROM src')
        con.unregister('src')
    con.execute(f"CREATE OR REPLACE VIEW v_meta AS SELECT '{pd.Timestamp.now().isoformat()}' AS loaded_at, '{frames.get('_mode', 'synthetic')}' AS mode")
    return con


def report(con, as_of):
    print(f'\nLOAD REPORT  (as_of {as_of})')
    print(f"{'table':24s}{'rows':>10s}  date range")
    ranges = {'accounts': 'created_at', 'account_status_events': '"at"', 'orders': 'created_at', 'activities': 'COALESCE(transaction_time, date::TIMESTAMP)',
              'transfers': 'created_at', 'journals': 'created_at'}
    for t in TABLE_ORDER:
        n = con.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]
        rng = ''
        if t in ranges and n:
            lo, hi = con.execute(f'SELECT MIN({ranges[t]})::DATE, MAX({ranges[t]})::DATE FROM {t}').fetchone()
            rng = f'{lo} → {hi}'
        print(f'{t:24s}{n:>10,}  {rng}')
    for t, c in [('accounts', 'status'), ('orders', 'status'), ('activities', 'activity_type'), ('transfers', 'status'), ('journals', 'status')]:
        vc = con.execute(f'SELECT {c}, COUNT(*) n FROM {t} GROUP BY 1 ORDER BY 2 DESC').fetchall()
        print(f'-- {t}.{c}: ' + ', '.join(f'{k}={v:,}' for k, v in vc))
    grain = con.execute("""
        SELECT (SELECT COUNT(*) FROM accounts) = (SELECT COUNT(DISTINCT id) FROM accounts) AS accounts_is_grain,
               (SELECT COUNT(*) FROM orders)   = (SELECT COUNT(DISTINCT id) FROM orders)   AS orders_is_grain,
               (SELECT COUNT(*) FROM activities WHERE order_id IS NOT NULL) AS fill_rows,
               (SELECT COUNT(DISTINCT order_id) FROM activities WHERE order_id IS NOT NULL) AS filled_orders,
               (SELECT COUNT(*) FROM accounts a WHERE NOT EXISTS (SELECT 1 FROM partners p WHERE p.correspondent = a.correspondent)) AS orphan_accounts
    """).fetchdf().iloc[0]
    print('-- grain: ' + ', '.join(f'{k}={v}' for k, v in grain.items()))
    print('-- fills (FILL activities) per filled order > 1 is normal: partial fills are separate rows.')


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--out', default=None, help='DuckDB path (default: $MONACO_DATA/sandbox.duckdb)')
    ap.add_argument('--seed', type=int, default=7)
    ap.add_argument('--partners', type=int, default=36)
    ap.add_argument('--accounts', type=int, default=40000, help='target number of accounts (Poisson around it)')
    ap.add_argument('--start', default='2025-04-01')
    ap.add_argument('--as-of', default='2026-10-22')
    a = ap.parse_args()
    a.out = a.out or str(default_db())
    t0 = time.time()
    print(f'synthetic  seed={a.seed} partners={a.partners} accounts≈{a.accounts:,} window {a.start} → {a.as_of}')
    frames = synth.generate(seed=a.seed, n_partners=a.partners, n_accounts=a.accounts, start=a.start, as_of=a.as_of)
    frames['_mode'] = 'synthetic'
    print(f'generated in {time.time() - t0:.1f}s; loading → {a.out}')
    con = load(frames, a.out)
    report(con, a.as_of)
    con.close()
    print(f'\nOK  {a.out}  ({time.time() - t0:.1f}s)')


if __name__ == '__main__':
    main()
