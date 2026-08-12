# Databricks notebook source
# MAGIC %md
# MAGIC # 03 — Train and govern learning-curve models
# MAGIC Fits four candidates per service program × cohort × KPI, logs every fit to MLflow, and registers each winner in Unity Catalog.

# COMMAND ----------

import datetime as dt
import math

import mlflow
import mlflow.pyfunc
import numpy as np
import pandas as pd

CATALOG = "workspace"
GOLD = f"{CATALOG}.contact_center_gold"
MODEL_SCHEMA = f"{CATALOG}.contact_center_models"
EXPERIMENT = "/Shared/contact_center_new_hire_learning_curves"
RUN_DATE = dt.date.today()

spark.sql(f"CREATE SCHEMA IF NOT EXISTS {MODEL_SCHEMA}")
mlflow.set_registry_uri("databricks-uc")
mlflow.set_experiment(EXPERIMENT)


class CurvePortfolioModel(mlflow.pyfunc.PythonModel):
    """One governed model artifact containing every selected cohort/KPI curve."""

    def __init__(self, winners):
        self.curves = {
            (row["service_program"], int(row["cohort_id"]), row["kpi"]):
            (row["model_type"], float(row["alpha"]), float(row["beta"]))
            for row in winners
        }

    def predict(self, context, model_input):
        predictions = []
        for row in model_input.itertuples(index=False):
            model_type, alpha, beta = self.curves[(row.service_program, int(row.cohort_id), row.kpi)]
            x = max(float(row.tenure_day), 1.0)
            if model_type == "linear":
                value = alpha + beta * x
            elif model_type == "logarithmic":
                value = alpha + beta * math.log(x)
            elif model_type == "exponential":
                value = alpha * math.exp(beta * x)
            else:
                value = alpha * x**beta
            predictions.append(value)
        return np.asarray(predictions)


def fit(model_type, x, y):
    if model_type == "linear":
        beta, alpha = np.polyfit(x, y, 1)
        predict = lambda z: alpha + beta * z
    elif model_type == "logarithmic":
        beta, alpha = np.polyfit(np.log(x), y, 1)
        predict = lambda z: alpha + beta * np.log(z)
    elif model_type == "exponential":
        beta, log_alpha = np.polyfit(x, np.log(np.maximum(y, 1e-9)), 1)
        alpha, predict = math.exp(log_alpha), lambda z: math.exp(log_alpha) * np.exp(beta * z)
    else:
        beta, log_alpha = np.polyfit(np.log(x), np.log(np.maximum(y, 1e-9)), 1)
        alpha, predict = math.exp(log_alpha), lambda z: math.exp(log_alpha) * np.power(z, beta)
    predicted = predict(x)
    total = float(np.sum((y - np.mean(y)) ** 2))
    residual = float(np.sum((y - predicted) ** 2))
    return float(alpha), float(beta), float(1 - residual / total if total else 0.0), predict


def solve_day(model_type, alpha, beta, target):
    try:
        if abs(beta) < 1e-12:
            return None
        value = {
            "linear": lambda: (target - alpha) / beta,
            "logarithmic": lambda: math.exp((target - alpha) / beta),
            "exponential": lambda: math.log(target / alpha) / beta,
            "power": lambda: (target / alpha) ** (1 / beta),
        }[model_type]()
        rounded = int(round(value))
        return rounded if 1 <= rounded <= 180 else None
    except (ValueError, OverflowError, ZeroDivisionError):
        return None


daily = spark.sql(f"""
SELECT service_program, cohort_id, cohort_name, kpi, normal,
       MAX(static_target) static_target, tenure_day,
       SUM(nominator) / NULLIF(SUM(denominator), 0) score,
       COUNT(DISTINCT agent_id) agent_count
FROM {GOLD}.fact_agent_kpi_daily
WHERE tenure_day BETWEEN 1 AND 90
GROUP BY service_program, cohort_id, cohort_name, kpi, normal, tenure_day
HAVING COUNT(DISTINCT agent_id) >= 5
""").toPandas()

