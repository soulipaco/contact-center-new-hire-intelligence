# Databricks notebook source
# MAGIC %md
# MAGIC # 01 — Generate privacy-safe Bronze data
# MAGIC Deterministic synthetic generation only. This notebook never reads the legacy workbook.

# COMMAND ----------

import datetime as dt
import math
import random

import numpy as np
import pandas as pd
from pyspark.sql import functions as F

SEED = 20260812
CATALOG = "workspace"
BRONZE = f"{CATALOG}.contact_center_bronze"
TODAY = dt.date.today()
LOAD_TS = dt.datetime.combine(TODAY, dt.time(6, 0))
random.seed(SEED)
np.random.seed(SEED)

spark.sql(f"CREATE SCHEMA IF NOT EXISTS {BRONZE}")

# Every public label is intentionally fictional.
PROGRAMS = [
    ("Asterline Mobility (Fictional)", "AM", ["English", "German"]),
    ("Copperleaf Delivery (Fictional)", "CD", ["English", "Italian"]),
    ("LumaWave Mobile (Fictional)", "LM", ["English", "Portuguese"]),
    ("Northstar Home (Fictional)", "NH", ["English", "French"]),
    ("Juniper Parcel (Fictional)", "JP", ["English", "Spanish"]),
]

KPIS = [
    ("QA Score", 1, "Percentage", 0.88, 0.62, "logarithmic", 0.035),
    ("QA Pass Rate", 1, "Percentage", 0.84, 0.57, "power", 0.045),
    ("CSAT", 1, "Percentage", 0.82, 0.61, "logarithmic", 0.050),
    ("FCR", 1, "Percentage", 0.77, 0.54, "linear", 0.040),
    ("Adherence", 1, "Percentage", 0.90, 0.68, "linear", 0.030),
    ("AHT", -1, "Number", 500.0, 760.0, "exponential", 28.0),
    ("ACW", -1, "Number", 95.0, 175.0, "power", 10.0),
    ("Hold Time", -1, "Number", 75.0, 145.0, "logarithmic", 9.0),
]

CHANNELS = ["Voice", "Chat", "Email"]
SITES = ["Site North", "Site Central", "Site South"]
MARKETS = ["Market Alpha", "Market Beta", "Market Gamma"]
COHORTS_PER_PROGRAM = 3
AGENTS_PER_COHORT = 20
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


