# Databricks notebook source
# MAGIC %pip install databricks-sdk httpx pyyaml --quiet
# MAGIC

# COMMAND ----------

# ============================================================================
# Trends Analysis — Genie Deep Research Pipeline
# ============================================================================
# Task 1 in the Action Plans pipeline. This notebook:
#   1. Reads pipeline_config.yml from the repo root
#   2. Validates that all configuration placeholders are filled in
#   3. Creates and seeds the trends questions table (idempotent)
#   4. Runs each active question against the configured Genie space via Deep Research
#   5. Parses responses for ## Summary and ## Warning sections
#   6. Writes results to the trends analysis Delta table
#
# Orchestrated BEFORE: pipeline/action_plans.py
# ============================================================================

# COMMAND ----------

import os
import re
import yaml

# ── Config loading ────────────────────────────────────────────────────────────

def _resolve_repo_root() -> str:
    """Resolve the workspace-absolute path of the repo root.

    This notebook lives at <repo_root>/pipeline/<name>.
    We go up two levels: past the notebook name, past 'pipeline/'.
    """
    try:
        nb_path = (
            dbutils.notebook.entry_point
            .getDbutils().notebook().getContext()
            .notebookPath().get()
        )
    except Exception:
        raise RuntimeError(
            "This notebook must be run inside Databricks. "
            "Cannot resolve repo root from local execution."
        )
    repo_root = os.path.dirname(os.path.dirname(os.path.dirname(nb_path)))
    if not repo_root.startswith("/Workspace"):
        repo_root = "/Workspace" + repo_root
    return repo_root


def _find_placeholders(obj, path="") -> list:
    """Recursively find {{PLACEHOLDER}} strings in a parsed YAML object."""
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
    """Load and validate pipeline_config.yml. Fails fast on any unconfigured placeholder."""
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
    """Return a fully qualified Delta table name: catalog.schema.prefix_suffix"""
    c = cfg["catalog"]
    return f"{c['name']}.{c['schema']}.{c['table_prefix']}_{suffix}"


CFG, REPO_ROOT = load_config()
print(f"Config loaded from: {REPO_ROOT}/pipeline/pipeline_config.yml")
print(f"  Space ID  : {CFG['genie']['space_id']}")
print(f"  Catalog   : {CFG['catalog']['name']}.{CFG['catalog']['schema']}")
print(f"  Prefix    : {CFG['catalog']['table_prefix']}")

# COMMAND ----------

# ============================================================================
# Create input/output tables (idempotent)
# ============================================================================

QUESTIONS_TABLE = full_table(CFG, "trends_questions")
ANALYSIS_TABLE  = full_table(CFG, "trends_analysis")

spark.sql(f"""
CREATE TABLE IF NOT EXISTS {QUESTIONS_TABLE} (
  id                BIGINT GENERATED ALWAYS AS IDENTITY,
  question_category STRING,
  question          STRING,
  is_active         BOOLEAN
)
USING DELTA
COMMENT 'Trends questions seeded per domain — one question per question_category'
""")

spark.sql(f"""
CREATE TABLE IF NOT EXISTS {ANALYSIS_TABLE} (
  id                BIGINT GENERATED ALWAYS AS IDENTITY,
  question_id       BIGINT,
  timestamp         TIMESTAMP,
  question_category STRING,
  question          STRING,
  response          STRING,
  summary           STRING,
  warning           STRING
)
USING DELTA
COMMENT 'Trends analysis results from Genie Deep Research'
""")

print(f"Tables ready:\n  {QUESTIONS_TABLE}\n  {ANALYSIS_TABLE}")

# COMMAND ----------

# ============================================================================
# Seed questions from pipeline_config.yml (idempotent MERGE)
# ============================================================================

from pyspark.sql import Row

seed_rows = [
    Row(question_category=seed["category"], question=seed["question"], is_active=True)
    for seed in CFG.get("questions", {}).get("seeds", [])
]

