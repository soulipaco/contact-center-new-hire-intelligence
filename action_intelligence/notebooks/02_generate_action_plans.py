# Databricks notebook source
# MAGIC %pip install databricks-sdk mlflow pyyaml --quiet
# MAGIC

# COMMAND ----------

# ============================================================================
# Action Plans — Vector Search RAG + LLM Pipeline
# ============================================================================
# Task 2 in the Action Plans pipeline. This notebook:
#   1. Reads action_intelligence/config/pipeline.yml
#   2. Validates that all configuration placeholders are filled in
#   3. For each active trends analysis row (from the run completed today):
#      a. Queries the Vector Search index for relevant playbook chunks
#      b. Calls the configured LLM endpoint with the system prompt from config
#      c. Appends the generated action plan to the action_plan Delta table
#
# Orchestrated AFTER: 01_trends_analysis.py
# Requires:          00_index_playbook.py has completed successfully
# ============================================================================

# COMMAND ----------

import os
import re
import json
import yaml
from datetime import datetime

# ── Config loading (same pattern as trends_analysis.py) ──────────────────────

def _resolve_repo_root() -> str:
    try:
        nb_path = (
            dbutils.notebook.entry_point
            .getDbutils().notebook().getContext()
            .notebookPath().get()
        )
    except Exception:
        raise RuntimeError("This notebook must be run inside Databricks.")
    repo_root = os.path.dirname(os.path.dirname(os.path.dirname(nb_path)))
    if not repo_root.startswith("/Workspace"):
        repo_root = "/Workspace" + repo_root
    return repo_root


def _find_placeholders(obj, path="") -> list:
    found = []
    if isinstance(obj, str):
        for match in re.finditer(r"\{\{[^}]+\}\}", obj):
            found.append((path, match.group(0)))
    elif isinstance(obj, dict):
        for k, v in obj.items():
            found.extend(_find_placeholders(v, path=f"{path}.{k}" if path else k))
    elif isinstance(obj, list):
        for i, item in enumerate(obj):
            found.extend(_find_placeholders(item, path=f"{path}[{i}]"))
    return found


def load_config() -> dict:
    repo_root = _resolve_repo_root()
    config_path = f"{repo_root}/action_intelligence/config/pipeline.yml"
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = yaml.safe_load(f)
    except FileNotFoundError:
        raise FileNotFoundError(
            f"pipeline_config.yml not found at:\n  {config_path}\n\n"
            "Ensure this notebook runs from a Databricks Repo and the file exists."
        )
    for widget, section, key in [
        ("genie_space_id", "genie", "space_id"),
        ("vector_search_endpoint", "vector_search", "endpoint"),
        ("llm_endpoint", "llm", "endpoint"),
    ]:
        try:
            value = dbutils.widgets.get(widget)
        except Exception:
            value = ""
        if value:
            cfg[section][key] = value
    placeholders = _find_placeholders(cfg)
    if placeholders:
        lines = "\n".join(f"  • {path}: {value}" for path, value in placeholders)
        raise ValueError(
            f"pipeline_config.yml contains unconfigured placeholder(s):\n{lines}\n\n"
            f"Edit {config_path} and replace all {{{{PLACEHOLDER}}}} values before running."
        )
    return cfg, repo_root


def full_table(cfg: dict, suffix: str) -> str:
    c = cfg["catalog"]
    return f"{c['name']}.{c['schema']}.{c['table_prefix']}_{suffix}"


CFG, REPO_ROOT = load_config()
print(f"Config loaded from: {REPO_ROOT}/pipeline/pipeline_config.yml")
print(f"  VS Endpoint : {CFG['vector_search']['endpoint']}")
print(f"  LLM Endpoint: {CFG['llm']['endpoint']}")

# COMMAND ----------

# ============================================================================
# Create action_plan table (idempotent)
# ============================================================================

ACTION_PLAN_TABLE  = full_table(CFG, "action_plan")
ANALYSIS_TABLE     = full_table(CFG, "trends_analysis")
VS_INDEX_NAME      = f"{CFG['catalog']['name']}.{CFG['catalog']['schema']}.{CFG['catalog']['table_prefix']}_playbook_chunks_index"

spark.sql(f"""
CREATE TABLE IF NOT EXISTS {ACTION_PLAN_TABLE} (
  id                  BIGINT GENERATED ALWAYS AS IDENTITY,
  analysis_id         BIGINT,
  timestamp           TIMESTAMP,
  question_category   STRING,
  question            STRING,
  trends_summary      STRING,
  retrieved_chunks    STRING,
  action_plan         STRING,
  model_endpoint      STRING
)
USING DELTA
COMMENT 'Generated action plans from LLM + Vector Search RAG'
""")

