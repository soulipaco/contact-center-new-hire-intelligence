#!/usr/bin/env python3
"""Initialize, validate, and render a customer source adapter."""

from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG = ROOT / "config/project.yml"
CUSTOMER_EXAMPLE = ROOT / "config/project.customer.example.yml"
DEFAULT_OUTPUT = ROOT / "lakehouse/generated/00_customer_adapter.sql"
DEFAULT_BUILD_ROOT = ROOT / "build"
IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
THREE_LEVEL_NAME = re.compile(
    r"^[A-Za-z_][A-Za-z0-9_]*\.[A-Za-z_][A-Za-z0-9_]*\.[A-Za-z_][A-Za-z0-9_]*$"
)
PROJECT_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")

REQUIRED_MAPPINGS = {
    "observations": ("performance_date", "agent_id", "kpi", "numerator", "denominator", "volume"),
    "agents": (
        "agent_id", "service_program", "first_day_in_production", "class_id",
        "cohort_id", "cohort_name", "snapshot_effective_from",
    ),
    "targets": (
        "service_program", "cohort_id", "kpi", "target", "direction", "format",
        "lower_limit", "upper_limit", "effective_from", "effective_to", "target_version",
    ),
    "training_classes": ("cohort_id", "cohort_name", "service_program", "class_id", "class_start_date"),
}


class ConfigError(ValueError):
    pass


