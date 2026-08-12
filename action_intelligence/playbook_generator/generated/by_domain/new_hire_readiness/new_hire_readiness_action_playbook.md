# New-Hire Readiness Operating Playbook

## Target attainment, learning confidence, sigma exceptions, and forecast response

*(All programs, cohorts, agents, and observations are deterministic synthetic data.)*

---

## 1) KPI Reference and How to Interpret Shifts

Use this playbook after the governed metrics identify a material readiness gap. It defines what to verify, how to triage, and which measurable response is appropriate without overstating correlation as causation.

**KPIs covered**

- static_target_attainment_rate : Direction-aware share of new-hire observations meeting the production target.
- days_to_target : Modeled tenure day at which the selected curve reaches the static target.
- best_model_r_squared : Fit-quality context for deciding whether a learning-curve conclusion is reliable.
- sigma_boundary_attainment : Cohort performance relative to direction-aware tenured one, two, and three-sigma boundaries.
- forecast_interval : Six-month Prophet outlook with an 80 percent uncertainty interval.

**General interpretation rules**

- Weight KPI scores with raw numerators and denominators; never average agent percentages.
- Treat AHT, ACW, and Hold Time as lower-is-better; all other published KPIs are higher-is-better.
- Treat R-squared below 0.30 as inconclusive and avoid target-date commitments.
- Pair performance conclusions with volume quartile and distinct-agent context.
- Use forecasts for planning scenarios, not causal claims or guaranteed outcomes.
- Grain context: date column: `performance_date`.
- Common filters include service_program, cohort_id, cohort_name, kpi.
- Preserve weighted KPI math
- Respect KPI direction
- Gate weak learning curves
- Carry reliability context
- Treat forecasts as scenarios

## 2) Scenario Playbooks (Symptoms -> Likely Causes -> Action Plans)

### Scenario A - Material target-attainment gap after day 60

**Symptoms**

- Static target attainment remains below the program median between tenure days 55 and 60.
- The gap appears across multiple volume quartiles rather than only the lowest-volume observations.

**Likely causes**

- Training content or nesting support may not match the production KPI mix.
- One channel, language, or site may be driving a broader cohort average.

**Action plan recommendations**

1. Immediate actions (24-48 hours)
   - Validate denominator coverage and direction-aware target logic.
   - Segment the cohort by site, channel, language, and volume quartile.
   - Compare the same KPI with the prior fictional cohort and tenured benchmark.

2. Short-term actions (1-2 weeks)
   - Assign targeted coaching to the confirmed driver segment.
   - Review training examples for the affected KPI and channel.
   - Track daily recovery against both training and static targets.

**Measurement targets**

- Improve static target attainment without degrading paired quality or customer KPIs.
- Reduce the cohort gap to the one-sigma tenured boundary.

### Scenario B - Slow or inconclusive learning curve

**Symptoms**

- Days to target is late or null.
- The selected model has R-squared below 0.30 or materially disagrees with other candidates.

**Likely causes**

- The cohort may have insufficient history, high variance, or a structural process change.
- A single curve family may not represent the observed ramp pattern.

**Action plan recommendations**

1. Immediate actions (24-48 hours)
   - Review all four candidate fits and observation coverage.
   - Check whether low-volume days or outliers drive model selection.
   - Label the conclusion inconclusive when the confidence gate fails.

2. Short-term actions (1-2 weeks)
   - Collect additional tenure history before committing to a target date.
   - Investigate training or operating changes aligned with curve breaks.

**Measurement targets**

- Increase reliable observation coverage and model fit before operationalizing days to target.

### Scenario C - Direction-aware sigma exception

**Symptoms**

- A cohort falls outside the one-sigma tenured boundary in the unfavorable direction.
- The exception persists across consecutive periods or reaches the two-sigma boundary.

**Likely causes**

- Ramp support may be insufficient for the affected KPI.
- A program-specific mix shift may make the tenured comparator less representative.

**Action plan recommendations**

1. Immediate actions (24-48 hours)
   - Confirm KPI direction and the applicable tenured comparison window.
   - Check whether the exception is isolated to one cohort or shared across the program.

2. Short-term actions (1-2 weeks)
   - Set a cohort-specific recovery threshold and owner.
   - Review the benchmark definition if the operating mix changed materially.

**Measurement targets**

- Return inside the one-sigma boundary while preserving paired KPI guardrails.

### Scenario D - Forecasted readiness or staffing risk

**Symptoms**

- The forecast deteriorates in the unfavorable direction for multiple future periods.
- The 80 percent interval overlaps a planning threshold.

**Likely causes**

- Recent cohort mix or performance trend may be carrying into the forecast.
- Wide uncertainty may reflect limited or volatile monthly history.

**Action plan recommendations**

1. Immediate actions (24-48 hours)
   - Separate the point forecast from its lower and upper interval.
   - Compare forecast direction with current target attainment and cohort mix.

2. Short-term actions (1-2 weeks)
   - Build base, downside, and upside staffing scenarios.
   - Refresh the forecast after the next complete period and monitor interval width.

**Measurement targets**

- Maintain a documented staffing response for the downside interval, not only the point estimate.

## 3) Recommendation Templates (Vector-Friendly Snippets)

These are short, reusable action cards designed for embedding and retrieval.

### Action Card: Readiness triage

Trigger: A cohort misses the day-60 target-attainment expectation.

**Actions:**

- Validate metric grain, direction, and denominator coverage.
- Rank driver segments by impact and reliability.
- Assign one owner, one recovery date, and paired KPI guardrails.

Expected impact: Converts a broad cohort gap into a measurable, evidence-backed intervention.

### Action Card: Model confidence gate

Trigger: A stakeholder asks for a target date from an inconclusive curve.

**Actions:**

- Show R-squared and all four candidate fits.
- State that the evidence is inconclusive below the 0.30 threshold.
- Request more history before committing to a date.

Expected impact: Prevents false precision in workforce planning.

## 4) Putting It Together: Example "Recommended Plan" Outputs

### Example Plan 1 (QA readiness lags while AHT improves)

Observed trend: A fictional cohort improves lower-is-better AHT but remains below QA target after day 60 with a reliable selected curve.

**Plan:**

- Validate the QA denominator and compare the cohort across volume quartiles.
- Prioritize coaching for the driver segment without setting an AHT-only incentive.
- Monitor QA target attainment, AHT, and CSAT together for two weeks.

Success metrics: QA target attainment and sigma position improve without materially worsening AHT or CSAT.