all_rows = []
for keys, group in daily.groupby(["service_program", "cohort_id", "cohort_name", "kpi", "normal"]):
    group = group.sort_values("tenure_day").dropna(subset=["score"])
    x, y = group.tenure_day.to_numpy(float), group.score.to_numpy(float)
    if len(x) < 14:
        continue
    target = float(group.static_target.iloc[0])
    candidates = []
    for model_type in ["linear", "logarithmic", "exponential", "power"]:
        alpha, beta, r_squared, predict = fit(model_type, x, y)
        with mlflow.start_run(run_name=f"{keys[2]} | {keys[3]} | {model_type}") as run:
            mlflow.set_tags({"service_program": keys[0], "cohort_id": str(keys[1]), "cohort_name": keys[2], "kpi": keys[3], "model_type": model_type, "pipeline_run_date": RUN_DATE.isoformat()})
            mlflow.log_params({"alpha": alpha, "beta": beta, "observation_days": len(x), "normal": int(keys[4])})
            mlflow.log_metrics({"r_squared": r_squared, "predicted_day_30": float(predict(30)), "predicted_day_60": float(predict(60)), "predicted_day_90": float(predict(90))})
            run_id = run.info.run_id
        candidates.append({
            "service_program": keys[0], "cohort_id": int(keys[1]), "cohort_name": keys[2], "kpi": keys[3], "normal": int(keys[4]),
            "model_type": model_type, "alpha": alpha, "beta": beta, "r_squared": r_squared,
            "predicted_day_30": float(predict(30)), "predicted_day_60": float(predict(60)), "predicted_day_90": float(predict(90)),
            "days_to_target": solve_day(model_type, alpha, beta, target), "static_target": target,
            "mlflow_run_id": run_id, "run_date": RUN_DATE,
        })
    best = max(candidates, key=lambda row: row["r_squared"])
    for row in candidates:
        row["is_best_model"] = row["mlflow_run_id"] == best["mlflow_run_id"]
        row["registered_model_name"] = None
        row["registered_model_version"] = None
        if not row["is_best_model"]:
            row["interpretation"] = None
        elif row["r_squared"] < 0.30:
            row["interpretation"] = "Insufficient evidence to establish a reliable learning curve (R-squared below 0.30)."
        else:
            improving = (row["normal"] == 1 and row["beta"] > 0) or (row["normal"] == -1 and row["beta"] < 0)
            timing = f"Projected to reach target around day {row['days_to_target']}." if row["days_to_target"] else "Not projected to reach target within 180 days."
            row["interpretation"] = f"Performance {'improves' if improving else 'moves away from target'}; {row['model_type']} is the strongest fit (R-squared {row['r_squared']:.2f}). {timing}"
        all_rows.append(row)

winners = [row for row in all_rows if row["is_best_model"]]
model_name = f"{MODEL_SCHEMA}.learning_curve_portfolio"
with mlflow.start_run(run_name=f"learning-curve-portfolio-{RUN_DATE.isoformat()}") as portfolio_run:
    mlflow.set_tags({"model_scope": "all configured cohorts and KPIs", "pipeline_run_date": RUN_DATE.isoformat()})
    mlflow.log_params({"candidate_count": len(all_rows), "winner_count": len(winners), "candidate_model_types": "linear,logarithmic,exponential,power"})
    mlflow.log_metrics({"average_winner_r_squared": float(np.mean([row["r_squared"] for row in winners]))})
    winner_manifest = [
        {key: (value.isoformat() if isinstance(value, dt.date) else value) for key, value in row.items()}
        for row in winners
    ]
    mlflow.log_dict({"winners": winner_manifest}, "governance/selected_curves.json")
    example = pd.DataFrame([{key: winners[0][key] for key in ("service_program", "cohort_id", "kpi")} | {"tenure_day": 30.0}])
    mlflow.pyfunc.log_model(name="model", python_model=CurvePortfolioModel(winners), input_example=example)
    portfolio_run_id = portfolio_run.info.run_id

registered = mlflow.register_model(f"runs:/{portfolio_run_id}/model", model_name)
for row in winners:
    row["registered_model_name"] = model_name
    row["registered_model_version"] = str(registered.version)

spark.createDataFrame(pd.DataFrame(all_rows)).write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable(f"{GOLD}.learning_curve_results")

display(spark.sql(f"""
SELECT model_type, COUNT(*) candidate_rows, COUNT_IF(is_best_model) winners,
       ROUND(AVG(r_squared), 3) average_r_squared
FROM {GOLD}.learning_curve_results
GROUP BY model_type ORDER BY model_type
"""))
