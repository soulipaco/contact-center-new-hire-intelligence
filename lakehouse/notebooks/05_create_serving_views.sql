-- Databricks notebook source
-- MAGIC %md
-- MAGIC # 05 — Create the governed serving layer

-- COMMAND ----------

-- Keep the core dashboard queryable before optional Action Intelligence is enabled.
CREATE VIEW IF NOT EXISTS workspace.contact_center_gold.mv_action_intelligence_latest AS
SELECT
  CAST(NULL AS TIMESTAMP) generated_at,
  CAST(NULL AS STRING) question_category,
  CAST(NULL AS STRING) question,
  CAST(NULL AS STRING) insight_summary,
  CAST(NULL AS STRING) recommended_action_plan,
  CAST(NULL AS STRING) warning,
  CAST(NULL AS STRING) model_endpoint,
  CAST(NULL AS BIGINT) retrieved_context_characters,
  CAST(NULL AS BIGINT) analysis_id
WHERE FALSE;

-- COMMAND ----------

CREATE OR REPLACE VIEW workspace.contact_center_gold.mv_action_intelligence_dashboard AS
SELECT
  'Enabled - latest grounded results' module_status,
  generated_at, question_category, question, insight_summary,
  recommended_action_plan, warning, model_endpoint,
  retrieved_context_characters, analysis_id
FROM workspace.contact_center_gold.mv_action_intelligence_latest
UNION ALL
SELECT
  'Optional module not enabled for this deployment' module_status,
  CAST(NULL AS TIMESTAMP) generated_at,
  CAST(NULL AS STRING) question_category,
  CAST(NULL AS STRING) question,
  CAST(NULL AS STRING) insight_summary,
  CAST(NULL AS STRING) recommended_action_plan,
  CAST(NULL AS STRING) warning,
  CAST(NULL AS STRING) model_endpoint,
  CAST(NULL AS BIGINT) retrieved_context_characters,
  CAST(NULL AS BIGINT) analysis_id
WHERE NOT EXISTS (
  SELECT 1 FROM workspace.contact_center_gold.mv_action_intelligence_latest
);

-- COMMAND ----------

CREATE OR REPLACE VIEW workspace.contact_center_gold.mv_new_hire_kpi_daily AS
SELECT
  performance_date, performance_month, agent_id, agent_label, service_program,
  cohort_id, cohort_name, class_id, site, market, language, channel,
  line_of_business, first_day_in_production, tenure_day, tenure_week,
  kpi, normal, kpi_format, nominator, denominator, agent_score, volume,
  static_target, training_target, tenured_3m_avg,
  target_1_sigma, target_2_sigma, target_3_sigma,
  cumulative_volume, volume_bin, is_new_hire,
  at_static_target, at_training_target, at_1_sigma
FROM workspace.contact_center_gold.fact_agent_kpi_daily
WHERE is_new_hire;

-- COMMAND ----------

CREATE OR REPLACE VIEW workspace.contact_center_gold.mv_learning_curve_best AS
SELECT *
FROM workspace.contact_center_gold.learning_curve_results
WHERE is_best_model;

-- COMMAND ----------

CREATE OR REPLACE VIEW workspace.contact_center_gold.mv_sigma_band_comparison AS
WITH monthly AS (
  SELECT
    performance_month period, service_program, cohort_id, cohort_name, kpi, normal,
    SUM(nominator) / NULLIF(SUM(denominator), 0) cohort_score,
    MAX(tenured_3m_avg) tenured_3m_avg,
    MAX(target_1_sigma) target_1_sigma,
    MAX(target_2_sigma) target_2_sigma,
    MAX(target_3_sigma) target_3_sigma,
    AVG(CASE WHEN at_1_sigma THEN 1.0 ELSE 0.0 END) at_1_sigma_rate,
    COUNT(DISTINCT agent_id) agent_count
  FROM workspace.contact_center_gold.fact_agent_kpi_daily
  WHERE is_new_hire
  GROUP BY performance_month, service_program, cohort_id, cohort_name, kpi, normal
)
SELECT *,
  CASE
    WHEN normal = 1 THEN cohort_score < target_1_sigma
    WHEN normal = -1 THEN cohort_score > target_1_sigma
    ELSE FALSE
  END below_1_sigma
