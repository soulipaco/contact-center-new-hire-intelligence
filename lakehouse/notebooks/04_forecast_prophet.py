# Databricks notebook source
# MAGIC %md
# MAGIC # 04 — Six-month Prophet forecasts
# MAGIC Produces actuals plus six future months with 80% uncertainty intervals.

# COMMAND ----------

import datetime as dt

import mlflow
import pandas as pd
from prophet import Prophet

GOLD = "workspace.contact_center_gold"
EXPERIMENT = "/Shared/contact_center_new_hire_forecasts"
RUN_DATE = dt.date.today()
mlflow.set_experiment(EXPERIMENT)

monthly = spark.sql(f"""
SELECT performance_month period, service_program, kpi, MAX(normal) normal,
       SUM(nominator) / NULLIF(SUM(denominator), 0) actual_value
FROM {GOLD}.fact_agent_kpi_daily
WHERE tenure_day <= 30
GROUP BY performance_month, service_program, kpi
ORDER BY service_program, kpi, period
""").toPandas()

rows = []
for (program, kpi), group in monthly.groupby(["service_program", "kpi"]):
    group = group.sort_values("period").dropna(subset=["actual_value"])
    if group.period.nunique() < 6:
        continue
    training = group.rename(columns={"period": "ds", "actual_value": "y"})[["ds", "y"]]
    training["ds"] = pd.to_datetime(training["ds"])
    with mlflow.start_run(run_name=f"{program} | {kpi} | Prophet"):
        mlflow.set_tags({"service_program": program, "kpi": kpi, "model_type": "prophet"})
        mlflow.log_params({"interval_width": 0.80, "history_months": len(training), "forecast_horizon_months": 6})
        model = Prophet(interval_width=0.80, yearly_seasonality=False, weekly_seasonality=False, daily_seasonality=False)
        model.fit(training)
        future = model.make_future_dataframe(periods=6, freq="MS", include_history=True)
        prediction = model.predict(future)
        merged = prediction[["ds", "yhat", "yhat_lower", "yhat_upper"]].merge(training, on="ds", how="left")
        for record in merged.itertuples(index=False):
            is_actual = pd.notna(record.y)
            point = float(record.y if is_actual else record.yhat)
            rows.append({
                "period": record.ds.date(), "service_program": program, "kpi": kpi,
                "normal": int(group.normal.iloc[0]), "forecast_value": point,
                "forecast_lower": point if is_actual else float(record.yhat_lower),
                "forecast_upper": point if is_actual else float(record.yhat_upper),
                "is_actual": bool(is_actual), "model_type": "prophet",
                "interval_width": 0.80, "model_run_date": RUN_DATE,
            })

spark.createDataFrame(pd.DataFrame(rows)).write.format("delta").mode("overwrite").option("overwriteSchema", "true").partitionBy("model_run_date").saveAsTable(f"{GOLD}.forecast_predictions")

display(spark.sql(f"""
SELECT service_program, kpi, COUNT_IF(is_actual) actual_months,
       COUNT_IF(NOT is_actual) forecast_months,
       MIN(CASE WHEN NOT is_actual THEN period END) first_forecast_month,
       MAX(CASE WHEN NOT is_actual THEN period END) last_forecast_month
FROM {GOLD}.forecast_predictions
GROUP BY service_program, kpi
ORDER BY service_program, kpi
"""))
