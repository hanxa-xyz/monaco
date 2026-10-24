---
name: takehome-charts
description: The house chart grammar — palette semantics, penetration-horizontal vs distribution-vertical, value labels, how-to-read blocks, footnotes as HTML, thin-cell muting. Load before building any figure for a take-home; use when the user asks for standardized charts or chart review.
user-invocable: true
---

# /takehome-charts — the visual grammar

Everything imports from `src/monaco/viz.py` (`from monaco import viz`). Never re-declare palette constants in a notebook or script
(they were hand-copied ~250 times across repos before consolidation; that ends here).

## Palette semantics
- `BLACK` = hero series, totals, the top tier. Orange ramp `O_PALE → O_LIGHT → O_MID → O_DARK` = ordered
  magnitude; pale = baseline/"neither". `GRAY` = reference lines. One hue + black; never blue.
- Heatmaps that price things: `WY` white→yellow, deliberately outside the house orange so they read as a
  different object.

## The two chart kinds (fixed labels, never per-chart variants)
- **Penetration — HORIZONTAL bars.** "Of a group, what share does the thing." Label:
  `N split within group (penetration)`. Pairs sum to 100% within a category.
- **Distribution — VERTICAL bars.** "Of a total, how it splits across groups." Label:
  `share of each population (distribution)`. Each series sums to 100% across the row.
- A segment can have a high rate and a small share, or the reverse — that's why both exist.

## Non-negotiables per figure
1. `titled(ax, title, subtitle)` — bold left title + gray definitional subtitle.
2. Direct value label on every bar; n= counts in tick labels, e.g. `(repeaters / non-repeaters)`.
3. Footnote via `save_fig(fig, name, footnote_text=...)` — renders as selectable HTML under the chart,
   never `fig.text` into the PNG. Escape `<` as `&lt;` (raw HTML).
4. Every non-obvious chart gets a `How to read:` block with one worked example.
5. Mute cells with n < `dsviz.MIN_CELL_N` (grey text) AND exclude them from any shared color scale.
6. Twin panels comparing populations share ONE color scale; the caption must say a near-white panel is
   the finding, not a rendering bug.
7. One shared category grouping per dimension across all charts (top-6 + "Else" for 100% coverage),
   except where "Else" is not actionable — then raw categories at min_n≥100/200, stated.
8. Dials/percent axes that are linear: use a TRUE numeric x-axis (categorical spacing bends straight lines).
9. **Read the rendered PNG before calling any chart done** — collisions are only caught by looking.
10. After trimming or swapping rows: rewrite the how-to (grep `Row [123]`), re-check every claim the old
    content supported, keep `squeeze=False` on subplots.

## Naming
"total GMV", "GMV per X" — never "avg GMV"/"total lifetime GMV". State the observation window once in the
assumptions box, not in every axis label.
