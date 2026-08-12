-- Reviewable starter queries for dashboard authors and smoke tests.

-- Readiness and volume by tenure week
SELECT service_program, cohort_name, kpi, tenure_week,
  SUM(nominator) / NULLIF(SUM(denominator), 0) weighted_score,
  SUM(volume) handled_volume,
  COUNT(DISTINCT agent_id) agents
FROM workspace.contact_center_gold.mv_new_hire_kpi_daily
GROUP BY service_program, cohort_name, kpi, tenure_week;

-- KPI versus volume relationship
SELECT service_program, cohort_name, kpi, tenure_week,
  target_index, average_daily_volume, cumulative_volume, attainment_rate
FROM workspace.contact_center_gold.mv_kpi_driver_relationship;

-- Direction-aware process-control signals
SELECT period, service_program, cohort_name, kpi,
  target_index, directional_z_score, control_status, special_cause_flag
FROM workspace.contact_center_gold.mv_process_control;

-- Six-month forecast interval
SELECT service_program, kpi, period, is_actual,
  forecast_value, forecast_lower_80, forecast_upper_80
FROM workspace.contact_center_gold.mv_kpi_forecast;