agent_snapshots, classes, target_history, facts = [], [], [], []
agent_id = 900000
for program_index, (program, prefix, languages) in enumerate(PROGRAMS):
    for cohort_index in range(COHORTS_PER_PROGRAM):
        cohort_id = 81000 + program_index * 100 + cohort_index
        cohort_name = f"{prefix}-Academy-{cohort_index + 1:02d}"
        class_id = f"{prefix}-CLASS-{cohort_index + 1:02d}"
        cohort_start = TODAY - dt.timedelta(days=690 - cohort_index * 190 - program_index * 9)
        classes.append({
            "cohort_id": cohort_id, "cohort_name": cohort_name,
            "cohort_abbreviation": f"{prefix}{cohort_index + 1:02d}",
            "service_program": program, "class_id": class_id,
            "class_start_date": cohort_start, "class_sort": cohort_index + 1,
            "source_load_timestamp": LOAD_TS, "synthetic_seed": SEED,
        })

        for kpi_index, (kpi, normal, kpi_format, target, start, curve, noise) in enumerate(KPIS):
            lower = 0.0 if kpi_format == "Percentage" else max(0.0, target * 0.25)
            upper = 1.0 if kpi_format == "Percentage" else start * 1.60
            for version, offset, factor in [(1, -730, 0.97), (2, -365, 1.00)]:
                target_history.append({
                    "service_program": program, "cohort_id": cohort_id, "kpi": kpi,
                    "target": float(target * factor), "normal": normal, "kpi_format": kpi_format,
                    "lower_limit": float(lower), "upper_limit": float(upper),
                    "effective_from": TODAY + dt.timedelta(days=offset),
                    "effective_to": TODAY + dt.timedelta(days=(-366 if version == 1 else 3650)),
                    "target_version": version, "source_load_timestamp": LOAD_TS,
                    "synthetic_seed": SEED,
                })

        for agent_offset in range(AGENTS_PER_COHORT):
            agent_id += 1
            first_day = cohort_start + dt.timedelta(days=int(np.random.randint(0, 28)))
            language, channel, site, market = random.choice(languages), random.choice(CHANNELS), random.choice(SITES), random.choice(MARKETS)
            agent_label = f"Agent {agent_id - 900000:04d}"
            base_snapshot = {
                "agent_id": agent_id, "agent_label": agent_label, "service_program": program,
                "site": site, "market": market, "language": language, "channel": channel,
                "line_of_business": f"{prefix} Support", "first_day_in_production": first_day,
                "class_id": class_id, "cohort_id": cohort_id, "cohort_name": cohort_name,
                "wave": f"Wave {cohort_index + 1:02d}", "snapshot_effective_from": first_day,
                "source_load_timestamp": LOAD_TS, "synthetic_seed": SEED,
            }
            agent_snapshots.append(base_snapshot)
            if agent_offset % 10 == 0:
                transfer_day = first_day + dt.timedelta(days=120)
                agent_snapshots.append({**base_snapshot, "channel": "Chat" if channel != "Chat" else "Voice", "snapshot_effective_from": transfer_day})

            agent_effect = float(np.random.normal(0, 0.025))
            for kpi, normal, kpi_format, target, start, curve, noise in KPIS:
                cumulative_volume = 0
                for tenure_day in range(1, MAX_TENURE_DAYS + 1):
                    performance_date = first_day + dt.timedelta(days=tenure_day - 1)
                    if performance_date > TODAY:
                        break
                    if performance_date.weekday() >= 5 and np.random.random() < 0.55:
                        continue
                    base = expected_score(tenure_day, start, target, curve)
                    if kpi_format == "Percentage":
                        score = float(np.clip(base + agent_effect + np.random.normal(0, noise), 0.15, 0.995))
                        volume = max(3, int(np.random.poisson(14)))
                    else:
                        score = float(max(5.0, base * (1 + agent_effect) + np.random.normal(0, noise)))
                        volume = max(3, int(np.random.poisson(10)))
                    cumulative_volume += volume
                    facts.append({
                        "performance_date": performance_date, "agent_id": agent_id, "kpi": kpi,
                        "nominator": score * volume, "denominator": float(volume), "volume": volume,
                        "source_sequence": tenure_day, "source_load_timestamp": LOAD_TS,
                        "synthetic_seed": SEED,
                    })


def overwrite(table, records, partition=None):
    writer = spark.createDataFrame(pd.DataFrame(records)).write.format("delta").mode("overwrite").option("overwriteSchema", "true")
    if partition:
        writer = writer.partitionBy(partition)
    writer.saveAsTable(f"{BRONZE}.{table}")


overwrite("bronze_agent_kpi_daily_raw", facts, "performance_date")
overwrite("bronze_agent_snapshot_raw", agent_snapshots)
overwrite("bronze_kpi_target_raw", target_history)
overwrite("bronze_training_class_raw", classes)

display(spark.sql(f"""
SELECT 'agent_kpi_daily' object_name, COUNT(*) row_count FROM {BRONZE}.bronze_agent_kpi_daily_raw
UNION ALL SELECT 'agent_snapshot', COUNT(*) FROM {BRONZE}.bronze_agent_snapshot_raw
UNION ALL SELECT 'kpi_target', COUNT(*) FROM {BRONZE}.bronze_kpi_target_raw
UNION ALL SELECT 'training_class', COUNT(*) FROM {BRONZE}.bronze_training_class_raw
"""))