def load_config(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise ConfigError(f"configuration does not exist: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ConfigError("configuration root must be a mapping")
    return data


def _require_mapping(value: Any, label: str, errors: list[str]) -> dict[str, Any]:
    if not isinstance(value, dict):
        errors.append(f"{label} must be a mapping")
        return {}
    return value


def validate_config(config: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    project = _require_mapping(config.get("project"), "project", errors)
    analytics = _require_mapping(config.get("analytics"), "analytics", errors)
    features = _require_mapping(config.get("features"), "features", errors)
    source = _require_mapping(config.get("source"), "source", errors)

    mode = project.get("mode")
    if mode not in {"demo", "customer"}:
        errors.append("project.mode must be demo or customer")
    if not isinstance(project.get("name"), str) or not PROJECT_NAME.fullmatch(project["name"]):
        errors.append("project.name must contain only letters, numbers, dots, underscores, or hyphens")
    for label, value in [("project.catalog", project.get("catalog"))]:
        if not isinstance(value, str) or not IDENTIFIER.fullmatch(value):
            errors.append(f"{label} must be a simple SQL identifier")
    schemas = _require_mapping(project.get("schemas"), "project.schemas", errors)
    for layer in ("bronze", "silver", "gold", "models"):
        value = schemas.get(layer)
        if not isinstance(value, str) or not IDENTIFIER.fullmatch(value):
            errors.append(f"project.schemas.{layer} must be a simple SQL identifier")

    integer_fields = {
        "new_hire_days": 1,
        "tenured_baseline_min_days": 2,
        "learning_curve_max_days": 2,
        "forecast_periods": 1,
    }
    for field, minimum in integer_fields.items():
        value = analytics.get(field)
        if not isinstance(value, int) or isinstance(value, bool) or value < minimum:
            errors.append(f"analytics.{field} must be an integer >= {minimum}")
    if isinstance(analytics.get("new_hire_days"), int) and isinstance(analytics.get("tenured_baseline_min_days"), int):
        if analytics["tenured_baseline_min_days"] <= analytics["new_hire_days"]:
            errors.append("analytics.tenured_baseline_min_days must exceed analytics.new_hire_days")
    interval = analytics.get("forecast_interval_width")
    if not isinstance(interval, (int, float)) or isinstance(interval, bool) or not 0 < interval < 1:
        errors.append("analytics.forecast_interval_width must be between 0 and 1")
    outliers = _require_mapping(analytics.get("outliers"), "analytics.outliers", errors)
    for field in ("z_score_threshold", "iqr_multiplier"):
        value = outliers.get(field)
        if not isinstance(value, (int, float)) or isinstance(value, bool) or value <= 0:
            errors.append(f"analytics.outliers.{field} must be positive")

    feature_names = {
        "learning_curve_ml", "forecasting", "genie", "dashboard",
        "action_intelligence", "vector_search",
    }
    for feature in feature_names:
        if not isinstance(features.get(feature), bool):
            errors.append(f"features.{feature} must be true or false")
    for core_feature in ("learning_curve_ml", "forecasting"):
        if features.get(core_feature) is False:
            errors.append(f"features.{core_feature} cannot be disabled in the current release")
    if features.get("action_intelligence") and not features.get("genie"):
        errors.append("features.action_intelligence requires features.genie")
    if features.get("action_intelligence") and not features.get("vector_search"):
        errors.append("features.action_intelligence requires features.vector_search")

    if mode == "demo":
        if source.get("type") != "synthetic":
            errors.append("demo mode requires source.type: synthetic")
        seed = source.get("synthetic_seed")
        if not isinstance(seed, int) or isinstance(seed, bool):
            errors.append("demo mode requires an integer source.synthetic_seed")
    elif mode == "customer":
        if source.get("type") != "unity_catalog":
            errors.append("customer mode currently requires source.type: unity_catalog")
        tables = _require_mapping(source.get("tables"), "source.tables", errors)
        mappings = _require_mapping(source.get("mappings"), "source.mappings", errors)
        for contract, required_columns in REQUIRED_MAPPINGS.items():
            table = tables.get(contract)
            if not isinstance(table, str) or not THREE_LEVEL_NAME.fullmatch(table):
                errors.append(f"source.tables.{contract} must be a three-level Unity Catalog name")
            mapping = _require_mapping(mappings.get(contract), f"source.mappings.{contract}", errors)
            for column in required_columns:
                source_column = mapping.get(column)
                if not isinstance(source_column, str) or not IDENTIFIER.fullmatch(source_column):
                    errors.append(f"source.mappings.{contract}.{column} must be a source column name")
            for canonical, source_column in mapping.items():
                if canonical not in set(required_columns) | set(_optional_columns(contract)):
                    errors.append(f"unknown canonical mapping source.mappings.{contract}.{canonical}")
                if not isinstance(source_column, str) or not IDENTIFIER.fullmatch(source_column):
                    errors.append(f"source.mappings.{contract}.{canonical} must be a source column name")
    return errors


def _optional_columns(contract: str) -> tuple[str, ...]:
    return {
        "observations": (),
        "agents": ("agent_label", "site", "market", "language", "channel", "line_of_business", "wave"),
        "targets": (),
        "training_classes": ("cohort_abbreviation", "class_sort"),
    }[contract]


def _qname(name: str) -> str:
    return ".".join(f"`{part}`" for part in name.split("."))


def _column(mapping: dict[str, str], name: str, default: str, cast: str | None = None) -> str:
    expression = f"`{mapping[name]}`" if name in mapping else default
    return f"CAST({expression} AS {cast})" if cast else expression


def render_customer_adapter(config: dict[str, Any]) -> str:
    errors = validate_config(config)
    if errors:
        raise ConfigError("\n".join(errors))
    if config["project"]["mode"] != "customer":
        raise ConfigError("render-adapter requires project.mode: customer")

    project, source = config["project"], config["source"]
    bronze = f"{project['catalog']}.{project['schemas']['bronze']}"
    tables, mappings = source["tables"], source["mappings"]
    o, a, t, c = (mappings[name] for name in ("observations", "agents", "targets", "training_classes"))

    return f'''-- Databricks notebook source
-- GENERATED FILE. Edit the YAML configuration, not this notebook.
-- Maps customer-owned Unity Catalog tables to canonical Bronze contracts.

CREATE SCHEMA IF NOT EXISTS {_qname(bronze)};

-- COMMAND ----------
CREATE OR REPLACE TABLE {_qname(bronze + '.bronze_agent_kpi_daily_raw')} USING DELTA AS
SELECT
  {_column(o, 'performance_date', 'NULL', 'DATE')} performance_date,
  {_column(o, 'agent_id', 'NULL', 'BIGINT')} agent_id,
  {_column(o, 'kpi', 'NULL', 'STRING')} kpi,
  {_column(o, 'numerator', 'NULL', 'DOUBLE')} nominator,
  {_column(o, 'denominator', 'NULL', 'DOUBLE')} denominator,
  {_column(o, 'volume', 'NULL', 'INT')} volume,
  ROW_NUMBER() OVER (ORDER BY `{o['performance_date']}`, `{o['agent_id']}`, `{o['kpi']}`) source_sequence,
  CURRENT_TIMESTAMP() source_load_timestamp,
  CAST(NULL AS BIGINT) synthetic_seed
FROM {_qname(tables['observations'])};

-- COMMAND ----------
CREATE OR REPLACE TABLE {_qname(bronze + '.bronze_agent_snapshot_raw')} USING DELTA AS
SELECT
  {_column(a, 'agent_id', 'NULL', 'BIGINT')} agent_id,
  {_column(a, 'agent_label', "CONCAT('Agent ', SUBSTRING(SHA2(CAST(`" + a['agent_id'] + "` AS STRING), 256), 1, 12))", 'STRING')} agent_label,
  {_column(a, 'service_program', 'NULL', 'STRING')} service_program,
  {_column(a, 'site', "'Unknown'", 'STRING')} site,
  {_column(a, 'market', "'Unknown'", 'STRING')} market,
  {_column(a, 'language', "'Unknown'", 'STRING')} language,
  {_column(a, 'channel', "'Unknown'", 'STRING')} channel,
  {_column(a, 'line_of_business', "'Unknown'", 'STRING')} line_of_business,
  {_column(a, 'first_day_in_production', 'NULL', 'DATE')} first_day_in_production,
  {_column(a, 'class_id', 'NULL', 'STRING')} class_id,
  {_column(a, 'cohort_id', 'NULL', 'BIGINT')} cohort_id,
  {_column(a, 'cohort_name', 'NULL', 'STRING')} cohort_name,
  {_column(a, 'wave', "'Unknown'", 'STRING')} wave,
  {_column(a, 'snapshot_effective_from', 'NULL', 'DATE')} snapshot_effective_from,
  CURRENT_TIMESTAMP() source_load_timestamp,
  CAST(NULL AS BIGINT) synthetic_seed
FROM {_qname(tables['agents'])};

-- COMMAND ----------
CREATE OR REPLACE TABLE {_qname(bronze + '.bronze_kpi_target_raw')} USING DELTA AS
SELECT
  {_column(t, 'service_program', 'NULL', 'STRING')} service_program,
  {_column(t, 'cohort_id', 'NULL', 'BIGINT')} cohort_id,
  {_column(t, 'kpi', 'NULL', 'STRING')} kpi,
  {_column(t, 'target', 'NULL', 'DOUBLE')} target,
  CASE LOWER({_column(t, 'direction', 'NULL', 'STRING')})
    WHEN 'higher_is_better' THEN 1 WHEN 'lower_is_better' THEN -1
    ELSE CAST({_column(t, 'direction', 'NULL', 'STRING')} AS INT) END normal,
  CASE LOWER({_column(t, 'format', 'NULL', 'STRING')})
    WHEN 'percentage' THEN 'Percentage' WHEN 'number' THEN 'Number'
    ELSE {_column(t, 'format', 'NULL', 'STRING')} END kpi_format,
  {_column(t, 'lower_limit', 'NULL', 'DOUBLE')} lower_limit,
  {_column(t, 'upper_limit', 'NULL', 'DOUBLE')} upper_limit,
  {_column(t, 'effective_from', 'NULL', 'DATE')} effective_from,
  {_column(t, 'effective_to', 'NULL', 'DATE')} effective_to,
  {_column(t, 'target_version', 'NULL', 'INT')} target_version,
  CURRENT_TIMESTAMP() source_load_timestamp,
  CAST(NULL AS BIGINT) synthetic_seed
FROM {_qname(tables['targets'])};

-- COMMAND ----------
CREATE OR REPLACE TABLE {_qname(bronze + '.bronze_training_class_raw')} USING DELTA AS
SELECT
  {_column(c, 'cohort_id', 'NULL', 'BIGINT')} cohort_id,
  {_column(c, 'cohort_name', 'NULL', 'STRING')} cohort_name,
  {_column(c, 'cohort_abbreviation', "SUBSTRING(SHA2(CAST(`" + c['cohort_id'] + "` AS STRING), 256), 1, 8)", 'STRING')} cohort_abbreviation,
  {_column(c, 'service_program', 'NULL', 'STRING')} service_program,
  {_column(c, 'class_id', 'NULL', 'STRING')} class_id,
  {_column(c, 'class_start_date', 'NULL', 'DATE')} class_start_date,
  {_column(c, 'class_sort', '1', 'INT')} class_sort,
  CURRENT_TIMESTAMP() source_load_timestamp,
  CAST(NULL AS BIGINT) synthetic_seed
FROM {_qname(tables['training_classes'])};

-- COMMAND ----------
-- Runtime preflight: fail before Silver/Gold when the canonical contracts are unsafe.
SELECT
  ASSERT_TRUE(COUNT(*) > 0, 'observations contract is empty'),
  ASSERT_TRUE(COUNT_IF(performance_date IS NULL OR agent_id IS NULL OR kpi IS NULL) = 0, 'observations contain null keys'),
  ASSERT_TRUE(COUNT_IF(denominator <= 0 OR volume < 0) = 0, 'observations contain invalid denominator or volume')
FROM {_qname(bronze + '.bronze_agent_kpi_daily_raw')};

WITH duplicate_keys AS (
  SELECT performance_date, agent_id, kpi
  FROM {_qname(bronze + '.bronze_agent_kpi_daily_raw')}
  GROUP BY performance_date, agent_id, kpi HAVING COUNT(*) > 1
)
SELECT ASSERT_TRUE(COUNT(*) = 0, 'observations violate date-agent-KPI grain') FROM duplicate_keys;

SELECT
  ASSERT_TRUE(COUNT(*) > 0, 'agents contract is empty'),
  ASSERT_TRUE(COUNT_IF(agent_id IS NULL OR cohort_id IS NULL OR first_day_in_production IS NULL OR snapshot_effective_from IS NULL) = 0, 'agents contain null required keys')
FROM {_qname(bronze + '.bronze_agent_snapshot_raw')};

SELECT
  ASSERT_TRUE(COUNT(*) > 0, 'targets contract is empty'),
  ASSERT_TRUE(COUNT_IF(normal NOT IN (-1, 1)) = 0, 'targets contain invalid KPI direction'),
  ASSERT_TRUE(COUNT_IF(effective_from > effective_to) = 0, 'targets contain invalid effective dates')
FROM {_qname(bronze + '.bronze_kpi_target_raw')};

WITH duplicate_cohorts AS (
  SELECT cohort_id FROM {_qname(bronze + '.bronze_training_class_raw')}
  GROUP BY cohort_id HAVING COUNT(*) > 1
)
SELECT ASSERT_TRUE(COUNT(*) = 0, 'training classes violate cohort grain') FROM duplicate_cohorts;
'''


def command_validate(path: Path) -> int:
    try:
        config = load_config(path)
        errors = validate_config(config)
    except ConfigError as exc:
        print(f"CONFIGURATION INVALID\n  - {exc}")
        return 1
    if errors:
        print("CONFIGURATION INVALID")
        for error in errors:
            print(f"  - {error}")
        return 1
    enabled = [name for name, value in config["features"].items() if value]
    print(f"CONFIGURATION VALID: mode={config['project']['mode']}; enabled={', '.join(enabled)}")
    return 0


def command_init(output: Path, force: bool) -> int:
    if output.exists() and not force:
        print(f"Refusing to overwrite {output}; pass --force to replace it.")
        return 1
    output.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(CUSTOMER_EXAMPLE, output)
    print(f"Created customer configuration: {output}")
    return 0


def command_render(path: Path, output: Path) -> int:
    try:
        sql = render_customer_adapter(load_config(path))
    except ConfigError as exc:
        print(f"ADAPTER NOT GENERATED\n  - {str(exc).replace(chr(10), chr(10) + '  - ')}")
        return 1
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(sql, encoding="utf-8", newline="\n")
    print(f"Generated customer adapter: {output}")
    return 0


def build_deployable(config: dict[str, Any], output: Path) -> Path:
    errors = validate_config(config)
    if errors:
        raise ConfigError("\n".join(errors))
    if output.exists():
        raise ConfigError(f"build output already exists: {output}")

    ignored = shutil.ignore_patterns(
        ".git", ".databricks", ".local", ".venv", "__pycache__", "*.pyc",
        "build", "legacy", "examples", "example_data.xlsx", "*.token", "*.secret",
    )
    shutil.copytree(ROOT, output, ignore=ignored)

    project = config["project"]
    catalog = project["catalog"]
    schemas = project["schemas"]
    replacements = {
        "workspace.contact_center_bronze": f"{catalog}.{schemas['bronze']}",
        "workspace.contact_center_silver": f"{catalog}.{schemas['silver']}",
        "workspace.contact_center_gold": f"{catalog}.{schemas['gold']}",
        "workspace.contact_center_models": f"{catalog}.{schemas['models']}",
        "/Volumes/workspace/contact_center_gold": f"/Volumes/{catalog}/{schemas['gold']}",
        'CATALOG = "workspace"': f'CATALOG = "{catalog}"',
        'BRONZE = f"{CATALOG}.contact_center_bronze"': f'BRONZE = f"{{CATALOG}}.{schemas["bronze"]}"',
        'GOLD = f"{CATALOG}.contact_center_gold"': f'GOLD = f"{{CATALOG}}.{schemas["gold"]}"',
        'MODEL_SCHEMA = f"{CATALOG}.contact_center_models"': f'MODEL_SCHEMA = f"{{CATALOG}}.{schemas["models"]}"',
        'EXPERIMENT = "/Shared/contact_center_new_hire_learning_curves"': f'EXPERIMENT = "/Shared/{project["name"]}_learning_curves"',
        'EXPERIMENT = "/Shared/contact_center_new_hire_forecasts"': f'EXPERIMENT = "/Shared/{project["name"]}_forecasts"',
        "name: workspace\n  schema: contact_center_gold": f"name: {catalog}\n  schema: {schemas['gold']}",
    }
    text_suffixes = {".py", ".sql", ".yml", ".yaml", ".json", ".md"}
    for file_path in output.rglob("*"):
        if not file_path.is_file() or file_path.suffix.lower() not in text_suffixes:
            continue
        text = file_path.read_text(encoding="utf-8")
        rendered = text
        for old, new in replacements.items():
            rendered = rendered.replace(old, new)
        if rendered != text:
            file_path.write_text(rendered, encoding="utf-8", newline="\n")

    rendered_config = output / "config/project.yml"
    rendered_config.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8", newline="\n")
    bundle_path = output / "databricks.yml"
    bundle_text = bundle_path.read_text(encoding="utf-8").replace(
        "name: contact-center-new-hire-intelligence",
        f"name: {project['name']}",
        1,
    )
    bundle_path.write_text(bundle_text, encoding="utf-8", newline="\n")
    (output / ".databricksignore").write_text(
        "__pycache__/\n*.pyc\n.local/\nbuild/\nlegacy/\n*.xlsx\n*.token\n*.secret\n",
        encoding="utf-8",
        newline="\n",
    )
    if project["mode"] == "customer":
        adapter = render_customer_adapter(config)
        adapter_path = output / "lakehouse/generated/00_customer_adapter.sql"
        adapter_path.parent.mkdir(parents=True, exist_ok=True)
        adapter_path.write_text(adapter, encoding="utf-8", newline="\n")
        jobs_path = output / "infrastructure/databricks/resources/jobs.yml"
        jobs = jobs_path.read_text(encoding="utf-8").replace(
            "../../../lakehouse/notebooks/01_generate_bronze.py",
            "../../../lakehouse/generated/00_customer_adapter.sql",
        )
        jobs_path.write_text(jobs, encoding="utf-8", newline="\n")

    analytics = config["analytics"]
    parameter_replacements = {
        "tenure_day <= 90": f"tenure_day <= {analytics['new_hire_days']}",
        "tenure_day > 90": f"tenure_day >= {analytics['tenured_baseline_min_days']}",
        "tenure_day BETWEEN 1 AND 90": f"tenure_day BETWEEN 1 AND {analytics['learning_curve_max_days']}",
        "EXPLODE(SEQUENCE(1, 90))": f"EXPLODE(SEQUENCE(1, {analytics['learning_curve_max_days']}))",
        "interval_width=0.80": f"interval_width={analytics['forecast_interval_width']}",
        '"interval_width": 0.80': f'"interval_width": {analytics["forecast_interval_width"]}',
        '"forecast_horizon_months": 6': f'"forecast_horizon_months": {analytics["forecast_periods"]}',
        "periods=6": f"periods={analytics['forecast_periods']}",
        "COUNT_IF(NOT is_actual) <> 6": f"COUNT_IF(NOT is_actual) <> {analytics['forecast_periods']}",
        "d.q1 - 1.5 *": f"d.q1 - {analytics['outliers']['iqr_multiplier']} *",
        "d.q3 + 1.5 *": f"d.q3 + {analytics['outliers']['iqr_multiplier']} *",
        "ABS(z_score) >= 3": f"ABS(z_score) >= {analytics['outliers']['z_score_threshold']}",
        "directional_z_score < -3": f"directional_z_score < -{analytics['outliers']['z_score_threshold']}",
    }
    parameter_files = [
        output / "lakehouse/notebooks/02_build_medallion.sql",
        output / "lakehouse/notebooks/03_train_learning_curves.py",
        output / "lakehouse/notebooks/04_forecast_prophet.py",
        output / "lakehouse/notebooks/05_create_serving_views.sql",
        output / "lakehouse/notebooks/06_acceptance_checks.sql",
        output / "genie/source/instructions/general.md",
    ]
    for file_path in parameter_files:
        text = file_path.read_text(encoding="utf-8")
        for old, new in parameter_replacements.items():
            text = text.replace(old, new)
        file_path.write_text(text, encoding="utf-8", newline="\n")

    feature_resource = {
        "dashboard": output / "infrastructure/databricks/resources/dashboard.yml",
        "genie": output / "infrastructure/databricks/resources/genie.yml",
        "action_intelligence": output / "infrastructure/databricks/resources/action_intelligence.yml",
    }
    for feature, resource_path in feature_resource.items():
        if not config["features"][feature] and resource_path.exists():
            resource_path.unlink()
    return output


def command_build(path: Path, output: Path | None) -> int:
    try:
        config = load_config(path)
        destination = output or DEFAULT_BUILD_ROOT / str(config.get("project", {}).get("name", "deployable"))
        build_deployable(config, destination.resolve())
    except ConfigError as exc:
        print(f"BUILD NOT CREATED\n  - {str(exc).replace(chr(10), chr(10) + '  - ')}")
        return 1
    print(f"Created deployable project: {destination.resolve()}")
    print("Next: run the repository validation commands from that directory, then deploy the bundle.")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    validate = sub.add_parser("validate", help="validate project configuration")
    validate.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    init = sub.add_parser("init", help="create a customer-mode configuration")
    init.add_argument("--output", type=Path, default=Path("config/my-project.yml"))
    init.add_argument("--force", action="store_true")
    render = sub.add_parser("render-adapter", help="render canonical Bronze adapter SQL")
    render.add_argument("--config", type=Path, required=True)
    render.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    build = sub.add_parser("build", help="create a namespace-rendered deployable repository")
    build.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    build.add_argument("--output", type=Path)
    return parser


def main() -> int:
    args = build_parser().parse_args()
    if args.command == "validate":
        return command_validate(args.config)
    if args.command == "init":
        return command_init(args.output, args.force)
    if args.command == "render-adapter":
        return command_render(args.config, args.output)
    return command_build(args.config, args.output)


if __name__ == "__main__":
    sys.exit(main())