FROM monthly;

-- COMMAND ----------

CREATE OR REPLACE VIEW workspace.contact_center_gold.mv_kpi_forecast AS
SELECT * FROM workspace.contact_center_gold.forecast_predictions;

-- COMMAND ----------

CREATE OR REPLACE VIEW workspace.contact_center_gold.mv_cohort_scorecard AS
SELECT
  f.service_program, f.cohort_id, f.cohort_name, f.kpi, MAX(f.normal) normal,
  COUNT(DISTINCT f.agent_id) agent_count,
  SUM(f.nominator) / NULLIF(SUM(f.denominator), 0) weighted_score,
  AVG(CASE WHEN f.at_static_target THEN 1.0 ELSE 0.0 END) static_target_attainment_rate,
  AVG(CASE WHEN f.at_training_target THEN 1.0 ELSE 0.0 END) training_target_attainment_rate,
  MAX(c.model_type) best_model_type,
  MAX(c.r_squared) best_model_r_squared,
  MAX(c.days_to_target) days_to_target,
  MAX(c.interpretation) learning_curve_interpretation
FROM workspace.contact_center_gold.fact_agent_kpi_daily f
LEFT JOIN workspace.contact_center_gold.mv_learning_curve_best c
  ON f.service_program = c.service_program
 AND f.cohort_id = c.cohort_id
 AND f.kpi = c.kpi
WHERE f.is_new_hire
GROUP BY f.service_program, f.cohort_id, f.cohort_name, f.kpi;

-- COMMAND ----------

CREATE OR REPLACE VIEW workspace.contact_center_gold.mv_learning_curve_points AS
SELECT
  service_program, cohort_id, cohort_name, kpi, model_type, r_squared,
  days_to_target, tenure_day, predicted_score
FROM workspace.contact_center_gold.mv_learning_curve_best
LATERAL VIEW STACK(
  3,
  30, predicted_day_30,
  60, predicted_day_60,
  90, predicted_day_90
) points AS tenure_day, predicted_score;

-- COMMAND ----------

CREATE OR REPLACE VIEW workspace.contact_center_gold.mv_learning_curve_series AS
WITH selected AS (
  SELECT c.*, EXPLODE(SEQUENCE(1, 90)) tenure_day
  FROM workspace.contact_center_gold.mv_learning_curve_best c
), fitted AS (
  SELECT
    service_program, cohort_id, cohort_name, kpi, normal, model_type, r_squared,
    days_to_target, tenure_day,
    CASE model_type
      WHEN 'linear' THEN alpha + beta * tenure_day
      WHEN 'logarithmic' THEN alpha + beta * LN(tenure_day)
      WHEN 'exponential' THEN alpha * EXP(beta * tenure_day)
      WHEN 'power' THEN alpha * POWER(tenure_day, beta)
    END fitted_score,
    static_target
  FROM selected
), observed AS (
  SELECT
    service_program, cohort_id, cohort_name, kpi, MAX(normal) normal,
    tenure_day,
    SUM(nominator) / NULLIF(SUM(denominator), 0) observed_score,
    MAX(static_target) static_target,
    MAX(training_target) training_target,
    SUM(volume) daily_volume,
    COUNT(DISTINCT agent_id) agent_count
  FROM workspace.contact_center_gold.mv_new_hire_kpi_daily
  GROUP BY service_program, cohort_id, cohort_name, kpi, tenure_day
), combined AS (
  SELECT
    o.service_program, o.cohort_id, o.cohort_name, o.kpi, o.normal,
    f.model_type, f.r_squared, f.days_to_target, o.tenure_day,
    o.observed_score, f.fitted_score, o.static_target, o.training_target,
    o.daily_volume, o.agent_count
  FROM observed o
  JOIN fitted f USING (service_program, cohort_id, cohort_name, kpi, tenure_day)
)
SELECT
  service_program, cohort_id, cohort_name, kpi, normal, model_type, r_squared,
  days_to_target, tenure_day, daily_volume, agent_count, series_name, raw_value,
  CASE
    WHEN raw_value IS NULL OR static_target IS NULL OR raw_value = 0 THEN NULL
    WHEN normal = 1 THEN 100.0 * raw_value / static_target
    ELSE 100.0 * static_target / raw_value
  END target_index
