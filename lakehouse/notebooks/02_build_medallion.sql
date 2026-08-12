-- Databricks notebook source
-- MAGIC %md
-- MAGIC # 02 — Build Silver and Gold analytical layers

-- COMMAND ----------

CREATE SCHEMA IF NOT EXISTS workspace.contact_center_silver;
CREATE SCHEMA IF NOT EXISTS workspace.contact_center_gold;

-- COMMAND ----------

CREATE OR REPLACE TABLE workspace.contact_center_silver.dim_training_class
USING DELTA AS
SELECT DISTINCT
  CAST(cohort_id AS BIGINT) cohort_id,
  cohort_name,
  cohort_abbreviation,
  service_program,
  class_id,
  CAST(class_start_date AS DATE) class_start_date,
  CAST(class_sort AS INT) class_sort
FROM workspace.contact_center_bronze.bronze_training_class_raw;

-- COMMAND ----------

CREATE OR REPLACE TABLE workspace.contact_center_silver.dim_agent
USING DELTA AS
WITH snapshots AS (
  SELECT *,
    LEAD(CAST(snapshot_effective_from AS DATE)) OVER (
      PARTITION BY agent_id ORDER BY snapshot_effective_from
    ) AS next_effective_from
  FROM workspace.contact_center_bronze.bronze_agent_snapshot_raw
)
SELECT
  CAST(agent_id AS BIGINT) agent_id,
  agent_label,
  service_program,
  site,
  market,
  language,
  channel,
  line_of_business,
  CAST(first_day_in_production AS DATE) first_day_in_production,
  class_id,
  CAST(cohort_id AS BIGINT) cohort_id,
  cohort_name,
  wave,
  CAST(snapshot_effective_from AS DATE) valid_from,
  COALESCE(DATE_SUB(next_effective_from, 1), DATE '9999-12-31') valid_until,
  next_effective_from IS NULL is_current
FROM snapshots;

-- COMMAND ----------

CREATE OR REPLACE TABLE workspace.contact_center_silver.dim_kpi_target
USING DELTA AS
SELECT
  service_program,
  CAST(cohort_id AS BIGINT) cohort_id,
  kpi,
  CAST(target AS DOUBLE) target,
  CAST(normal AS INT) normal,
  kpi_format,
  CAST(lower_limit AS DOUBLE) lower_limit,
  CAST(upper_limit AS DOUBLE) upper_limit,
  CAST(effective_from AS DATE) effective_from,
  CAST(effective_to AS DATE) effective_to,
  CAST(target_version AS INT) target_version
FROM workspace.contact_center_bronze.bronze_kpi_target_raw;

-- COMMAND ----------

CREATE OR REPLACE TABLE workspace.contact_center_silver.fact_agent_kpi_daily
USING DELTA
PARTITIONED BY (performance_month) AS
SELECT
  CAST(f.performance_date AS DATE) performance_date,
  CAST(DATE_TRUNC('MONTH', f.performance_date) AS DATE) performance_month,
  CAST(f.agent_id AS BIGINT) agent_id,
  a.agent_label,
  a.service_program,
  a.cohort_id,
  a.cohort_name,
  a.class_id,
  a.site,
  a.market,
  a.language,
  a.channel,
  a.line_of_business,
  a.first_day_in_production,
  DATEDIFF(f.performance_date, a.first_day_in_production) + 1 tenure_day,
  CAST(FLOOR(DATEDIFF(f.performance_date, a.first_day_in_production) / 7) + 1 AS INT) tenure_week,
  f.kpi,
  t.normal,
  t.kpi_format,
  CAST(f.nominator AS DOUBLE) nominator,
  CAST(f.denominator AS DOUBLE) denominator,
  CAST(f.volume AS INT) volume,
  t.target static_target,
  t.lower_limit,
  t.upper_limit,
  f.source_load_timestamp
FROM workspace.contact_center_bronze.bronze_agent_kpi_daily_raw f
JOIN workspace.contact_center_silver.dim_agent a
  ON f.agent_id = a.agent_id
 AND f.performance_date BETWEEN a.valid_from AND a.valid_until
JOIN workspace.contact_center_silver.dim_kpi_target t
  ON a.service_program = t.service_program
 AND a.cohort_id = t.cohort_id
 AND f.kpi = t.kpi
 AND f.performance_date BETWEEN t.effective_from AND t.effective_to
WHERE f.performance_date >= a.first_day_in_production
  AND f.denominator > 0;

-- COMMAND ----------

CREATE OR REPLACE TABLE workspace.contact_center_gold.kpi_results_inc_nh
USING DELTA AS
SELECT
  performance_month period,
  service_program,
  cohort_id,
  cohort_name,
  kpi,
  agent_id,
  MAX(normal) normal,
  SUM(nominator) / NULLIF(SUM(denominator), 0) agent_score,
  SUM(volume) volume
FROM workspace.contact_center_silver.fact_agent_kpi_daily
WHERE tenure_day <= 30
GROUP BY performance_month, service_program, cohort_id, cohort_name, kpi, agent_id;

CREATE OR REPLACE TABLE workspace.contact_center_gold.kpi_results_exc_nh
USING DELTA AS
SELECT
  performance_month period,
  service_program,
  kpi,
  agent_id,
  MAX(normal) normal,
  SUM(nominator) / NULLIF(SUM(denominator), 0) agent_score,
  SUM(volume) volume
