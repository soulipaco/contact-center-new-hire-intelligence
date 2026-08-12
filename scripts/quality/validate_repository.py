#!/usr/bin/env python3
from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.project.cli import load_config, validate_config

GENIE = ROOT / "genie"
SOURCE = GENIE / "source"
HEX_ID = re.compile(r"^[0-9a-f]{32}$")
errors = []
ids = {}

config = yaml.safe_load((GENIE / "config/room.yml").read_text(encoding="utf-8"))
sources = yaml.safe_load((SOURCE / "data_sources/tables.yml").read_text(encoding="utf-8"))

for source in sources.get("tables", []):
    if len(source.get("identifier", "").split(".")) != 3:
        errors.append(f"table identifier is not three-level: {source.get('identifier')}")
    metadata = SOURCE / source.get("column_metadata_file", "")
    if not metadata.exists():
        errors.append(f"missing metadata file: {metadata.relative_to(ROOT)}")

for path in [GENIE / "config/room.yml", *SOURCE.glob("benchmarks/*.yml"), *SOURCE.glob("instruction_library/corpus/**/*.yml")]:
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    records = data.get("sample_questions", []) if path.name == "room.yml" else [data]
    for record in records:
        value = record.get("id")
        if value is None:
            continue
        if not HEX_ID.fullmatch(value):
            errors.append(f"invalid ID in {path.relative_to(ROOT)}: {value}")
        if value in ids:
            errors.append(f"duplicate ID in {path.relative_to(ROOT)} and {ids[value]}")
        ids[value] = path.relative_to(ROOT)

required = [
    ROOT / "config/project.yml",
    ROOT / "config/project.customer.example.yml",
    ROOT / "contracts/observations.yml",
    ROOT / "contracts/agents.yml",
    ROOT / "contracts/targets.yml",
    ROOT / "contracts/training_classes.yml",
    SOURCE / "instructions/general.md",
    ROOT / "lakehouse/notebooks/01_generate_bronze.py",
    ROOT / "lakehouse/notebooks/02_build_medallion.sql",
    ROOT / "lakehouse/notebooks/03_train_learning_curves.py",
    ROOT / "lakehouse/notebooks/04_forecast_prophet.py",
    ROOT / "lakehouse/notebooks/05_create_serving_views.sql",
    ROOT / "lakehouse/notebooks/06_acceptance_checks.sql",
    ROOT / "dashboard/dashboard_brief.md",
    ROOT / "docs/quickstart.md",
    ROOT / "docs/data_contracts.md",
    ROOT / "docs/configuration.md",
    ROOT / "CONTRIBUTING.md",
    ROOT / "SECURITY.md",
]
example_root = ROOT / "examples/fictional_customer"
if example_root.exists():
    required.extend([
        example_root / "config.yml",
        example_root / "databricks.yml",
        example_root / "notebooks/00_create_source_tables.py",
    ])
for path in required:
    if not path.exists():
        errors.append(f"missing required file: {path.relative_to(ROOT)}")

for config_path in [
    ROOT / "config/project.yml",
    ROOT / "config/project.customer.example.yml",
    ROOT / "examples/fictional_customer/config.yml",
]:
    if config_path.exists():
        for error in validate_config(load_config(config_path)):
            errors.append(f"{config_path.relative_to(ROOT)}: {error}")

if errors:
    print("VALIDATION FAILED")
    for error in errors:
        print(f"  - {error}")
    sys.exit(1)

print(f"VALIDATION PASSED: {len(sources['tables'])} tables, {len(ids)} unique IDs")