print(f"Table ready: {ACTION_PLAN_TABLE}")

# COMMAND ----------

# ============================================================================
# Load today's trends analysis rows (most recent run per category)
# ============================================================================

from pyspark.sql import functions as F

analysis_df = (
    spark.table(ANALYSIS_TABLE)
    .withColumn("date", F.to_date("timestamp"))
    .filter(F.col("date") == F.current_date())
    .groupBy("question_category")
    .agg(F.max("id").alias("max_id"))
    .join(spark.table(ANALYSIS_TABLE), [
        spark.table(ANALYSIS_TABLE).question_category ==
            F.col("question_category"),
        spark.table(ANALYSIS_TABLE).id == F.col("max_id"),
    ])
    .select(
        spark.table(ANALYSIS_TABLE).id.alias("analysis_id"),
        spark.table(ANALYSIS_TABLE).question_category,
        spark.table(ANALYSIS_TABLE).question,
        spark.table(ANALYSIS_TABLE)["summary"].alias("trends_summary"),
        spark.table(ANALYSIS_TABLE).warning,
    )
)

# Simpler approach — just get the latest rows per category from today
analysis_df = spark.sql(f"""
    SELECT t.id AS analysis_id,
           t.question_category,
           t.question,
           t.summary AS trends_summary,
           t.warning
    FROM {ANALYSIS_TABLE} t
    INNER JOIN (
        SELECT question_category, MAX(id) AS max_id
        FROM {ANALYSIS_TABLE}
        WHERE DATE(timestamp) = CURRENT_DATE()
        GROUP BY question_category
    ) latest ON t.id = latest.max_id
""")

analysis_rows = analysis_df.collect()

if not analysis_rows:
    print("No trends analysis rows found for today. Run trends_analysis.py first.")
    dbutils.notebook.exit("No rows to process.")

print(f"{len(analysis_rows)} analysis row(s) to process into action plans.")

# COMMAND ----------

# ============================================================================
# Vector Search client
# ============================================================================

from databricks.vector_search.client import VectorSearchClient

vs_client = VectorSearchClient()

VS_ENDPOINT    = CFG["vector_search"]["endpoint"]
VS_NUM_RESULTS = CFG["vector_search"].get("num_results", 5)


def retrieve_playbook_chunks(question_category: str, trends_summary: str) -> list:
    """Query the VS index filtered by question_category, return top chunks."""
    index = vs_client.get_index(
        endpoint_name=VS_ENDPOINT,
        index_name=VS_INDEX_NAME,
    )
    query_text = f"{question_category}: {trends_summary[:500]}"
    results = index.similarity_search(
        query_text=query_text,
        columns=["chunk_text", "question_category", "source_file", "chunk_index"],
        filters={"question_category": question_category},
        num_results=VS_NUM_RESULTS,
    )
    chunks = []
    for hit in (results.get("result", {}).get("data_array", [])):
        if hit:
            chunks.append({
                "chunk_text": hit[0] if len(hit) > 0 else "",
                "question_category": hit[1] if len(hit) > 1 else "",
                "source_file": hit[2] if len(hit) > 2 else "",
                "chunk_index": hit[3] if len(hit) > 3 else 0,
            })
    return chunks


# COMMAND ----------

# ============================================================================
# LLM action plan generation
# ============================================================================

import mlflow.deployments

deploy_client = mlflow.deployments.get_deploy_client("databricks")
LLM_ENDPOINT   = CFG["llm"]["endpoint"]
LLM_MAX_TOKENS = CFG["llm"].get("max_tokens", 4096)
LLM_TEMP       = CFG["llm"].get("temperature", 0.3)
SYSTEM_PROMPTS = CFG.get("system_prompts", {})


def _default_system_prompt(question_category: str) -> str:
    return (
        f"You are an expert operations analyst for {question_category}. "
        "You will receive a trends analysis report and relevant playbook recommendations. "
        "Generate a concrete, prioritized action plan. "
        "Structure it as: Immediate Actions (24-48h), Short-term Actions (1-2 weeks), "
        "Measurement Targets."
    )


