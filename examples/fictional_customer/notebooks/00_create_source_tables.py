# Databricks notebook source
# Initialize the Spark session explicitly so the fixture works in serverless jobs.
from pyspark.sql import SparkSession

spark = SparkSession.builder.getOrCreate()

# COMMAND ----------

import datetime as dt
import math
import random

import numpy as np
import pandas as pd

SEED = 20260813
SOURCE_SCHEMA = "workspace.cc_fixture_source"
TODAY = dt.date.today()
LOAD_TS = dt.datetime.combine(TODAY, dt.time(5, 0))
random.seed(SEED)
np.random.seed(SEED)

spark.sql(f"CREATE SCHEMA IF NOT EXISTS {SOURCE_SCHEMA}")

PROGRAMS = [
    ("Acorn Connect (Fictional)", "AC", ["English", "Dutch"]),
    ("Bluebird Travel (Fictional)", "BT", ["English", "Spanish"]),
    ("Cedar Health Desk (Fictional)", "CH", ["English", "French"]),
]
KPIS = [
    ("QA Score", "higher_is_better", "percentage", 0.88, 0.61, "logarithmic", 0.035),
    ("QA Pass Rate", "higher_is_better", "percentage", 0.84, 0.56, "power", 0.045),
    ("CSAT", "higher_is_better", "percentage", 0.82, 0.60, "logarithmic", 0.050),
    ("FCR", "higher_is_better", "percentage", 0.77, 0.53, "linear", 0.040),
    ("Adherence", "higher_is_better", "percentage", 0.90, 0.67, "linear", 0.030),
    ("AHT", "lower_is_better", "number", 500.0, 770.0, "exponential", 28.0),
    ("ACW", "lower_is_better", "number", 95.0, 180.0, "power", 10.0),
    ("Hold Time", "lower_is_better", "number", 75.0, 150.0, "logarithmic", 9.0),
]
CHANNELS = ["Voice", "Chat", "Email"]
LOCATIONS = ["Harbor Campus", "Orchard Campus", "Summit Campus"]
MARKETS = ["Region One", "Region Two", "Region Three"]
COHORTS_PER_PROGRAM = 3
AGENTS_PER_COHORT = 12
MAX_TENURE_DAYS = 210


def expected_score(day, start, target, curve):
    bounded = max(1, min(day, 90))
    if curve == "linear":
        return start + (target - start) * bounded / 90
    if curve == "logarithmic":
        return start + (target - start) * math.log1p(bounded) / math.log1p(90)
    if curve == "exponential":
        return start * math.exp(math.log(target / start) * bounded / 90)
    return start * bounded ** (math.log(target / start) / math.log(90))


