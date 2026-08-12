# Databricks notebook source
# MAGIC %pip install databricks-sdk databricks-vectorsearch pypdf pyyaml --quiet
# MAGIC

# COMMAND ----------

# ============================================================================
# Setup: Vector Search Index
# ============================================================================
# Run ONCE (or re-run to refresh). This notebook:
#   1. Reads pipeline_config.yml from the repo root
#   2. Validates all placeholders are filled
#   3. Reads playbook PDFs (from UC Volume or workspace repo path)
#   4. Chunks the text and writes to a Delta table with Change Data Feed
#   5. Creates (or syncs) a Vector Search index on that table
#
# Re-running is safe — it upserts chunks via MERGE and calls sync_index()
# if the index already exists, or create_delta_sync_index() on first run.
#
# Run this notebook from the Databricks UI or via create_workflow.py before
# scheduling the pipeline workflow for the first time.
# ============================================================================

# COMMAND ----------

import os
import re
import yaml
import json
import hashlib
import datetime
from pathlib import Path

def _resolve_repo_root() -> str:
    try:
        nb_path = (
            dbutils.notebook.entry_point
            .getDbutils().notebook().getContext()
            .notebookPath().get()
        )
    except Exception:
        raise RuntimeError("This notebook must be run inside Databricks.")
    # Goes up three levels: past notebook name, past 'setup/', past any subfolder
    # notebook is at <repo_root>/setup/<name>  → two dirname calls
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

CATALOG       = CFG["catalog"]["name"]
SCHEMA        = CFG["catalog"]["schema"]
TABLE_PREFIX  = CFG["catalog"]["table_prefix"]
VS_ENDPOINT   = CFG["vector_search"]["endpoint"]
EMBED_MODEL   = CFG["vector_search"].get("embedding_model", "databricks-gte-large-en")

CHUNKS_TABLE  = full_table(CFG, "playbook_chunks")
INDEX_NAME    = f"{CHUNKS_TABLE}_index"

SOURCE_TYPE   = CFG["playbooks"]["source_type"]        # "volume" or "local"
VOLUME_PATH   = CFG["playbooks"].get("volume_path", "")
LOCAL_PATH    = CFG["playbooks"].get("local_path", "pipeline_playbook_generator/generated/pdfs")
SOURCES       = CFG["playbooks"].get("sources", [])

print(f"Config loaded — source_type={SOURCE_TYPE}")
print(f"  Chunks table : {CHUNKS_TABLE}")
print(f"  VS index     : {INDEX_NAME}")
print(f"  {len(SOURCES)} source file(s) configured.")

# COMMAND ----------

# ============================================================================
# Create chunks table with Change Data Feed (required for VS sync)
# ============================================================================

spark.sql(f"CREATE SCHEMA IF NOT EXISTS {CATALOG}.{SCHEMA}")

spark.sql(f"""
CREATE TABLE IF NOT EXISTS {CHUNKS_TABLE} (
  chunk_id          STRING NOT NULL,
  source_file       STRING,
  question_category STRING,
  chunk_index       INT,
  chunk_text        STRING
)
USING DELTA
TBLPROPERTIES (delta.enableChangeDataFeed = true)
COMMENT 'Playbook PDF chunks for Vector Search indexing'
""")

print(f"Table ready (CDF enabled): {CHUNKS_TABLE}")

# COMMAND ----------

# ============================================================================
# PDF text extraction and chunking
# ============================================================================

import pypdf
import textwrap

CHUNK_SIZE    = 800   # characters per chunk
CHUNK_OVERLAP = 100   # overlap between adjacent chunks


def _pdf_path(source_entry: dict) -> str:
    """Return the filesystem path for a PDF based on source_type."""
    pdf_file = source_entry["pdf_file"]
    if SOURCE_TYPE == "volume":
        if not VOLUME_PATH:
            raise ValueError(
                "playbooks.volume_path must be set when source_type is 'volume'.\n"
                "Edit pipeline_config.yml."
            )
        return f"{VOLUME_PATH}/{pdf_file}"
    else:  # local
        base = f"{REPO_ROOT}/{LOCAL_PATH}"
        return f"{base}/{pdf_file}"


def _extract_text(path: str) -> str:
    """Extract all text from a PDF at the given path."""
    reader = pypdf.PdfReader(path)
    pages = []
    for page in reader.pages:
        text = page.extract_text() or ""
        pages.append(text.strip())
    return "\n\n".join(p for p in pages if p)


def _chunk_text(text: str) -> list:
    """Split text into overlapping character windows."""
    chunks = []
    start = 0
    idx = 0
    while start < len(text):
        end = start + CHUNK_SIZE
        chunk = text[start:end].strip()
        if chunk:
            chunks.append((idx, chunk))
            idx += 1
        start = end - CHUNK_OVERLAP
    return chunks