FROM combined
LATERAL VIEW STACK(
  3,
  'Observed cohort score', observed_score,
  'Selected model fit', fitted_score,
  'Static target (index = 100)', static_target
) series AS series_name, raw_value;

-- COMMAND ----------

CREATE OR REPLACE VIEW workspace.contact_center_gold.mv_ramp_volume_progression AS
WITH agent_week AS (
  SELECT
    service_program, cohort_id, cohort_name, kpi, agent_id, tenure_week,
    SUM(volume) weekly_volume,
    MAX(cumulative_volume) cumulative_volume
  FROM workspace.contact_center_gold.mv_new_hire_kpi_daily
  GROUP BY service_program, cohort_id, cohort_name, kpi, agent_id, tenure_week
)
SELECT
  service_program, cohort_id, cohort_name, kpi, tenure_week,
  COUNT(DISTINCT agent_id) agent_count,
  SUM(weekly_volume) total_volume,
  AVG(weekly_volume) average_weekly_volume_per_agent,
  AVG(cumulative_volume) average_cumulative_volume_per_agent
FROM agent_week
GROUP BY service_program, cohort_id, cohort_name, kpi, tenure_week;

-- COMMAND ----------

CREATE OR REPLACE VIEW workspace.contact_center_gold.mv_kpi_driver_relationship AS
SELECT
  service_program, cohort_id, cohort_name, kpi, MAX(normal) normal, tenure_week,
  AVG(tenure_day) average_tenure_day,
  SUM(nominator) / NULLIF(SUM(denominator), 0) weighted_score,
  CASE
    WHEN MAX(normal) = 1 THEN
      100.0 * (SUM(nominator) / NULLIF(SUM(denominator), 0)) / NULLIF(MAX(static_target), 0)
    ELSE
      100.0 * MAX(static_target) / NULLIF(SUM(nominator) / NULLIF(SUM(denominator), 0), 0)
  END target_index,
  SUM(volume) total_volume,
  AVG(volume) average_daily_volume,
  AVG(cumulative_volume) average_cumulative_volume,
  AVG(CASE WHEN at_static_target THEN 1.0 ELSE 0.0 END) target_attainment_rate,
  COUNT(DISTINCT agent_id) agent_count,
  COUNT(*) observation_count
FROM workspace.contact_center_gold.mv_new_hire_kpi_daily
GROUP BY service_program, cohort_id, cohort_name, kpi, tenure_week;

-- COMMAND ----------