if not seed_rows:
    raise ValueError(
        "No seed questions found in pipeline_config.yml under questions.seeds.\n"
        "Add at least one entry before running this notebook."
    )

seed_df = spark.createDataFrame(seed_rows)
seed_df.createOrReplaceTempView("_seed_questions")

spark.sql(f"""
MERGE INTO {QUESTIONS_TABLE} AS target
USING _seed_questions AS seed
ON target.question_category = seed.question_category
AND target.question = seed.question
WHEN MATCHED THEN
  UPDATE SET target.is_active = seed.is_active
WHEN NOT MATCHED THEN
  INSERT (question_category, question, is_active)
  VALUES (seed.question_category, seed.question, seed.is_active)
""")

print(f"{len(seed_rows)} seed question(s) synchronized into {QUESTIONS_TABLE}.")

# COMMAND ----------

# ============================================================================
# Genie Deep Research client
# ============================================================================

import asyncio
import logging
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import httpx
import pandas as pd
from databricks.sdk import WorkspaceClient
from databricks.sdk.config import Config

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("genie_client")


@dataclass
class ResearchStep:
    type: str
    title: str = ""
    content: str = ""
    query: Optional[str] = None
    statement_id: Optional[str] = None
    status: str = "running"


@dataclass
class GenieResult:
    success: bool
    answer_text: Optional[str] = None
    sql: Optional[str] = None
    data: Optional[pd.DataFrame] = None
    error: Optional[str] = None
    reasoning_steps: List[ResearchStep] = field(default_factory=list)
    is_deep_research: bool = False
    raw_response: Optional[Dict[str, Any]] = None


