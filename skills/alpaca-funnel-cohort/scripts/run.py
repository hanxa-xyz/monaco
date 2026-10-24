"""Thin wrapper: the analysis lives in monaco.cli_funnel (pip install -e . from the repo root).
Kept so the skill still runs as a script in a checkout where the console entry point is not on PATH."""
from monaco.cli_funnel import main

if __name__ == '__main__':
    main()
