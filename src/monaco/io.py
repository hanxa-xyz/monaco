"""io — get a DataFrame onto a column contract from DuckDB + SQL, CSV or parquet.

The analytics modules read a fixed set of column names (the contract). Everything upstream of those
names is the SQL file's or the --cols mapping's problem, never the module's.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from monaco.paths import default_db


def load(db=None, sql=None, csv=None, cols=None, parquet=None):
    """Return a DataFrame from (DuckDB file + SQL file-or-text) or from a CSV/parquet.
    `cols` renames input columns onto the contract, e.g. {'acct_uuid': 'account_id'}."""
    if csv:
        df = pd.read_csv(csv)
    elif parquet:
        df = pd.read_parquet(parquet)
    else:
        import duckdb
        q = Path(sql).read_text() if sql and Path(str(sql)).exists() else sql
        if not q:
            raise SystemExit('load() needs --sql (file or text) when reading from DuckDB')
        con = duckdb.connect(str(db or default_db()), read_only=True)
        try:
            df = con.execute(q).fetchdf()
        finally:
            con.close()
    if cols:
        df = df.rename(columns=cols)
    return df


def parse_cols(spec):
    """'account_id=acct,partner_id=corr' -> {'acct': 'account_id', 'corr': 'partner_id'} (input -> contract)."""
    if not spec:
        return None
    out = {}
    for kv in spec.split(','):
        k, v = kv.split('=')
        out[v.strip()] = k.strip()
    return out
