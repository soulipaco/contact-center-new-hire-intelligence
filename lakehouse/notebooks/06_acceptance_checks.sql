-- Databricks notebook source
-- MAGIC %md
-- MAGIC # 06 — Data and model acceptance gates
-- MAGIC The notebook raises an error when any gate fails, so the Workflow cannot report a false success.

-- COMMAND ----------

CREATE OR REPLACE TEMP VIEW portfolio_acceptance_checks AS
WITH checks AS (
  SELECT 'fact_primary_key_duplicates' check_name, COUNT(*) failure_count FROM (
    SELECT performance_date, agent_id, kpi
    FROM workspace.contact_center_gold.fact_agent_kpi_daily
    GROUP BY performance_date, agent_id, kpi HAVING COUNT(*) > 1
  )
  UNION ALL SELECT 'null_fact_keys', COUNT(*) FROM workspace.contact_center_gold.fact_agent_kpi_daily
    WHERE performance_date IS NULL OR agent_id IS NULL OR kpi IS NULL
  UNION ALL SELECT 'invalid_directionality', COUNT(*) FROM workspace.contact_center_gold.fact_agent_kpi_daily
    WHERE normal NOT IN (1, -1)
  UNION ALL SELECT 'invalid_denominator', COUNT(*) FROM workspace.contact_center_gold.fact_agent_kpi_daily
    WHERE denominator <= 0
  UNION ALL SELECT 'invalid_volume_bin', COUNT(*) FROM workspace.contact_center_gold.fact_agent_kpi_daily
    WHERE volume_bin NOT BETWEEN 1 AND 4
  UNION ALL SELECT 'invalid_percentage_score', COUNT(*) FROM workspace.contact_center_gold.fact_agent_kpi_daily
    WHERE kpi_format = 'Percentage' AND agent_score NOT BETWEEN 0 AND 1
  UNION ALL SELECT 'missing_tenured_population', CASE WHEN COUNT_IF(tenure_day > 90) = 0 THEN 1 ELSE 0 END
    FROM workspace.contact_center_gold.fact_agent_kpi_daily
  UNION ALL SELECT 'scd_overlaps', COUNT(*) FROM (
    SELECT agent_id, valid_from,
      LAG(valid_until) OVER (PARTITION BY agent_id ORDER BY valid_from) previous_valid_until
    FROM workspace.contact_center_silver.dim_agent
  ) WHERE previous_valid_until >= valid_from
  UNION ALL SELECT 'silver_fact_agent_join_loss', ABS(
    (SELECT COUNT(*) FROM workspace.contact_center_silver.fact_agent_kpi_daily) -
    (SELECT COUNT(*) FROM workspace.contact_center_bronze.bronze_agent_kpi_daily_raw)
  )
  UNION ALL SELECT 'learning_curve_candidate_count', COUNT(*) FROM (
    SELECT service_program, cohort_id, kpi
    FROM workspace.contact_center_gold.learning_curve_results
    GROUP BY service_program, cohort_id, kpi
    HAVING COUNT(*) <> 4 OR COUNT_IF(is_best_model) <> 1
  )
  UNION ALL SELECT 'missing_mlflow_lineage', COUNT(*) FROM workspace.contact_center_gold.learning_curve_results
    WHERE mlflow_run_id IS NULL OR (is_best_model AND registered_model_name IS NULL)
  UNION ALL SELECT 'forecast_horizon_not_six', COUNT(*) FROM (
    SELECT service_program, kpi
    FROM workspace.contact_center_gold.forecast_predictions
    GROUP BY service_program, kpi HAVING COUNT_IF(NOT is_actual) <> 6
  )
  UNION ALL SELECT 'invalid_forecast_interval', COUNT(*) FROM workspace.contact_center_gold.forecast_predictions
    WHERE NOT is_actual AND NOT (forecast_lower <= forecast_value AND forecast_value <= forecast_upper)
  UNION ALL SELECT 'unsafe_agent_label', COUNT(*) FROM workspace.contact_center_gold.fact_agent_kpi_daily
    WHERE agent_label IS NULL OR agent_label RLIKE '(^|[^A-Za-z0-9._%+-])[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+[.][A-Za-z]{2,}($|[^A-Za-z0-9.-])'
  UNION ALL SELECT 'outlier_flag_inconsistency', COUNT(*) FROM workspace.contact_center_gold.mv_agent_weekly_outliers
    WHERE adverse_outlier AND NOT (z_score_outlier OR iqr_outlier)
  UNION ALL SELECT 'invalid_process_control_status', COUNT(*) FROM workspace.contact_center_gold.mv_process_control
    WHERE directional_z_score < -3 AND NOT special_cause_flag
  UNION ALL SELECT 'invalid_lean_six_sigma_counts', COUNT(*) FROM workspace.contact_center_gold.mv_lean_six_sigma_summary
    WHERE defect_count > opportunity_count OR first_pass_yield_pct NOT BETWEEN 0 AND 100
  UNION ALL SELECT 'serving_view_missing_rows', COUNT(*) FROM (
    SELECT 'mv_new_hire_kpi_daily' view_name, COUNT(*) row_count FROM workspace.contact_center_gold.mv_new_hire_kpi_daily
    UNION ALL SELECT 'mv_learning_curve_best', COUNT(*) FROM workspace.contact_center_gold.mv_learning_curve_best
    UNION ALL SELECT 'mv_sigma_band_comparison', COUNT(*) FROM workspace.contact_center_gold.mv_sigma_band_comparison
    UNION ALL SELECT 'mv_kpi_forecast', COUNT(*) FROM workspace.contact_center_gold.mv_kpi_forecast
    UNION ALL SELECT 'mv_cohort_scorecard', COUNT(*) FROM workspace.contact_center_gold.mv_cohort_scorecard
    UNION ALL SELECT 'mv_learning_curve_points', COUNT(*) FROM workspace.contact_center_gold.mv_learning_curve_points
    UNION ALL SELECT 'mv_kpi_forecast_series', COUNT(*) FROM workspace.contact_center_gold.mv_kpi_forecast_series
    UNION ALL SELECT 'mv_agent_target_series', COUNT(*) FROM workspace.contact_center_gold.mv_agent_target_series
    UNION ALL SELECT 'mv_learning_curve_series', COUNT(*) FROM workspace.contact_center_gold.mv_learning_curve_series
    UNION ALL SELECT 'mv_ramp_volume_progression', COUNT(*) FROM workspace.contact_center_gold.mv_ramp_volume_progression
    UNION ALL SELECT 'mv_kpi_driver_regression', COUNT(*) FROM workspace.contact_center_gold.mv_kpi_driver_regression
    UNION ALL SELECT 'mv_tenure_regression_series', COUNT(*) FROM workspace.contact_center_gold.mv_tenure_regression_series
    UNION ALL SELECT 'mv_volume_regression_series', COUNT(*) FROM workspace.contact_center_gold.mv_volume_regression_series
    UNION ALL SELECT 'mv_process_control', COUNT(*) FROM workspace.contact_center_gold.mv_process_control
    UNION ALL SELECT 'mv_process_control_series', COUNT(*) FROM workspace.contact_center_gold.mv_process_control_series
    UNION ALL SELECT 'mv_lean_six_sigma_summary', COUNT(*) FROM workspace.contact_center_gold.mv_lean_six_sigma_summary
    UNION ALL SELECT 'mv_agent_weekly_outliers', COUNT(*) FROM workspace.contact_center_gold.mv_agent_weekly_outliers
    UNION ALL SELECT 'mv_action_intelligence_dashboard', COUNT(*) FROM workspace.contact_center_gold.mv_action_intelligence_dashboard
  ) WHERE row_count = 0
)
SELECT * FROM checks;

-- COMMAND ----------

SELECT * FROM portfolio_acceptance_checks ORDER BY check_name;

-- COMMAND ----------

SELECT
  ASSERT_TRUE(
    SUM(failure_count) = 0,
    CONCAT('Portfolio acceptance failed with ', CAST(SUM(failure_count) AS STRING), ' violations')
  ) AS acceptance_gate,
  'PASS' AS acceptance_status,
  SUM(failure_count) AS total_failures
FROM portfolio_acceptance_checks;