observations, assignments, targets, classes = [], [], [], []
worker_key = 710000
for program_index, (program, prefix, languages) in enumerate(PROGRAMS):
    for cohort_index in range(COHORTS_PER_PROGRAM):
        cohort_key = 91000 + program_index * 100 + cohort_index
        cohort_name = f"{prefix}-Launch-{cohort_index + 1:02d}"
        class_key = f"{prefix}-ACADEMY-{cohort_index + 1:02d}"
        cohort_start = TODAY - dt.timedelta(days=640 - cohort_index * 210 - program_index * 11)
        classes.append({
            "academy_cohort_key": cohort_key,
            "academy_cohort_name": cohort_name,
            "academy_code": f"{prefix}{cohort_index + 1:02d}",
            "account_name": program,
            "academy_class_key": class_key,
            "academy_start": cohort_start,
            "presentation_order": cohort_index + 1,
            "fixture_loaded_at": LOAD_TS,
        })

        for metric_code, direction, value_format, goal, start, curve, noise in KPIS:
            valid_min = 0.0 if value_format == "percentage" else max(0.0, goal * 0.25)
            valid_max = 1.0 if value_format == "percentage" else start * 1.60
            for version_number, offset, factor in [(1, -730, 0.97), (2, -365, 1.00)]:
                targets.append({
                    "account_name": program,
                    "academy_cohort_key": cohort_key,
                    "metric_code": metric_code,
                    "goal": float(goal * factor),
                    "performance_direction": direction,
                    "value_format": value_format,
                    "valid_min": float(valid_min),
                    "valid_max": float(valid_max),
                    "valid_from": TODAY + dt.timedelta(days=offset),
                    "valid_to": TODAY + dt.timedelta(days=-366 if version_number == 1 else 3650),
                    "version_number": version_number,
                    "fixture_loaded_at": LOAD_TS,
                })

        for agent_offset in range(AGENTS_PER_COHORT):
            worker_key += 1
            production_start = cohort_start + dt.timedelta(days=int(np.random.randint(0, 24)))
            language = random.choice(languages)
            channel = random.choice(CHANNELS)
            location = random.choice(LOCATIONS)
            market = random.choice(MARKETS)
            assignment = {
                "worker_key": worker_key,
                "public_agent_alias": f"Worker-{worker_key - 710000:04d}",
                "account_name": program,
                "location_name": location,
                "market_segment": market,
                "supported_language": language,
                "interaction_channel": channel,
                "business_unit": f"{prefix} Customer Care",
                "production_start": production_start,
                "academy_class_key": class_key,
                "academy_cohort_key": cohort_key,
                "academy_cohort_name": cohort_name,
                "training_wave_name": f"Launch Wave {cohort_index + 1:02d}",
                "assignment_start": production_start,
                "fixture_loaded_at": LOAD_TS,
            }
            assignments.append(assignment)
            if agent_offset % 8 == 0:
                assignments.append({
                    **assignment,
                    "interaction_channel": "Chat" if channel != "Chat" else "Voice",
                    "assignment_start": production_start + dt.timedelta(days=120),
                })

            agent_effect = float(np.random.normal(0, 0.025))
            for metric_code, direction, value_format, goal, start, curve, noise in KPIS:
                for tenure_day in range(1, MAX_TENURE_DAYS + 1):
                    report_date = production_start + dt.timedelta(days=tenure_day - 1)
                    if report_date > TODAY:
                        break
                    if report_date.weekday() >= 5 and np.random.random() < 0.55:
                        continue
                    base = expected_score(tenure_day, start, goal, curve)
                    if value_format == "percentage":
                        score = float(np.clip(base + agent_effect + np.random.normal(0, noise), 0.15, 0.995))
                        handled = max(3, int(np.random.poisson(14)))
                    else:
                        score = float(max(5.0, base * (1 + agent_effect) + np.random.normal(0, noise)))
                        handled = max(3, int(np.random.poisson(10)))
                    observations.append({
                        "report_date": report_date,
                        "worker_key": worker_key,
                        "metric_code": metric_code,
                        "weighted_numerator": score * handled,
                        "score_denominator": float(handled),
                        "handled_contacts": handled,
                        "fixture_loaded_at": LOAD_TS,
                    })


def overwrite(table, records, partition=None):
    writer = (
        spark.createDataFrame(pd.DataFrame(records))
        .write.format("delta").mode("overwrite").option("overwriteSchema", "true")
    )
    if partition:
        writer = writer.partitionBy(partition)
    writer.saveAsTable(f"{SOURCE_SCHEMA}.{table}")


overwrite("kpi_daily", observations, "report_date")
overwrite("agent_assignments", assignments)
overwrite("target_schedule", targets)
overwrite("academy_classes", classes)

display(spark.sql(f"""
SELECT 'kpi_daily' source_table, COUNT(*) row_count FROM {SOURCE_SCHEMA}.kpi_daily
UNION ALL SELECT 'agent_assignments', COUNT(*) FROM {SOURCE_SCHEMA}.agent_assignments
UNION ALL SELECT 'target_schedule', COUNT(*) FROM {SOURCE_SCHEMA}.target_schedule
UNION ALL SELECT 'academy_classes', COUNT(*) FROM {SOURCE_SCHEMA}.academy_classes
"""))
