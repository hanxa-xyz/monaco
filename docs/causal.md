# Causal inference — the ladder, the assumptions, the estimators here

Every method answers one question: *what would have happened without the change?* They differ only in what
assumption buys the missing counterfactual. A confounder (baseline engagement, tenure, size) drives both who
gets treated and the outcome; a naive treated-vs-untreated comparison adds that leak to the real effect.
Randomization breaks the confounder → treatment arrow; everything else blocks it (adjust / weight), differences
it out (DiD), finds a slice where it vanishes (RDD) or uses variation that does not run through it (IV).

## The ladder (strongest claim first — walk down until one fits)

| rung | question | method | assumption to defend | main pitfall | in `monaco.causal` |
|---|---|---|---|---|---|
| 1 | can you randomize it? | A/B test, holdout | proper randomization; no interference (SUTVA) | underpowered, peeking, novelty | `cuped()` for power |
| 2 | assigned by a cutoff? | regression discontinuity | continuity at the cutoff; no manipulation | effect local to the threshold; bunching | — |
| 3 | can you nudge uptake? | IV / encouragement | relevance; exclusion; monotonicity (→ LATE) | weak instruments; compliers only | — |
| 4 | one unit vs many controls? | synthetic control | good pre-fit; clean donors; no spillover | overfit pre-period; no donors | — |
| 5 | treated + control over time? | difference-in-differences, event study | parallel trends; no anticipation; stable composition | differential trends; staggered TWFE bias | `did()`, `event_study()` |
| 6 | confounders all measured? | IPW / propensity (→ doubly robust) | conditional ignorability; positivity / overlap | hidden confounders; extreme weights | `ipw()` |
| 7 | just before vs after? | interrupted time series | the pre-trend would have continued; no co-occurring shock | anything else that changed | `its()` |

`method_ladder(randomize=…, cutoff=…, nudge=…, one_unit_many_controls=…, panel_pre_post=…, confounders_measured=…, pre_post_only=…)`
returns the first rung answered yes. The ladder is a priority order, not a ranking of good vs bad; a lower rung can be the only option.

## Difference-in-differences (rung 5)

ATT = (Ȳ treated,post − Ȳ treated,pre) − (Ȳ control,post − Ȳ control,pre). The control's change is the read on
everything else that happened (seasonality, drift, macro); subtracting it leaves the effect. The dashed
counterfactual in `plot_did` is the treated pre-level plus the control's change.

- **Standard errors**: cluster bootstrap over units, resampled within arm so every draw keeps both arms. With a
  single treated unit the SE only reflects control noise; the CLI prints that caveat.
- **Event study** (`event_study`): coef_r = (T_r − C_r) − (T_ref − C_ref), ref = −1. Pre coefficients should sit
  on zero; a ramp means the groups were already diverging and the design is not identified. Joint pre-trend test
  via the bootstrap covariance, plus the magnitude rule (max |pre| < 25% of |ATT|) because the joint test is
  overpowered when SEs are tight.
- **Watch for**: composition shifts mid-window, anticipation, shocks hitting one arm, and staggered adoption
  (units treated at different dates): the 2x2 is biased there; use a staggered-aware estimator, do not pool.

## Selection on observables (rung 6)

`ipw()`: fit e(X) = P(treated | X) by logistic regression, weight (ATT: control by e/(1−e); ATE: 1/e and
1/(1−e)), stabilize so each arm's weights sum to its n, trim outside [0.01, 0.99]. Reports effective sample size,
max weight, and the balance table (standardized mean differences before/after; |SMD| < 0.10 is the usual bar).
Inspect `plot_overlap` first: where only one arm has mass there is nothing to compare, only extrapolation.
Doubly robust (AIPW) pairs the propensity model with an outcome model and is consistent if either is right;
prefer it when an outcome model is cheap.

## Variance reduction (rung 1 helper)

`cuped()`: θ = cov(y, y_pre) / var(y_pre); y_adj = y − θ (y_pre − mean). Shrinks the SE of a randomized test by
roughly (1 − ρ²); it detects smaller effects faster. It does not fix confounding and must not be presented as if it did.

## Last resort (rung 7)

`its()`: segmented regression y = a + b·t + c·post + d·post·(t − t0). Level change c, slope change d. No
control, so any co-occurring change is in the estimate; the readout says "weakest rung".

## Playbook notes
- **Bug-fix impact**: fixes ship to everyone at once. Best → worst: stage the rollout (recover a randomized or
  not-yet-treated comparison) → platform-gated bug, DiD with the other platform as control → global fix, ITS.
  Scope to users who hit the broken path; measuring everyone dilutes toward zero. The bug's damage may have been
  growing, so a flat pre/post understates it.
- **Cannibalization**: hold out a random slice and measure *both* the new surface and the products it might
  cannibalize in the same window; net incrementality = incremental value − value cannibalized. Never pre-season vs
  in-season; the control must be in-season too.
- **Marketing measurement stack**: attribution reports, response curves allocate, experiments adjudicate.
  Geo-lift / synthetic control calibrates an iROAS deflator per channel; allocate to equalize marginal, not
  average, return.

## Glossary
Parallel trends · conditional ignorability · positivity/overlap · SUTVA · exclusion restriction · monotonicity
(LATE) · continuity at the cutoff · ITT vs ATT · doubly robust. Definitions in the table above; the readout names
the one in play.