def _chunk_id(source_file: str, chunk_index: int) -> str:
    """Deterministic ID so re-runs can MERGE without duplicating rows."""
    raw = f"{source_file}::{chunk_index}"
    return hashlib.md5(raw.encode()).hexdigest()


# COMMAND ----------

# ============================================================================
# Process each source PDF and MERGE into the chunks table
# ============================================================================

from pyspark.sql import Row
from pyspark.sql.types import StructType, StructField, StringType, IntegerType

all_chunk_rows = []

for source in SOURCES:
    pdf_file = source["pdf_file"]
    category = source["question_category"]
    path     = _pdf_path(source)

    print(f"Processing: {pdf_file}  (category={category})")
    print(f"  Path: {path}")

    try:
        text = _extract_text(path)
        raw_chunks = _chunk_text(text)
        print(f"  Extracted {len(text):,} chars → {len(raw_chunks)} chunks.")
    except Exception as e:
        print(f"  ERROR reading PDF: {e}")
        print("  Skipping this source — fix the path or upload the PDF first.")
        continue

    for idx, chunk_text in raw_chunks:
        all_chunk_rows.append(Row(
            chunk_id=_chunk_id(pdf_file, idx),
            source_file=pdf_file,
            question_category=category,
            chunk_index=idx,
            chunk_text=chunk_text,
        ))

if not all_chunk_rows:
    raise RuntimeError(
        "No chunks were produced. Check that PDFs exist at the configured paths.\n"
        f"  source_type : {SOURCE_TYPE}\n"
        f"  volume_path : {VOLUME_PATH or '(not set)'}\n"
        f"  local_path  : {REPO_ROOT}/{LOCAL_PATH}\n"
        "If using source_type='volume', run setup/upload_pdfs.py first."
    )

schema = StructType([
    StructField("chunk_id",          StringType(),  False),
    StructField("source_file",       StringType(),  True),
    StructField("question_category", StringType(),  True),
    StructField("chunk_index",       IntegerType(), True),
    StructField("chunk_text",        StringType(),  True),
])
chunks_df = spark.createDataFrame(all_chunk_rows, schema=schema)
chunks_df.createOrReplaceTempView("_new_chunks")

existing_chunks_df = spark.table(CHUNKS_TABLE).select(chunks_df.columns)
chunks_changed = (
    chunks_df.subtract(existing_chunks_df).limit(1).count() > 0
    or existing_chunks_df.subtract(chunks_df).limit(1).count() > 0
)

if chunks_changed:
    spark.sql(f"""
MERGE INTO {CHUNKS_TABLE} AS target
USING _new_chunks AS src
ON target.chunk_id = src.chunk_id
WHEN MATCHED THEN
  UPDATE SET target.chunk_text        = src.chunk_text,
             target.question_category = src.question_category,
             target.source_file       = src.source_file,
             target.chunk_index       = src.chunk_index
WHEN NOT MATCHED THEN
  INSERT (chunk_id, source_file, question_category, chunk_index, chunk_text)
  VALUES (src.chunk_id, src.source_file, src.question_category, src.chunk_index, src.chunk_text)
""")
    print("Chunk content changed; Delta source updated.")
else:
    print("Chunk content is unchanged; Delta update and Vector Search sync can be skipped.")

total = spark.table(CHUNKS_TABLE).count()
print(f"\nChunks table now has {total} rows.")

# COMMAND ----------

# ============================================================================
# Create or sync the Vector Search index
# ============================================================================

from databricks.vector_search.client import VectorSearchClient

vs_client = VectorSearchClient()

try:
    index = vs_client.get_index(endpoint_name=VS_ENDPOINT, index_name=INDEX_NAME)
    print(f"Index already exists: {INDEX_NAME}")
    print("Waiting for any provisioning or prior update to finish...")
    index.wait_until_ready(verbose=True, timeout=datetime.timedelta(minutes=15), wait_for_updates=False)
    if chunks_changed:
        print("Triggering sync to pick up new/updated chunks...")
        index.sync()
        print("Sync triggered.")
except Exception as e:
    if "does not exist" in str(e).lower() or "not found" in str(e).lower():
        print(f"Creating new VS index: {INDEX_NAME}")
        index = vs_client.create_delta_sync_index(
            endpoint_name=VS_ENDPOINT,
            index_name=INDEX_NAME,
            source_table_name=CHUNKS_TABLE,
            pipeline_type="TRIGGERED",
            primary_key="chunk_id",
            embedding_source_column="chunk_text",
            embedding_model_endpoint_name=EMBED_MODEL,
        )
        print("Index creation initiated. It may take a few minutes to become ONLINE.")
    else:
        raise

print("Waiting for the Vector Search index to become queryable...")
index.wait_until_ready(
    verbose=True,
    timeout=datetime.timedelta(minutes=15),
    wait_for_updates=chunks_changed,
)
print(f"\nSetup complete. VS index: {INDEX_NAME}")
print("Next step: run pipeline/trends_analysis.py to start the pipeline.")