CREATE OR REPLACE VIEW workspace.contact_center_gold.mv_kpi_driver_regression AS
WITH stats AS (
  SELECT
    service_program, cohort_id, cohort_name, kpi,
    COVAR_SAMP(target_index, average_tenure_day) / NULLIF(VAR_SAMP(average_tenure_day), 0) tenure_slope,
    AVG(target_index) -
      (COVAR_SAMP(target_index, average_tenure_day) / NULLIF(VAR_SAMP(average_tenure_day), 0))
      * AVG(average_tenure_day) tenure_intercept,
    CORR(target_index, average_tenure_day) tenure_correlation,
    COVAR_SAMP(target_index, average_daily_volume) / NULLIF(VAR_SAMP(average_daily_volume), 0) volume_slope,
    AVG(target_index) -
      (COVAR_SAMP(target_index, average_daily_volume) / NULLIF(VAR_SAMP(average_daily_volume), 0))
      * AVG(average_daily_volume) volume_intercept,
    CORR(target_index, average_daily_volume) volume_correlation
  FROM workspace.contact_center_gold.mv_kpi_driver_relationship
  GROUP BY service_program, cohort_id, cohort_name, kpi
)
SELECT
  r.*,
  s.tenure_slope, s.tenure_intercept, s.tenure_correlation,
  ABS(s.tenure_correlation) abs_tenure_correlation,
  s.tenure_intercept + s.tenure_slope * r.average_tenure_day tenure_fitted_target_index,
  s.volume_slope, s.volume_intercept, s.volume_correlation,
  ABS(s.volume_correlation) abs_volume_correlation,
  s.volume_intercept + s.volume_slope * r.average_daily_volume volume_fitted_target_index
FROM workspace.contact_center_gold.mv_kpi_driver_relationship r
JOIN stats s USING (service_program, cohort_id, cohort_name, kpi);

-- COMMAND ----------

CREATE OR REPLACE VIEW workspace.contact_center_gold.mv_tenure_regression_series AS
SELECT
  service_program, cohort_id, cohort_name, kpi, tenure_week,
  average_tenure_day, average_daily_volume, total_volume, agent_count,
  tenure_correlation, series_name, series_value
FROM workspace.contact_center_gold.mv_kpi_driver_regression
LATERAL VIEW STACK(
  2,
  'Observed target index', target_index,
  'Tenure regression fit', tenure_fitted_target_index
) series AS series_name, series_value;

-- COMMAND ----------

CREATE OR REPLACE VIEW workspace.contact_center_gold.mv_volume_regression_series AS
SELECT
  service_program, cohort_id, cohort_name, kpi, tenure_week,
  average_tenure_day, average_daily_volume, total_volume, agent_count,
  volume_correlation, series_name, series_value
FROM workspace.contact_center_gold.mv_kpi_driver_regression
LATERAL VIEW STACK(
  2,
  'Observed target index', target_index,
  'Volume regression fit', volume_fitted_target_index
) series AS series_name, series_value;

-- COMMAND ----------

CREATE OR REPLACE VIEW workspace.contact_center_gold.mv_process_control AS
WITH monthly AS (
  SELECT
    performance_month period, service_program, cohort_id, cohort_name, kpi,
    MAX(normal) normal,
    SUM(nominator) / NULLIF(SUM(denominator), 0) cohort_score,
    MAX(tenured_3m_avg) centerline,
    ABS(MAX(target_1_sigma) - MAX(tenured_3m_avg)) process_std,
    SUM(volume) total_volume,
    COUNT(DISTINCT agent_id) agent_count
  FROM workspace.contact_center_gold.mv_new_hire_kpi_daily
  GROUP BY performance_month, service_program, cohort_id, cohort_name, kpi
), scored AS (
  SELECT *, normal * (cohort_score - centerline) / NULLIF(process_std, 0) directional_z_score
  FROM monthly
)
SELECT *,
  CASE
    WHEN directional_z_score < -3 THEN 'Special cause: >3 sigma adverse'
    WHEN directional_z_score < -2 THEN 'High risk: 2-3 sigma adverse'
    WHEN directional_z_score < -1 THEN 'Watch: 1-2 sigma adverse'
    ELSE 'In control or favorable'
  END control_status,
  directional_z_score < -3 special_cause_flag
FROM scored;

-- COMMAND ----------

CREATE OR REPLACE VIEW workspace.contact_center_gold.mv_process_control_series AS
SELECT
  period, service_program, cohort_id, cohort_name, kpi, total_volume,
  agent_count, control_status, series_name, series_value