FROM workspace.contact_center_silver.fact_agent_kpi_daily
WHERE tenure_day > 90
GROUP BY performance_month, service_program, kpi, agent_id;

-- COMMAND ----------

CREATE OR REPLACE TABLE workspace.contact_center_gold.kpi_monthly_baselines
USING DELTA
PARTITIONED BY (period) AS
WITH tenured_month AS (
  SELECT period, service_program, kpi, MAX(normal) normal,
    SUM(agent_score * volume) / NULLIF(SUM(volume), 0) tenured_score,
    STDDEV_SAMP(agent_score) tenured_agent_std
  FROM workspace.contact_center_gold.kpi_results_exc_nh
  GROUP BY period, service_program, kpi
), new_hire_month AS (
  SELECT period, service_program, kpi,
    SUM(agent_score * volume) / NULLIF(SUM(volume), 0) new_hire_score,
    STDDEV_SAMP(agent_score) new_hire_std
  FROM workspace.contact_center_gold.kpi_results_inc_nh
  GROUP BY period, service_program, kpi
), joined AS (
  SELECT COALESCE(t.period, n.period) period,
    COALESCE(t.service_program, n.service_program) service_program,
    COALESCE(t.kpi, n.kpi) kpi,
    t.normal, t.tenured_score, t.tenured_agent_std,
    n.new_hire_score, n.new_hire_std
  FROM tenured_month t FULL OUTER JOIN new_hire_month n
    ON t.period = n.period AND t.service_program = n.service_program AND t.kpi = n.kpi
), rolling AS (
  SELECT *,
    AVG(tenured_score) OVER (PARTITION BY service_program, kpi ORDER BY period ROWS BETWEEN 3 PRECEDING AND 1 PRECEDING) tenured_3m_avg,
    AVG(tenured_agent_std) OVER (PARTITION BY service_program, kpi ORDER BY period ROWS BETWEEN 3 PRECEDING AND 1 PRECEDING) tenured_3m_std,
    AVG(new_hire_score) OVER (PARTITION BY service_program, kpi ORDER BY period ROWS BETWEEN 2 PRECEDING AND CURRENT ROW) new_hire_3m_avg
  FROM joined
)
SELECT
  r.*,
  CASE WHEN r.normal = 1 THEN r.tenured_3m_avg - r.tenured_3m_std ELSE r.tenured_3m_avg + r.tenured_3m_std END target_1_sigma,
  CASE WHEN r.normal = 1 THEN r.tenured_3m_avg - 2 * r.tenured_3m_std ELSE r.tenured_3m_avg + 2 * r.tenured_3m_std END target_2_sigma,
  CASE WHEN r.normal = 1 THEN r.tenured_3m_avg - 3 * r.tenured_3m_std ELSE r.tenured_3m_avg + 3 * r.tenured_3m_std END target_3_sigma,
  CASE
    WHEN MAX(t.kpi_format) = 'Percentage' AND r.normal = 1 THEN r.new_hire_3m_avg - 0.15
    WHEN MAX(t.kpi_format) = 'Percentage' AND r.normal = -1 THEN r.new_hire_3m_avg + 0.15
    WHEN r.normal = 1 THEN r.new_hire_3m_avg * 0.70
    ELSE r.new_hire_3m_avg * 1.30
  END training_target
FROM rolling r
JOIN workspace.contact_center_silver.dim_kpi_target t
  ON r.service_program = t.service_program AND r.kpi = t.kpi
GROUP BY ALL;

-- COMMAND ----------

CREATE OR REPLACE TABLE workspace.contact_center_gold.fact_agent_kpi_daily
USING DELTA
PARTITIONED BY (performance_month) AS
WITH enriched AS (
  SELECT
    s.*,
    s.nominator / NULLIF(s.denominator, 0) agent_score,
    b.training_target,
    b.tenured_3m_avg,
    b.target_1_sigma,
    b.target_2_sigma,
    b.target_3_sigma,
    SUM(s.volume) OVER (PARTITION BY s.agent_id, s.kpi ORDER BY s.performance_date) cumulative_volume,
    NTILE(4) OVER (PARTITION BY s.service_program, s.cohort_id, s.kpi ORDER BY s.volume) volume_bin
  FROM workspace.contact_center_silver.fact_agent_kpi_daily s
  LEFT JOIN workspace.contact_center_gold.kpi_monthly_baselines b
    ON s.performance_month = b.period
   AND s.service_program = b.service_program
   AND s.kpi = b.kpi
)
SELECT *,
  tenure_day <= 90 is_new_hire,
  CASE WHEN normal = 1 THEN agent_score >= static_target ELSE agent_score <= static_target END at_static_target,
  CASE WHEN training_target IS NULL THEN NULL
       WHEN normal = 1 THEN agent_score >= training_target ELSE agent_score <= training_target END at_training_target,
  CASE WHEN target_1_sigma IS NULL THEN NULL
       WHEN normal = 1 THEN agent_score >= target_1_sigma ELSE agent_score <= target_1_sigma END at_1_sigma
FROM enriched;

-- COMMAND ----------

OPTIMIZE workspace.contact_center_silver.fact_agent_kpi_daily ZORDER BY (service_program, kpi, agent_id);
OPTIMIZE workspace.contact_center_gold.fact_agent_kpi_daily ZORDER BY (service_program, kpi, agent_id);
OPTIMIZE workspace.contact_center_gold.kpi_monthly_baselines ZORDER BY (service_program, kpi);