class DatabricksGenieClient:
    def __init__(self, space_id: str, host: Optional[str] = None, token: Optional[str] = None):
        self._space_id = space_id
        self._token: Optional[str] = None
        self._host: Optional[str] = None
        self._workspace_client: Optional[WorkspaceClient] = None

        try:
            if host and token:
                self._workspace_client = WorkspaceClient(host=host, token=token)
            elif host:
                self._workspace_client = WorkspaceClient(host=host)
            else:
                self._workspace_client = WorkspaceClient()
            cfg: Config = self._workspace_client.config
            self._host = cfg.host.rstrip("/")
            header = cfg.authenticate()
            auth_value = header.get("Authorization", "")
            if auth_value.startswith("Bearer "):
                self._token = auth_value[len("Bearer "):]
            logger.info(f"Authenticated via Databricks SDK — host={self._host}")
        except Exception as sdk_err:
            logger.warning(f"Databricks SDK auth failed ({sdk_err}), falling back...")

        if not self._token and token:
            self._token = token
        if not self._host and host:
            self._host = host.rstrip("/")
        if not self._token:
            self._token = os.environ.get("DATABRICKS_TOKEN")
        if not self._host:
            self._host = (os.environ.get("DATABRICKS_HOST") or "").rstrip("/")

        if not self._host or not self._token:
            raise ValueError(
                "Could not resolve Databricks credentials.\n"
                "Provide host+token explicitly, set DATABRICKS_HOST/DATABRICKS_TOKEN, "
                "or configure a .databrickscfg profile."
            )

    def _get_auth_headers(self) -> Dict[str, str]:
        return {"Authorization": f"Bearer {self._token}", "Content-Type": "application/json"}

    def ask_sync(self, question: str, mode: str = "deep_research", timeout_minutes: float = 10.0) -> GenieResult:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = None
        if loop and loop.is_running():
            import nest_asyncio
            nest_asyncio.apply()
            return loop.run_until_complete(self.ask(question, mode, timeout_minutes))
        return asyncio.run(self.ask(question, mode, timeout_minutes))

    async def ask(self, question: str, mode: str = "deep_research", timeout_minutes: float = 10.0) -> GenieResult:
        return await self._deep_research_search(question, timeout_minutes)

    async def _deep_research_search(self, question: str, timeout_minutes: float) -> GenieResult:
        try:
            conversation_id = await self._create_dr_conversation(question)
            if not conversation_id:
                return GenieResult(success=False, error="Failed to create Deep Research conversation", is_deep_research=True)
            message_id = await self._send_dr_message(conversation_id, question)
            if not message_id:
                return GenieResult(success=False, error="Failed to send Deep Research message", is_deep_research=True)
            return await self._poll_dr_results(conversation_id, message_id, timeout_minutes)
        except Exception as e:
            logger.error(f"Deep Research failed: {e}")
            return GenieResult(success=False, error=str(e), is_deep_research=True)

    async def _create_dr_conversation(self, query: str) -> Optional[str]:
        url = f"{self._host}/api/2.0/data-rooms/{self._space_id}/conversations"
        payload = {"title": query[:100], "model": "SMART_AI", "visibility": "PRIVATE", "conversation_type": "DEEP_RESEARCH"}
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, headers=self._get_auth_headers(), json=payload)
            if resp.status_code != 200:
                logger.error(f"Create DR conversation failed: {resp.status_code}")
                return None
            data = resp.json()
            return data.get("conversation_id") or data.get("id")

    async def _send_dr_message(self, conversation_id: str, content: str) -> Optional[str]:
        url = f"{self._host}/api/2.0/data-rooms/{self._space_id}/conversations/{conversation_id}/messages"
        payload = {"content": content, "client_context": {"genie_app_context": {"force_deep_research_planning": True, "enable_verification": False}}}
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, headers=self._get_auth_headers(), json=payload)
            if resp.status_code != 200:
                logger.error(f"Send DR message failed: {resp.status_code}")
                return None
            data = resp.json()
            return data.get("message_id") or data.get("id")

    async def _poll_dr_results(self, conversation_id: str, message_id: str, timeout_minutes: float) -> GenieResult:
        url = f"{self._host}/api/2.0/data-rooms/{self._space_id}/conversations/{conversation_id}/messages/{message_id}"
        deadline = time.time() + timeout_minutes * 60
        poll_interval = 2.0
        async with httpx.AsyncClient(timeout=30.0) as client:
            while time.time() < deadline:
                try:
                    resp = await client.get(url, headers=self._get_auth_headers())
                    if resp.status_code != 200:
                        await asyncio.sleep(poll_interval)
                        continue
                    data = resp.json()
                    status = data.get("status", "UNKNOWN")
                    is_final = data.get("is_final", False)
                    if status == "COMPLETED" and is_final:
                        return self._extract_dr_results(data)
                    if status in ("FAILED", "CANCELLED"):
                        err = data.get("error", {})
                        return GenieResult(success=False, error=err.get("message", f"Query {status}"), is_deep_research=True)
                    await asyncio.sleep(poll_interval)
                    poll_interval = min(poll_interval * 1.1, 5.0)
                except Exception as e:
                    logger.warning(f"Poll error: {e}")
                    await asyncio.sleep(poll_interval)
        return GenieResult(success=False, error="Timeout waiting for Deep Research", is_deep_research=True)

    def _extract_dr_results(self, data: Dict[str, Any]) -> GenieResult:
        report_summary = None
        generated_sql = None
        for att in data.get("attachments", []):
            if "deep_research_report" in att:
                report_summary = att["deep_research_report"].get("report_summary")
            if "query" in att and not generated_sql:
                generated_sql = att["query"].get("query")
        return GenieResult(success=True, answer_text=report_summary, sql=generated_sql, is_deep_research=True, raw_response=data)


# COMMAND ----------

# ============================================================================
# Batch Deep Research — process each active question
# ============================================================================

from pyspark.sql.functions import col, max as spark_max
from pyspark.sql.types import StructType, StructField, LongType, TimestampType, StringType
from datetime import datetime


def extract_summary(text: str) -> str:
    """Extract content under ## Summary, stopping before ## Warning."""
    if not text:
        return ""
    pattern = r"(?i)#{1,4}\s+summary.*?\n([\s\S]*?)(?=\n#{1,4}\s+warning|\n#{1,4}\s|\Z)"
    match = re.search(pattern, text)
    if match:
        return match.group(1).strip()
    pattern2 = r"(?i)\*\*summary[^*]*\*\*[:\s]*([\s\S]*?)(?=\*\*warning|\n#{1,4}\s|\Z)"
    match2 = re.search(pattern2, text)
    if match2:
        return match2.group(1).strip()
    return ""


