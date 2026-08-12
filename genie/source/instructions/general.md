# General instructions

> **Source ID:** `c3f38aef0fce47dfaf0f0d489c55a101`

This space analyzes contact-center new-hire ramp performance through governed, pseudonymous agent identifiers. The bundled demo is fully fictional; customer deployments must preserve the same privacy boundary.

## Source routing

- Use `workspace.contact_center_gold.mv_new_hire_kpi_daily` for daily agent performance, tenure progression, targets, sigma bands, volume reliability, channel, language, market, and site questions.
- Use `workspace.contact_center_gold.mv_learning_curve_best` for selected model, R-squared, milestone prediction, MLflow lineage, interpretation, and days-to-target questions.
- Use `workspace.contact_center_gold.mv_cohort_scorecard` for cohort rankings and compact cross-cohort comparisons.
- Use `workspace.contact_center_gold.mv_sigma_band_comparison` for comparison with tenured one-, two-, and three-sigma benchmarks.
- Use `workspace.contact_center_gold.mv_kpi_forecast` for actual-versus-Prophet-forecast monthly trend questions.

## KPI directionality

- `normal = 1` means higher is better. A score meets target when `agent_score >= target`.
- `normal = -1` means lower is better. A score meets target when `agent_score <= target`.
- Never rank AHT or ACW as if higher were better.

## Grain and aggregation

- `mv_new_hire_kpi_daily` is one row per new-hire agent, KPI, and performance date. Aggregate scores as `SUM(nominator) / NULLIF(SUM(denominator), 0)`, never as an unweighted average of `agent_score`.
- A new hire has `is_new_hire = true` or `tenure_day <= 90`.
- For week-of-ramp analysis, group by `tenure_week`, not calendar week.
- `mv_learning_curve_best` already contains only the selected model per cohort and KPI. Do not add a second model-ranking layer.
- `mv_kpi_forecast` contains historical actuals and future Prophet forecasts. Filter `is_actual = false` for future-only questions.
- `target_1_sigma`, `target_2_sigma`, and `target_3_sigma` are direction-aware. For `normal = -1`, smaller scores are better even though the numerical band boundary is higher.
- Use `below_1_sigma = true` for cohorts on the adverse side of the direction-aware one-sigma boundary.
- `volume_bin = 1` represents the lowest-volume quartile and therefore the least reliable agent-level observations.

## Filtering and output

- Use `ILIKE '%value%'` for text filters.
- Include every filtered dimension in the SELECT output.
- Use bounded half-open date windows for date filters.
- Show percentage KPIs as percentages and AHT, ACW, and Hold Time in seconds.
- Treat R-squared below 0.30 as inconclusive.
