"""Template: self-contained HTML report builder (the Faire bang.html architecture).

Pattern: load data -> compute EVERY quoted stat into live variables -> render figures into
dsviz.FIGS -> emit one f-string HTML body -> wrap with monaco/assets/report.css -> write a single
self-contained file (all charts base64-inlined).

Standing rules while editing:
- The html_body is an f-string: single {} are live Python; double every literal brace.
- Hide, never delete: wrap cut content in <!-- HIDDEN: ...restore note... --> and strip img()
  calls inside so dead base64 doesn't bloat the file. HTML comments cannot nest — stash sections
  that contain hidden sub-blocks as plain (non-f) strings instead.
- Escape < as &lt; in prose/fignotes (raw HTML).
- End with self-verifying prints: figure count + every headline number.
- After each build: check figure count, regex for brace leaks, Read one extracted PNG.
"""
import os

from monaco import viz as dsviz
from monaco.viz import FIGS, apply_style

os.chdir(os.path.dirname(os.path.abspath(__file__)))     # repo-relative paths below
apply_style(dpi=150)

# ============ LOAD & COMPUTE (every number quoted below is computed here) ============
# df = pd.read_csv('data/...')
# n_entities = df.ID.nunique()

# ============ FIGURES ============
# fig, ax = plt.subplots(figsize=(9.5, 4.2))
# titled(ax, 'Title', 'Definition subtitle')
# save_fig(fig, 'f1', 'Footnote — becomes selectable HTML under the chart; escape < as &lt;.')

# ============ HTML ============
CSS = open(os.path.join(os.path.dirname(dsviz.__file__), 'report.css')).read()

html_body = """
<h1>Title</h1>
<p class="sub">Subtitle</p>

<h2>Context</h2>
<p><b>Goal:</b> ...</p>

<h2>Summary</h2>
<ol>
<li>...</li>
</ol>

<h2>Recommendations</h2>
<h3>Part 1 · Operational Adoption</h3>
<h3>Part 2 · Strategy and Experimentation</h3>
<div class="box"><b style="color:#b34212">Recommendation:</b> <b>...</b><br><br>
<b>Hypothesis:</b> ...<br><br>
<b>Goal:</b> ...<br><br>
<b>Test structure:</b> ... <b>Guardrail:</b> ...<br><br>
<b>Opportunity sizing:</b> dials, not point estimates.<br><br>
<b>Mechanism:</b> ...</div>

<h2>1 · ...</h2>
<div class="assume"><b>Assumptions (§1):</b> ...</div>

<h2>N · Follow-ups &amp; assumptions</h2>
"""

page = f"""<!DOCTYPE html><html><head><meta charset="utf-8"><title>Title</title>
<style>{CSS}</style></head><body>{html_body}</body></html>"""
with open('docs/report.html', 'w') as fh:
    fh.write(page)
print(f"report.html written: {os.path.getsize('docs/report.html')//1024} KB, figures: {len(FIGS)}")
# print every headline number here — the self-verification block
