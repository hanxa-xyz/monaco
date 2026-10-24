"""monaco — a data-science toolkit that enforces one house grammar for charts, EDA, modelling and readouts.

Modules
-------
viz             palette + chart grammar (titled, apply_style, save_fig/img, notebook helpers)
eda             the fixed EDA view vocabulary: structure · trio · penetration · mix · distribution · time · saturation · pareto
eda_build       SPEC dict -> one executed EDA notebook
modeling        RF + XGBoost exploratory pass with deterministic decisions and a leakage tripwire
model_build     SPEC dict -> one executed modelling notebook
stats           Wilson intervals and the two formatters (pct, money)
io              DuckDB / CSV / parquet loading with column mapping onto a contract
readout         table printing, markdown tables, PNG saving, and the readout writer that FORCES the close
funnel          stage funnel + cohort retention on a (entity_id, group_id, event, ts) event table
partner_health  concentration, trends and early-warning flags on a group x month table
sandbox         synthetic Broker-API-shaped data (real field names and enums) in DuckDB
paths           where data and outputs live (MONACO_DATA / MONACO_OUT)
"""
__version__ = '0.1.0'
