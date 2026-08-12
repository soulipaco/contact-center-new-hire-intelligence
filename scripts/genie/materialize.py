#!/usr/bin/env python3
from __future__ import annotations

import shutil
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "genie" / "source"
ROUTES = {
    "example_sql": (SOURCE / "instruction_library/corpus/example_sql", SOURCE / "instructions/example_sql"),
    "filters": (SOURCE / "instruction_library/corpus/filters", SOURCE / "instructions/sql_snippets/filters"),
    "measures": (SOURCE / "instruction_library/corpus/measures", SOURCE / "instructions/sql_snippets/measures"),
}

for asset_type, (source_dir, target_dir) in ROUTES.items():
    manifest_path = SOURCE / "instruction_library/activation" / f"{asset_type}.active.yml"
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    active_ids = set(manifest.get("active_ids", []))
    target_dir.mkdir(parents=True, exist_ok=True)
    for old in target_dir.glob("*.yml"):
        old.unlink()
    copied = 0
    for source in sorted(source_dir.glob("*.yml")):
        data = yaml.safe_load(source.read_text(encoding="utf-8"))
        if data.get("id") in active_ids:
            shutil.copy2(source, target_dir / source.name)
            copied += 1
    if copied != len(active_ids):
        raise RuntimeError(f"{asset_type}: activated {len(active_ids)} IDs but materialized {copied} files")
    print(f"{asset_type}: materialized {copied}")