FROM workspace.contact_center_gold.mv_process_control
LATERAL VIEW STACK(
  5,
  'Directional z-score', directional_z_score,
  'Centerline', CAST(0.0 AS DOUBLE),
  '1 sigma adverse', CAST(-1.0 AS DOUBLE),
  '2 sigma adverse', CAST(-2.0 AS DOUBLE),
  '3 sigma adverse', CAST(-3.0 AS DOUBLE)
) series AS series_name, series_value;

-- COMMAND ----------

CREATE OR REPLACE VIEW workspace.contact_center_gold.mv_lean_six_sigma_summary AS
SELECT
  service_program, cohort_id, cohort_name, kpi,
  COUNT(*) opportunity_count,
  COUNT_IF(NOT at_static_target) defect_count,
  100.0 * COUNT_IF(at_static_target) / NULLIF(COUNT(*), 0) first_pass_yield_pct,
  1000000.0 * COUNT_IF(NOT at_static_target) / NULLIF(COUNT(*), 0) defects_per_million_opportunities,
  COUNT(DISTINCT agent_id) agent_count,
  SUM(volume) total_volume
FROM workspace.contact_center_gold.mv_new_hire_kpi_daily
GROUP BY service_program, cohort_id, cohort_name, kpi;

-- COMMAND ----------

CREATE OR REPLACE VIEW workspace.contact_center_gold.mv_agent_weekly_outliers AS
WITH agent_week AS (
  SELECT
    service_program, cohort_id, cohort_name, agent_id, agent_label, kpi,
    MAX(normal) normal, tenure_week,
    SUM(nominator) / NULLIF(SUM(denominator), 0) agent_score,
    SUM(volume) total_volume,
    COUNT(*) observation_count
  FROM workspace.contact_center_gold.mv_new_hire_kpi_daily
  GROUP BY service_program, cohort_id, cohort_name, agent_id, agent_label, kpi, tenure_week
), distribution AS (
  SELECT
    service_program, cohort_id, cohort_name, kpi, tenure_week,
    AVG(agent_score) peer_mean,
    STDDEV_SAMP(agent_score) peer_std,
    PERCENTILE_APPROX(agent_score, 0.25) q1,
    PERCENTILE_APPROX(agent_score, 0.75) q3,
    COUNT(*) peer_count
  FROM agent_week
  GROUP BY service_program, cohort_id, cohort_name, kpi, tenure_week
), scored AS (
  SELECT
    a.*, d.peer_mean, d.peer_std, d.q1, d.q3, d.peer_count,
    d.q1 - 1.5 * (d.q3 - d.q1) iqr_lower_bound,
    d.q3 + 1.5 * (d.q3 - d.q1) iqr_upper_bound,
    (a.agent_score - d.peer_mean) / NULLIF(d.peer_std, 0) z_score,
    a.normal * (a.agent_score - d.peer_mean) / NULLIF(d.peer_std, 0) directional_z_score
  FROM agent_week a
  JOIN distribution d USING (service_program, cohort_id, cohort_name, kpi, tenure_week)
)
SELECT *,
  ABS(z_score) >= 3 z_score_outlier,
  agent_score < iqr_lower_bound OR agent_score > iqr_upper_bound iqr_outlier,
  directional_z_score <= -3
    OR (normal = 1 AND agent_score < iqr_lower_bound)
    OR (normal = -1 AND agent_score > iqr_upper_bound) adverse_outlier,
  CASE
    WHEN directional_z_score <= -3 THEN 'Adverse z-score outlier'
    WHEN normal = 1 AND agent_score < iqr_lower_bound THEN 'Adverse IQR outlier'
    WHEN normal = -1 AND agent_score > iqr_upper_bound THEN 'Adverse IQR outlier'
    WHEN ABS(z_score) >= 3 OR agent_score < iqr_lower_bound OR agent_score > iqr_upper_bound THEN 'Favorable or neutral outlier'
    ELSE 'Within expected variation'
  END outlier_status
