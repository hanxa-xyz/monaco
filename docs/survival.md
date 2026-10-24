# Survival analysis — time-to-event with censoring

## When
Any "how long until" question where some entities have not had the event yet at the time you look: time to
churn, to first order, to first trade, to KYC approval, to repayment. A cohort table answers "what share by day
30" only for closed cohorts; Kaplan-Meier answers it for all of them, including the ones still running.

## The contract (`monaco.survival`)
| column | meaning |
|---|---|
| `duration` | time from t0 to the event, or to the end of observation if the event has not happened |
| `event` | 1 = event at `duration`; 0 = censored (still at risk when observation stopped) |
| `group` | optional split |

`from_timestamps(df, start, end, as_of, group)` builds it: `end` null or after `as_of` ⇒ censored at `as_of`.
Settle t0, the event and as_of **before** computing anything; the event definition is the whole analysis.

## What the estimator does
At each event time t: Ŝ(t) ← Ŝ(t⁻) · (1 − d/n), d = events at t, n = at risk just before t. Censored entities
leave the risk set without counting as events. That single rule is what a naive cohort read gets wrong in one
of two directions: dropping censored entities biases survival down ("closed cohort only"), counting them as
survivors biases it up. `naive_vs_km()` shows both gaps at the marks; they grow with the censored share, i.e.
with how recent the cohort is.

- **CI**: Greenwood variance, interval on the log(−log S) scale so it stays in [0, 1].
- **Median**: first t with S ≤ 0.5; report "not reached" when the curve never crosses.
- **RMST to τ**: area under S up to τ; the honest average lifetime when the median is not reached.
- **Peak-hazard window**: the interval with the largest drop in S; where an onboarding / save intervention lands.
- **Thin tail**: shaded where n at risk < 10; the band balloons and the curve is early entrants only. Don't read it.
- **Log-rank**: tests whether k curves are the same; association, not causation (groups self-select).

## What it assumes
Non-informative censoring: being censored (recent, or lost to follow-up) does not predict the event. The usual
violation: entities that stop sending data *because* they churned. Say the assumption once per readout and name
the plausible violation.

## What it is not
- Not causal. "Adopters survive longer" is selection until a design (holdout, DiD, matching) says otherwise.
- Not competing risks. If an entity can exit two ways (graduated vs churned), treating one as censoring
  overstates survival from the other; say which exit is the event and that the simplification is known.
- Not a covariate model. Cox proportional hazards is the next step for "controlling for"; check PH before
  reading a hazard ratio.

## Reading order for a readout
S at the marks → median / RMST → the slope (peak hazard) → by-group with log-rank → the close.
