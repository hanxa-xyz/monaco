---
name: takehome-sizing
description: Opportunity sizing discipline for take-home recommendations — EV anchors, dials instead of point estimates, causal haircuts, annualization, corroboration by two routes, break-even framing. Use when sizing a recommendation or reviewing someone's sizing.
user-invocable: true
---

# /takehome-sizing — pricing a recommendation honestly

Sizings built here survived a reviewer who cut every recommendation that offered point estimates.
The acceptable form is **explicit dials, stated assumptions, one narrative number**.

## The canonical sizing shape
`Incremental value = N × c × (T − A)` — pool size × conversion dial × per-unit value gap. Present it so
only one column moves with the dial (that's why the answer scales exactly linearly — and prove linearity
on a numeric axis with origin lines when charted).

## Rules
1. **Dials, not point estimates.** Conversion at 10/25/50/75/100% with the realistic band (10–25%) shaded;
   a stated causal haircut (50% is the house default) as a second, separate discount. Label the compound
   honestly ("captured AND converted").
2. **EV anchor first.** Establish what one converted unit is worth (e.g. one manufactured 90-day repeater),
   then keep the RATE ($ per pp) separate from the OPPORTUNITY SIZE ($m for a named pool).
3. **Corroborate by two independent routes** and state the gap (Faire: observed repeater-vs-non gap $21,427
   vs Premier-conversion model $21,155 — 1.3% apart). Agreement says the anchor isn't an artifact of its
   construction. Both stay labeled correlational upper bounds.
4. **Prefer the conservative estimator and show the pair.** Weighted (within-stratum, composition-controlled)
   imputation vs unweighted; report both, headline the conservative one, explain the gap.
5. **Count overlaps once.** Populations defined by unions (missing field A ∪ missing field B) must impute
   the joint cell from the full known grid — answer the double-count question before it's asked.
6. **Annualise intake, not time.** A 2-month cohort × 6 = a year of signups; give the comparable denominator
   (×6 cohort GMV, not this extract's GMV) or the number reads as absurd.
7. **What-if sensitivity table**: +1/+3/+5pp on the anchor metric → units → $, labeled correlational EV
   anchor, haircut dial welcome.
8. **Endogenous levers are findings, not recommendations.** If treatment is assigned on expected outcome
   (credit terms, self-selected app installs), say the extract cannot separate treatment from selection,
   name the data that would settle it, name the prerequisite lever — and add a "levers considered and
   deprioritized" box so the choice reads as deliberate.
9. **Break-even framing for risk levers**: (take-rate × ΔEV) ÷ exposure = break-even default rate, compared
   to industry norms — gives the risk owner a threshold to stress rather than a promise.
10. **Sub-recommendation template** (each bolded on its own line):
    `Hypothesis / Goal / Test structure (with a Guardrail) / Opportunity sizing / Mechanism`.
11. Phrase non-pejoratively: "credit the retailers who already match credit-receiving profiles," never
    "make X look like Y." Tiers get neutral names (Premier/Base, never "whales").
