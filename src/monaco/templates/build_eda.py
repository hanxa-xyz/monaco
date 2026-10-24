"""Template: generate AND execute an EDA notebook (the Faire EDA.ipynb architecture).

Never hand-edit the .ipynb — edit this builder and re-run. Any failing cell fails the build, so
the notebook can never ship stale or broken. Every analytical cell should print() its underlying
table so the notebook is auditable without a re-run.

ESCAPING (the trap): cell sources below are plain (non-f) triple-quoted strings — {} need no
doubling, but \\n and \\$ must stay escaped or THIS file's parser consumes them. Verify with repr()
after any sweep.
"""
import os

from monaco.viz import build_and_execute, code, md, new_notebook

nb = new_notebook()
C = nb.cells

C.append(md("""# <Company> — EDA & Chart Library
**Backup notebook for the submission document.** Structure: **1** load -> **2** shape -> **3** summary
stats -> **4** what we learned about the data -> **5** definitions & cutoffs -> **6** chart library."""))

C.append(md("""## 1 · Loading data"""))
C.append(code("""import warnings; warnings.filterwarnings('ignore')
import pandas as pd, numpy as np
import matplotlib.pyplot as plt
import matplotlib.ticker as mtick
from monaco.viz import BLACK, O_DARK, O_MID, O_LIGHT, O_PALE, GRAY, RAMP4, WY, apply_style, titled
apply_style(dpi=110)
pd.set_option('display.width', 200)

# df = pd.read_csv('../data/...')
# print('shape:', df.shape)"""))

C.append(md("""## 2 · Shape of the data
Entity grain FIRST: what is one row? Verify with nunique() on candidate keys before anything else."""))
C.append(code("""# print(df.dtypes)
# print('rows:', len(df), '| distinct <KEY>:', df.<KEY>.nunique())   # grain check
# nulls, dupes, date ranges, join integrity / orphan checks"""))

C.append(md("""## 3 · Summary stats"""))
C.append(code("""# df.describe(percentiles=[.25,.5,.75,.99])"""))

C.append(md("""## 4 · What we learned about the data
The non-obvious structural facts (multi-key rows, truncated dates, degenerate categories...)."""))

C.append(md("""## 5 · Definitions & cutoffs
Every metric definition printed live from the data, not asserted."""))

C.append(md("""## 6 · Chart library"""))

build_and_execute(nb, os.path.join(os.path.dirname(os.path.abspath(__file__)), 'EDA.ipynb'))
