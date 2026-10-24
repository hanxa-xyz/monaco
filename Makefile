.PHONY: setup test lint sandbox funnel health demo skills clean

PY ?= python3

setup:            ## editable install with everything
	$(PY) -m pip install -e ".[all]"

test:             ## unit tests (fast; no DuckDB file needed)
	$(PY) -m pytest

lint:
	$(PY) -m ruff check src tests

sandbox:          ## build the synthetic platform DuckDB under ./data
	monaco-sandbox

funnel:           ## account funnel + cohort retention readout under ./out/funnel
	monaco-funnel

health:           ## partner concentration, trends, early-warning flags under ./out/partner_health
	monaco-partner-health

demo: sandbox funnel health   ## the whole thing, end to end, from a clean checkout

skills:           ## link ./skills into ~/.claude/skills so every project sees them
	scripts/install_skills.sh

clean:
	rm -rf out data/*.duckdb data/*.wal .pytest_cache .ruff_cache
	find . -name __pycache__ -type d -prune -exec rm -rf {} +