def generate_action_plan(
    question_category: str,
    trends_summary: str,
    chunks: list,
) -> str:
    """Call the LLM endpoint to generate an action plan from trends + playbook chunks."""
    system_prompt = SYSTEM_PROMPTS.get(question_category) or _default_system_prompt(question_category)

    if chunks:
        playbook_section = "\n\n".join(
            f"[Playbook excerpt — {c.get('source_file','?')}]\n{c.get('chunk_text','')}"
            for c in chunks
        )
    else:
        playbook_section = "No matching playbook excerpts found for this category."

    user_message = (
        f"## Trends Analysis Report\n\n{trends_summary}\n\n"
        f"## Playbook Recommendations\n\n{playbook_section}"
    )

    response = deploy_client.predict(
        endpoint=LLM_ENDPOINT,
        inputs={
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user",   "content": user_message},
            ],
            "max_tokens": LLM_MAX_TOKENS,
            "temperature": LLM_TEMP,
        },
    )
    choices = response.get("choices", [])
    if not choices:
        return "[Error: LLM returned no choices]"
    return choices[0].get("message", {}).get("content", "[Error: no content in choice]")


# COMMAND ----------

# ============================================================================
# Process each analysis row — retrieve → generate → collect
# ============================================================================

from pyspark.sql.types import (
    StructType, StructField, LongType, TimestampType, StringType
)
from pyspark.sql import Row

result_rows = []

for row in analysis_rows:
    cat       = row["question_category"]
    question  = row["question"]
    summary   = row["trends_summary"] or ""
    a_id      = row["analysis_id"]

    print(f"\n[{a_id}] ({cat}) {question[:80]}...")

    chunks = []
    chunks_json = "[]"
    action_plan = ""

    try:
        chunks = retrieve_playbook_chunks(cat, summary)
        chunks_json = json.dumps(chunks, ensure_ascii=False)
        print(f"   Retrieved {len(chunks)} chunk(s) from VS index.")
    except Exception as e:
        print(f"   VS retrieval failed: {e}")
        chunks_json = json.dumps({"error": str(e)})

    try:
        action_plan = generate_action_plan(cat, summary, chunks)
        print(f"   Action plan generated — {len(action_plan)} chars.")
    except Exception as e:
        action_plan = f"[Error generating action plan: {e}]"
        print(f"   LLM call failed: {e}")

    result_rows.append(Row(
        analysis_id=a_id,
        timestamp=datetime.utcnow(),
        question_category=cat,
        question=question,
        trends_summary=summary,
        retrieved_chunks=chunks_json,
        action_plan=action_plan,
        model_endpoint=LLM_ENDPOINT,
    ))

# COMMAND ----------

# ============================================================================
# Write results to the action_plan table
# ============================================================================

if result_rows:
    schema = StructType([
        StructField("analysis_id",       LongType(),      True),
        StructField("timestamp",         TimestampType(), True),
        StructField("question_category", StringType(),    True),
        StructField("question",          StringType(),    True),
        StructField("trends_summary",    StringType(),    True),
        StructField("retrieved_chunks",  StringType(),    True),
        StructField("action_plan",       StringType(),    True),
        StructField("model_endpoint",    StringType(),    True),
    ])
    result_df = spark.createDataFrame(result_rows, schema=schema)
    result_df.write.mode("append").saveAsTable(ACTION_PLAN_TABLE)
    print(f"\n{len(result_rows)} action plan(s) written to {ACTION_PLAN_TABLE}.")

    spark.sql(f"""
    CREATE OR REPLACE VIEW {CFG['catalog']['name']}.{CFG['catalog']['schema']}.mv_action_intelligence_latest AS
    WITH latest_action AS (
      SELECT *, ROW_NUMBER() OVER (
        PARTITION BY question_category ORDER BY timestamp DESC, id DESC
      ) AS row_number
      FROM {ACTION_PLAN_TABLE}
    ), latest_analysis AS (
      SELECT *, ROW_NUMBER() OVER (
        PARTITION BY question_category ORDER BY timestamp DESC, id DESC
      ) AS row_number
      FROM {ANALYSIS_TABLE}
    )
    SELECT
      a.timestamp generated_at,
      a.question_category,
      a.question,
      LEFT(COALESCE(NULLIF(TRIM(a.trends_summary), ''), a.action_plan), 1200) insight_summary,
      LEFT(a.action_plan, 4000) recommended_action_plan,
      n.warning,
      a.model_endpoint,
      LENGTH(a.retrieved_chunks) retrieved_context_characters,
      a.analysis_id
    FROM latest_action a
    LEFT JOIN latest_analysis n ON a.analysis_id = n.id
    WHERE a.row_number = 1
    """)
    print("Latest insight/action serving view refreshed for AI/BI.")
else:
    print("\nNo action plans to write.")
