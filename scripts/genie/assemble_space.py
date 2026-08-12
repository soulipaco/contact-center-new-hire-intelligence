#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

import requests
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
GENIE_ROOT = REPO_ROOT / "genie"
SOURCE_ROOT = GENIE_ROOT / "source"


def load_yaml(path: Path):
    with path.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def load_yaml_dir(path: Path):
    return [load_yaml(item) for item in sorted(path.glob("*.yml")) if item.is_file()]


def assemble_payload(warehouse_id: str, parent_path: str) -> dict:
    config = load_yaml(GENIE_ROOT / "config" / "room.yml")
    sources = load_yaml(SOURCE_ROOT / "data_sources" / "tables.yml")
    tables = []
    for source in sources["tables"]:
        metadata = load_yaml(SOURCE_ROOT / source["column_metadata_file"])
        column_configs = []
        for column in metadata.get("columns", []):
            item = {"column_name": column["column_name"]}
            for key in ["exclude", "enable_format_assistance", "enable_entity_matching"]:
                if key in column:
                    item[key] = column[key]
            column_configs.append(item)
        tables.append({
            "identifier": source["identifier"],
            "description": [source.get("description", "")],
            "column_configs": sorted(column_configs, key=lambda row: row["column_name"]),
        })

    examples = load_yaml_dir(SOURCE_ROOT / "instructions" / "example_sql")
    filters = load_yaml_dir(SOURCE_ROOT / "instructions" / "sql_snippets" / "filters")
    measures = load_yaml_dir(SOURCE_ROOT / "instructions" / "sql_snippets" / "measures")
    benchmarks = load_yaml_dir(SOURCE_ROOT / "benchmarks")
    general = (SOURCE_ROOT / "instructions" / "general.md").read_text(encoding="utf-8")

    serialized = {
        "version": 2,
        "config": {"sample_questions": sorted([
            {"id": row["id"], "question": [row["question"]]} for row in config["sample_questions"]
        ], key=lambda row: row["id"])},
        "data_sources": {"tables": sorted(tables, key=lambda row: row["identifier"])},
        "instructions": {
            "text_instructions": [{"id": "c3f38aef0fce47dfaf0f0d489c55a101", "content": [general]}],
            "example_question_sqls": sorted([
                {"id": row["id"], "question": [row["question"]], "sql": [row["sql"]], **({"usage_guidance": [row["usage_guidance"]]} if row.get("usage_guidance") else {})}
                for row in examples
            ], key=lambda row: row["id"]),
            "sql_snippets": {
                "filters": sorted([
                    {"id": row["id"], "display_name": row["display_name"], "sql": [row["sql"]], "synonyms": row.get("synonyms", []), "instruction": [row.get("instruction", "")]}
                    for row in filters
                ], key=lambda row: row["id"]),
                "measures": sorted([
                    {"id": row["id"], "alias": row["alias"], "display_name": row["display_name"], "sql": [row["sql"]], "synonyms": row.get("synonyms", []), "instruction": [row.get("instruction", "")]}
                    for row in measures
                ], key=lambda row: row["id"]),
                "expressions": [],
            },
        },
        "benchmarks": {"questions": sorted([
            {"id": row["id"], "question": [row["question"]], "answer": [{"format": row.get("answer_format", "SQL"), "content": [row["sql"]]}]}
            for row in benchmarks
        ], key=lambda row: row["id"])},
    }
    return {
        "title": config["title"],
        "description": config["description"],
        "warehouse_id": warehouse_id,
        "parent_path": parent_path,
        "serialized_space": json.dumps(serialized),
    }


def deploy(payload: dict, space_id: str | None, dry_run: bool, profile: str | None):
    serialized = json.loads(payload["serialized_space"])
    if dry_run:
        print(json.dumps({
            "title": payload["title"],
            "warehouse_id": payload["warehouse_id"],
            "parent_path": payload["parent_path"],
            "tables": len(serialized["data_sources"]["tables"]),
            "sample_questions": len(serialized["config"]["sample_questions"]),
            "example_sql": len(serialized["instructions"]["example_question_sqls"]),
            "filters": len(serialized["instructions"]["sql_snippets"]["filters"]),
            "measures": len(serialized["instructions"]["sql_snippets"]["measures"]),
            "benchmarks": len(serialized["benchmarks"]["questions"]),
        }, indent=2))
        return None

    if profile:
        method = "patch" if space_id else "post"
        endpoint = "/api/2.0/genie/spaces" + (f"/{space_id}" if space_id else "")
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", encoding="utf-8", delete=False) as handle:
            json.dump(payload, handle)
            payload_path = handle.name
        try:
            command = ["databricks", "api", method, endpoint, "--json", f"@{payload_path}", "--profile", profile, "--output", "json"]
            completed = subprocess.run(command, check=True, capture_output=True, text=True)
            return json.loads(completed.stdout) if completed.stdout.strip() else {}
        except FileNotFoundError as exc:
            raise RuntimeError("Databricks CLI was not found on PATH.") from exc
        except subprocess.CalledProcessError as exc:
            raise RuntimeError(f"Databricks CLI deployment failed: {exc.stderr.strip()}") from exc
        finally:
            Path(payload_path).unlink(missing_ok=True)

    host = os.environ.get("DATABRICKS_HOST", "").rstrip("/")
    token = os.environ.get("DATABRICKS_TOKEN")
    if not host or not token:
        raise RuntimeError("Use --profile for CLI OAuth, or set DATABRICKS_HOST and DATABRICKS_TOKEN.")
    url = f"{host}/api/2.0/genie/spaces" + (f"/{space_id}" if space_id else "")
    response = requests.patch(url, headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"}, json=payload, timeout=90) if space_id else requests.post(url, headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"}, json=payload, timeout=90)
    response.raise_for_status()
    return response.json()


def main() -> int:
    parser = argparse.ArgumentParser(description="Deploy the contact-center new-hire Genie space")
    parser.add_argument("--warehouse-id", required=True)
    parser.add_argument("--parent-path", required=True)
    parser.add_argument("--space-id")
    parser.add_argument("--profile", help="Databricks CLI profile for unified OAuth authentication")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    result = deploy(assemble_payload(args.warehouse_id, args.parent_path), args.space_id, args.dry_run, args.profile)
    if result:
        print(f"Deploy successful. Space ID: {result.get('space_id') or result.get('id')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
