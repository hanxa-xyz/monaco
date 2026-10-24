import pandas as pd

from monaco.io import load, parse_cols
from monaco.readout import CLOSE_KEYS, md_table, render_close, write_readout


def test_parse_cols_maps_input_to_contract():
    assert parse_cols('account_id=acct,partner_id=corr') == {'acct': 'account_id', 'corr': 'partner_id'}
    assert parse_cols('') is None and parse_cols(None) is None


def test_load_csv_with_mapping(tmp_path):
    p = tmp_path / 'e.csv'
    pd.DataFrame({'acct': [1, 2], 'corr': ['A', 'B'], 'stage': ['created', 'created'], 'event_time': ['2026-01-01', '2026-01-02']}).to_csv(p, index=False)
    df = load(csv=p, cols=parse_cols('account_id=acct,partner_id=corr,event=stage,ts=event_time'))
    assert list(df.columns) == ['account_id', 'partner_id', 'event', 'ts']


def test_load_duckdb_sql_text(tmp_path):
    import duckdb
    db = tmp_path / 'x.duckdb'
    con = duckdb.connect(str(db)); con.execute('CREATE TABLE t AS SELECT 1 AS a UNION ALL SELECT 2'); con.close()
    assert load(db=db, sql='SELECT COUNT(*) AS n FROM t').n.iloc[0] == 2


def test_md_table_roundtrip():
    df = pd.DataFrame({'k': ['x', 'y'], 'v': [1.23456, 1234.5]})
    out = md_table(df)
    assert out.splitlines()[0] == '| k | v |'
    assert '1.235' in out and '1,234' in out


def test_close_never_silently_drops_a_line(tmp_path):
    close = {'headline': '35% reach first trade in 30d', 'action': '[draft] split KYCD by cohort'}
    rendered = render_close(close)
    for k in CLOSE_KEYS:
        assert ('[TODO]' in rendered) if k not in close else True
    assert rendered.count('[TODO]') == 3
    p = write_readout(tmp_path / 'r.md', 'T', [('Inputs', 'one row per account'), ('Table', pd.DataFrame({'a': [1]}))], close)
    text = p.read_text()
    assert text.startswith('# T') and '## Close' in text and '| a |' in text