FROM scored;

-- COMMAND ----------

CREATE OR REPLACE VIEW workspace.contact_center_gold.mv_kpi_forecast_series AS
SELECT
  period, service_program, kpi, is_actual, model_type, series_name, series_value
FROM workspace.contact_center_gold.mv_kpi_forecast
LATERAL VIEW STACK(
  3,
  'Forecast / actual', forecast_value,
  'Lower 80%', forecast_lower,
  'Upper 80%', forecast_upper
) series AS series_name, series_value;

-- COMMAND ----------

CREATE OR REPLACE VIEW workspace.contact_center_gold.mv_agent_target_series AS
SELECT
  performance_date, agent_id, agent_label, service_program, cohort_name,
  channel, language, site, kpi, tenure_day, series_name, series_value
FROM workspace.contact_center_gold.mv_new_hire_kpi_daily
LATERAL VIEW STACK(
  3,
  'Agent score', agent_score,
  'Static target', static_target,
  'Training target', training_target
) series AS series_name, series_value;

-- COMMAND ----------

SELECT 'mv_new_hire_kpi_daily' object_name, COUNT(*) row_count FROM workspace.contact_center_gold.mv_new_hire_kpi_daily
UNION ALL SELECT 'mv_learning_curve_best', COUNT(*) FROM workspace.contact_center_gold.mv_learning_curve_best
UNION ALL SELECT 'mv_sigma_band_comparison', COUNT(*) FROM workspace.contact_center_gold.mv_sigma_band_comparison
UNION ALL SELECT 'mv_kpi_forecast', COUNT(*) FROM workspace.contact_center_gold.mv_kpi_forecast
UNION ALL SELECT 'mv_cohort_scorecard', COUNT(*) FROM workspace.contact_center_gold.mv_cohort_scorecard
UNION ALL SELECT 'mv_learning_curve_points', COUNT(*) FROM workspace.contact_center_gold.mv_learning_curve_points
UNION ALL SELECT 'mv_kpi_forecast_series', COUNT(*) FROM workspace.contact_center_gold.mv_kpi_forecast_series
UNION ALL SELECT 'mv_agent_target_series', COUNT(*) FROM workspace.contact_center_gold.mv_agent_target_series
UNION ALL SELECT 'mv_learning_curve_series', COUNT(*) FROM workspace.contact_center_gold.mv_learning_curve_series
UNION ALL SELECT 'mv_ramp_volume_progression', COUNT(*) FROM workspace.contact_center_gold.mv_ramp_volume_progression
UNION ALL SELECT 'mv_kpi_driver_relationship', COUNT(*) FROM workspace.contact_center_gold.mv_kpi_driver_relationship
UNION ALL SELECT 'mv_kpi_driver_regression', COUNT(*) FROM workspace.contact_center_gold.mv_kpi_driver_regression
UNION ALL SELECT 'mv_tenure_regression_series', COUNT(*) FROM workspace.contact_center_gold.mv_tenure_regression_series
UNION ALL SELECT 'mv_volume_regression_series', COUNT(*) FROM workspace.contact_center_gold.mv_volume_regression_series
UNION ALL SELECT 'mv_process_control', COUNT(*) FROM workspace.contact_center_gold.mv_process_control
UNION ALL SELECT 'mv_process_control_series', COUNT(*) FROM workspace.contact_center_gold.mv_process_control_series
UNION ALL SELECT 'mv_lean_six_sigma_summary', COUNT(*) FROM workspace.contact_center_gold.mv_lean_six_sigma_summary
UNION ALL SELECT 'mv_agent_weekly_outliers', COUNT(*) FROM workspace.contact_center_gold.mv_agent_weekly_outliers
UNION ALL SELECT 'mv_action_intelligence_dashboard', COUNT(*) FROM workspace.contact_center_gold.mv_action_intelligence_dashboard;
