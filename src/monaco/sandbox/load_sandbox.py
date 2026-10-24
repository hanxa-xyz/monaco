"""load_sandbox — materialise the Alpaca Broker API object model into a local DuckDB file.

    monaco-sandbox                 # synthetic (default)
    monaco-sandbox --mode live     # needs ALPACA_BROKER_API_KEY / _SECRET
    monaco-sandbox --seed 11 --accounts 20000 --out /tmp/x.duckdb

Tables (schema.sql, real field names + ENUM-enforced values): partners, accounts, account_status_events, orders,
positions, activities, transfers, journals. Live mode pulls from https://broker-api.sandbox.alpaca.markets with
basic auth and maps the JSON onto the same schema; it is written against the public reference and has NOT been
run against real credentials from this machine. Anything the live sandbox lacks (partner table, status history
beyond what /v1/events returns) is left empty rather than invented. Nothing here touches production.
"""
from __future__ import annotations

import argparse
import os
import time
from pathlib import Path

import duckdb
import pandas as pd

from monaco.paths import SCHEMA_SQL, default_db
from monaco.sandbox import synth

HERE = Path(__file__).resolve().parent
TABLE_ORDER = ['partners', 'accounts', 'account_status_events', 'orders', 'positions', 'activities', 'transfers', 'journals']


# ------------------------------------------------------------------ live sandbox (optional)
def fetch_live(base='https://broker-api.sandbox.alpaca.markets', max_accounts=500):
    import requests
    key, sec = os.environ.get('ALPACA_BROKER_API_KEY'), os.environ.get('ALPACA_BROKER_API_SECRET')
    if not (key and sec):
        raise SystemExit('live mode needs ALPACA_BROKER_API_KEY and ALPACA_BROKER_API_SECRET in the environment')
    s = requests.Session(); s.auth = (key, sec)

    def get(path, **params):
        r = s.get(base + path, params=params, timeout=30); r.raise_for_status(); return r.json()

    accounts = pd.json_normalize(get('/v1/accounts'))[:max_accounts]
    acc_ids = accounts['id'].tolist()
    orders, positions, transfers = [], [], []
    for i, aid in enumerate(acc_ids):
        orders += get(f'/v1/trading/accounts/{aid}/orders', status='all', limit=500)
        positions += [dict(p, account_id=aid) for p in get(f'/v1/trading/accounts/{aid}/positions')]
        transfers += get(f'/v1/accounts/{aid}/transfers')
        if i % 25 == 0:
            print(f'  accounts fetched: {i + 1}/{len(acc_ids)}'); time.sleep(0.2)
    acts, token = [], None
    while True:
        page = get('/v1/accounts/activities', page_size=1000, **({'page_token': token} if token else {}))
        acts += page
        if len(page) < 1000:
            break
        token = page[-1]['id']
    journals = get('/v1/journals')
    frames = {
        'partners': pd.DataFrame(columns=['correspondent', 'partner_name', 'partner_type', 'country', 'onboarded_at', 'kyc_flow', 'instant_funding']),
        'accounts': accounts.rename(columns={'kyc_results.summary': 'kyc_summary'}).assign(correspondent=os.environ.get('ALPACA_CORRESPONDENT', 'SBOX')),
        'account_status_events': pd.DataFrame(columns=['event_id', 'account_id', 'account_number', 'at', 'status_from', 'status_to', 'reason']),
        'orders': pd.DataFrame(orders), 'positions': pd.DataFrame(positions), 'activities': pd.DataFrame(acts),
        'transfers': pd.DataFrame(transfers), 'journals': pd.DataFrame(journals),
    }
    if 'enabled_assets' not in frames['accounts']:
        frames['accounts']['enabled_assets'] = [['us_equity']] * len(frames['accounts'])
    return frames


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
            if types[c] in ('TIMESTAMP', 'DATE'):                               # live JSON strings / mixed NaT -> datetime
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
    ap.add_argument('--mode', choices=['synthetic', 'live', 'auto'], default='auto',
                    help='auto = live if ALPACA_BROKER_API_KEY is set, else synthetic')
    ap.add_argument('--out', default=None, help='DuckDB path (default: $MONACO_DATA/alpaca_sandbox.duckdb)')
    ap.add_argument('--seed', type=int, default=7)
    ap.add_argument('--partners', type=int, default=36)
    ap.add_argument('--accounts', type=int, default=40000, help='target number of accounts (Poisson around it)')
    ap.add_argument('--start', default='2025-04-01')
    ap.add_argument('--as-of', default='2026-10-22')
    a = ap.parse_args()
    a.out = a.out or str(default_db())
    mode = a.mode if a.mode != 'auto' else ('live' if os.environ.get('ALPACA_BROKER_API_KEY') else 'synthetic')
    t0 = time.time()
    if mode == 'live':
        print('mode: live sandbox (broker-api.sandbox.alpaca.markets)')
        frames = fetch_live(); frames['_mode'] = 'live'
    else:
        print(f'mode: synthetic  seed={a.seed} partners={a.partners} accounts≈{a.accounts:,} window {a.start} → {a.as_of}')
        frames = synth.generate(seed=a.seed, n_partners=a.partners, n_accounts=a.accounts, start=a.start, as_of=a.as_of)
        frames['_mode'] = 'synthetic'
    print(f'generated in {time.time() - t0:.1f}s; loading → {a.out}')
    con = load(frames, a.out)
    report(con, a.as_of)
    con.close()
    print(f'\nOK  {a.out}  ({time.time() - t0:.1f}s)')


if __name__ == '__main__':
    main()
