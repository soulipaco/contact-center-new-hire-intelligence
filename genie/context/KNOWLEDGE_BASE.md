# Knowledge Base

## Source Table

| Table | Grain | Date Col |
|---|---|---|
| `mv_new_hire_kpi_daily` | pseudonymous agent, KPI, performance day | `performance_date` |
| `mv_learning_curve_best` | service program, cohort, KPI | `run_date` |
| `mv_cohort_scorecard` | service program, cohort, KPI | none |
| `mv_sigma_band_comparison` | month, service program, cohort, KPI | `period` |
| `mv_kpi_forecast` | month, service program, KPI, actual/forecast | `period` |

## Query Decision Heuristic

| Question intent | Preferred source |
|---|---|
| Daily or weekly ramp, targets, agents, or volume reliability | `mv_new_hire_kpi_daily` |
| Model type, fit confidence, interpretation, or days to target | `mv_learning_curve_best` |
| Cross-cohort readiness comparison | `mv_cohort_scorecard` |
| Tenured statistical benchmark or sigma exception | `mv_sigma_band_comparison` |
| Future planning or uncertainty interval | `mv_kpi_forecast` |
