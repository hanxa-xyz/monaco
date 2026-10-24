"""paths — where generated data and outputs live. Nothing in the package writes anywhere else.

    MONACO_DATA   directory for DuckDB files and downloaded inputs   (default: ./data)
    MONACO_OUT    directory for figures, tables and readouts         (default: ./out)

Both default relative to the current working directory so a `git pull` of this repo works with no setup;
set the environment variables to point elsewhere.
"""
import os
from pathlib import Path

PKG = Path(__file__).resolve().parent
SQL_DIR = PKG / 'sandbox' / 'sql'
SCHEMA_SQL = PKG / 'sandbox' / 'schema.sql'
ASSETS = PKG / 'assets'
TEMPLATES = PKG / 'templates'


def data_dir() -> Path:
    p = Path(os.environ.get('MONACO_DATA', Path.cwd() / 'data'))
    p.mkdir(parents=True, exist_ok=True)
    return p


def out_dir(*sub) -> Path:
    p = Path(os.environ.get('MONACO_OUT', Path.cwd() / 'out')).joinpath(*sub)
    p.mkdir(parents=True, exist_ok=True)
    return p


def default_db() -> Path:
    return data_dir() / 'sandbox.duckdb'