def extract_warning(text: str) -> str:
    """Extract warning flag (0 or 1) from Genie response markdown."""
    if not text:
        return ""
    pattern_heading = r"(?i)#{1,4}\s+warnings?\s*[:\-]?\s*([01]?).*?\n?([\s\S]*?)(?=\n#{1,4}\s|\Z)"
    match = re.search(pattern_heading, text)
    if match:
        inline_val = match.group(1).strip()
        if inline_val in ("0", "1"):
            return inline_val
        body = match.group(2).strip()
        digit = re.search(r"\b([01])\b", body)
        if digit:
            return digit.group(1)
    pattern_bold = r"(?i)\*\*warnings?\*\*\s*[:\-]?\s*([01])"
    match2 = re.search(pattern_bold, text)
    if match2:
        return match2.group(1)
    tail = text[-200:]
    match3 = re.search(r"(?i)warning\s*[:\-]\s*([01])", tail)
    if match3:
        return match3.group(1)
    return ""


# Load active questions
questions_df = spark.table(QUESTIONS_TABLE)
seed_temp_df = spark.createDataFrame(seed_rows)
seed_temp_df.createOrReplaceTempView("_seed_latest")

active_questions = (
    questions_df
    .filter(col("is_active") == True)
    .join(seed_temp_df.select("question_category", "question"), ["question_category", "question"], "inner")
    .groupBy("question_category", "question")
    .agg(spark_max("id").alias("id"))
    .select("id", "question_category", "question")
    .orderBy("question_category", "id")
    .collect()
)

if not active_questions:
    print("No active questions found — nothing to do.")
else:
    print(f"{len(active_questions)} active question(s) to process.\n")

# COMMAND ----------

SPACE_ID = CFG["genie"]["space_id"]
genie = DatabricksGenieClient(space_id=SPACE_ID)

results_rows = []

for row in active_questions:
    q_id = row["id"]
    q_category = row["question_category"]
    q_text = row["question"]

    print(f"[{q_id}] ({q_category}) {q_text[:100]}...")

    response_text = ""
    summary_text = ""
    warning = None

    try:
        result = genie.ask_sync(question=q_text, mode="deep_research", timeout_minutes=15.0)

        if result.success:
            response_text = result.answer_text or ""
            summary_text = extract_summary(response_text)
            response_warning = extract_warning(response_text)
            if response_warning:
                warning = response_warning
            elif not summary_text:
                warning = "No summary section found in the response."
            print(f"   Done — {len(response_text)} chars response, warning={warning!r}")
        else:
            warning = f"Deep Research failed: {result.error}"
            print(f"   Failed — {result.error}")

    except Exception as e:
        warning = f"Exception: {str(e)}"
        print(f"   Exception — {e}")

    results_rows.append(Row(
        question_id=q_id,
        timestamp=datetime.utcnow(),
        question_category=q_category,
        question=q_text,
        response=response_text,
        summary=summary_text,
        warning=warning,
    ))

# COMMAND ----------

# ============================================================================
# Write results to the analysis table
# ============================================================================

if results_rows:
    schema = StructType([
        StructField("question_id",       LongType(),      True),
        StructField("timestamp",         TimestampType(), True),
        StructField("question_category", StringType(),    True),
        StructField("question",          StringType(),    True),
        StructField("response",          StringType(),    True),
        StructField("summary",           StringType(),    True),
        StructField("warning",           StringType(),    True),
    ])
    results_spark_df = spark.createDataFrame(results_rows, schema=schema)
    results_spark_df.write.mode("append").saveAsTable(ANALYSIS_TABLE)
    print(f"\n{len(results_rows)} result(s) written to {ANALYSIS_TABLE}.")
else:
    print("\nNo results to write.")
