"""
generate_playbook.py — Deployment Kit Playbook Generator
=========================================================
Reads a Genie Deployment Kit and generates:
  - A domain-structured action playbook (Markdown)
  - Vector-search-ready chunks (JSON)
  - One PDF per domain (via ReportLab)

Supports two kit formats (--kit-format):
  legacy_contract  Legacy contract-based format:
                room.yml, references/*_metric_view.yaml,
                docs/contracts/*.md, snapshots/exported_space.json
  genie_kit   New deployment kit format (default):
                genie/config/room.yml, genie/source/metadata/columns/*.yml, genie/context/

Usage (from the repo root):
  python pipeline_playbook_generator/generate_playbook.py

With explicit options:
  python pipeline_playbook_generator/generate_playbook.py \\
      --kit-root . \\
      --kit-format genie_kit \\
      --config config/playbook_blueprint.yml \\
      --output-dir pipeline_playbook_generator/generated \\
      --pdf-output-dir pipeline_playbook_generator/generated/pdfs
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import textwrap
from collections import OrderedDict
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from xml.sax.saxutils import escape

import yaml


# ── Vendored dependencies (bundled with this script) ─────────────────────────
VENDOR_PATH = Path(__file__).resolve().parent / ".vendor"
if VENDOR_PATH.exists():
    vendor_str = str(VENDOR_PATH)
    if vendor_str not in sys.path:
        sys.path.insert(0, vendor_str)


# ── Contract section names (for legacy contract format) ──────────────────────
SECTION_NAMES = [
    "Likely Business Purpose",
    "Likely Grain",
    "Important Dimensions",
    "Important Measures / Metrics",
    "Likely Filter Columns",
    "Likely Time Columns",
    "Metric-View Specific Logic",
    "Candidate Genie Use Cases",
    "Contract Confidence",
]


# ─────────────────────────────────────────────────────────────────────────────
# Data classes
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class DomainProfile:
    base_name: str
    display_name: str
    question_category: str
    metric_view_identifier: str
    metric_view_description: str
    source_identifier: str
    yaml_comment: str
    dimensions: List[Dict]
    measures: List[Dict]
    contract_sections: Dict[str, List[str]]
    scenario: Dict

    @property
    def key_measures(self) -> List[str]:
        contract_measures = extract_contract_terms(self.contract_sections.get("Important Measures / Metrics", []))
        if contract_measures:
            return contract_measures
        names = [m["name"] for m in self.measures if m.get("name", "").lower() != "count"]
        return names[:8]

    @property
    def key_dimensions(self) -> List[str]:
        contract_dims = extract_contract_terms(self.contract_sections.get("Important Dimensions", []))
        if contract_dims:
            return contract_dims
        return [d["name"] for d in self.dimensions[:8]]

    @property
    def filter_columns(self) -> List[str]:
        items = extract_contract_terms(self.contract_sections.get("Likely Filter Columns", []))
        if items:
            return items
        return self.key_dimensions[:8]

    @property
    def time_columns(self) -> List[str]:
        return extract_contract_terms(self.contract_sections.get("Likely Time Columns", []), limit=6)

    @property
    def metric_logic(self) -> List[str]:
        return self.contract_sections.get("Metric-View Specific Logic", [])[:6]

    @property
    def use_cases(self) -> List[str]:
        return self.contract_sections.get("Candidate Genie Use Cases", [])[:6]

    @property
    def grain_summary(self) -> str:
        grain_lines = self.contract_sections.get("Likely Grain", [])
        return " ".join(grain_lines) if grain_lines else "Grain not extracted."


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def build_cli() -> argparse.ArgumentParser:
    repo_root = Path(__file__).resolve().parents[2]
    parser = argparse.ArgumentParser(
        description="Generate a room action playbook from a deployment kit.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "--kit-root",
        type=Path,
        default=repo_root,
        help="Path to the deployment kit root (default: parent of this script).",
    )
    parser.add_argument(
        "--kit-format",
        choices=["genie_kit", "legacy_contract"],
        default="genie_kit",
        help=(
            "Kit format to read. "
            "'genie_kit' reads genie/config + genie/source/metadata + genie/context. "
            "'legacy_contract' reads room.yml + references/ + docs/contracts/. "
            "(default: genie_kit)"
        ),
    )
    parser.add_argument(
        "--config",
        type=str,
        default="config/playbook_blueprint.yml",
        help="Path to the playbook blueprint YAML (absolute or relative to this script's directory).",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path(__file__).resolve().parent / "generated",
        help="Directory where generated artifacts will be written.",
    )
    parser.add_argument(
        "--pdf-output-dir",
        type=str,
        default="pdfs",
        help=(
            "Where to save generated PDFs. "
            "Relative values are resolved inside --output-dir. "
            "Absolute paths are used as-is. "
            "(default: pdfs → {output_dir}/pdfs/)"
        ),
    )
    return parser


# ─────────────────────────────────────────────────────────────────────────────
# Shared utilities
# ─────────────────────────────────────────────────────────────────────────────

def load_yaml(path: Path) -> Dict:
    with path.open("r", encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def normalize_item(item) -> str:
    if isinstance(item, dict):
        return normalize_text("; ".join(f"{key}: {value}" for key, value in item.items()))
    return normalize_text(str(item))


def extract_contract_terms(items: List[str], limit: int = 8) -> List[str]:
    terms: List[str] = []
    for raw_item in items:
        item = normalize_item(raw_item)
        if not item or item.endswith(":"):
            continue
        candidates = re.findall(r"`([^`]+)`", item) or [item]
        for candidate in candidates:
            candidate = normalize_text(candidate)
            if candidate and candidate not in terms:
                terms.append(candidate)
        if len(terms) >= limit:
            break
    return terms[:limit]


def bullets(items: List[str], prefix: str = "- ") -> str:
    return "\n".join(f"{prefix}{item}" for item in items)


def format_list_inline(items: List[str]) -> str:
    return ", ".join(f"`{item}`" for item in items) if items else "None extracted"


def slug_to_contract_name(base_name: str) -> str:
    return f"{base_name}.md"


# ─────────────────────────────────────────────────────────────────────────────
# Legacy contract format (preserved for backward compatibility)
# ─────────────────────────────────────────────────────────────────────────────

def parse_contract_sections(text: str) -> Dict[str, List[str]]:
    sections: Dict[str, List[str]] = OrderedDict()
    current = None
    for raw_line in text.splitlines():
        line = raw_line.rstrip()
        if line.startswith("## "):
            current = line[3:].strip()
            sections[current] = []
            continue
        if current is None:
            continue
        stripped = line.strip()
        if not stripped:
            continue
        if stripped.startswith("- "):
            sections[current].append(stripped[2:].strip())
        elif stripped.startswith("  - "):
            sections[current].append(stripped[4:].strip())
        elif current in SECTION_NAMES and not stripped.startswith("### "):
            sections[current].append(stripped)
    return sections


def load_snapshot(kit_root: Path) -> Dict[str, Dict[str, str]]:
    snapshot_path = kit_root / "snapshots" / "exported_space.json"
    if not snapshot_path.exists():
        return {}
    snapshot_raw = json.loads(snapshot_path.read_text(encoding="utf-8"))
    serialized_space = json.loads(snapshot_raw["serialized_space"])
    by_base_name: Dict[str, Dict[str, str]] = {}
    for metric_view in serialized_space.get("data_sources", {}).get("metric_views", []):
        identifier = metric_view["identifier"]
        base_name = identifier.replace("_metric_view", "").split(".")[-1]
        description = " ".join(metric_view.get("description", []))
        by_base_name[base_name] = {
            "identifier": identifier,
            "description": normalize_text(description),
        }
    return by_base_name


def build_domain_profiles_legacy_contract(kit_root: Path, blueprint: Dict) -> Tuple[List[DomainProfile], Dict]:
    """Build domain profiles from the legacy contract-based kit format."""
    room = load_yaml(kit_root / "room.yml")
    snapshot = load_snapshot(kit_root)
    profiles: List[DomainProfile] = []

    for base_name, scenario in blueprint["domains"].items():
        yaml_path = kit_root / "references" / f"{base_name}_metric_view.yaml"
        contract_path = kit_root / "docs" / "contracts" / slug_to_contract_name(base_name)

        yaml_doc = load_yaml(yaml_path)
        contract_sections = parse_contract_sections(contract_path.read_text(encoding="utf-8"))
        snapshot_info = snapshot.get(base_name, {})

        profiles.append(DomainProfile(
            base_name=base_name,
            display_name=scenario["display_name"],
            question_category=scenario["question_category"],
            metric_view_identifier=snapshot_info.get("identifier", f"{base_name}_metric_view"),
            metric_view_description=snapshot_info.get("description", ""),
            source_identifier=yaml_doc.get("source", ""),
            yaml_comment=normalize_text(yaml_doc.get("comment", "")),
            dimensions=yaml_doc.get("dimensions", []),
            measures=yaml_doc.get("measures", []),
            contract_sections=contract_sections,
            scenario=scenario,
        ))

    return profiles, room


# ─────────────────────────────────────────────────────────────────────────────
# genie_kit format adapted to the repository's modular Genie layout
# ─────────────────────────────────────────────────────────────────────────────

def load_room_genie_kit(kit_root: Path) -> Dict:
    """Load room identity from the repository's Genie module."""
    config_path = kit_root / "genie" / "config" / "room.yml"
    if not config_path.exists():
        raise FileNotFoundError(
            f"Genie room config not found at {config_path}.\n"
            "Ensure --kit-root points to this portfolio repository."
        )
    return load_yaml(config_path)


def parse_column_metadata_sections(
    path: Path,
) -> Tuple[List[str], List[str], List[str], List[str], str]:
    """
    Parse a metadata/columns/*.yml file into (dimensions, measures, filter_cols, time_cols, source).

    The YAML comment convention MUST be present:
        # ── Dimensions ──  (or any line containing "Dimensions" starting with #)
        # ── Measures ──    (or any line containing "Measures" starting with #)

    Columns appearing before the Dimensions comment are skipped.
    Columns appearing between Dimensions and Measures comments are dimensions.
    Columns appearing after the Measures comment are measures.
    Excluded columns (exclude: true) are not included in either list.
    """
    raw_text = path.read_text(encoding="utf-8")
    data = load_yaml(path)

    source_identifier = data.get("table", "")
    all_columns: List[Dict] = data.get("columns", [])
    col_map = {c.get("column_name", ""): c for c in all_columns}

    # Parse section assignment from raw text comments
    dimensions_raw: List[str] = []
    measures_raw: List[str] = []
    current_section: Optional[str] = None

    for line in raw_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("#") and "dimensions" in stripped.lower():
            current_section = "dimensions"
            continue
        if stripped.startswith("#") and "measures" in stripped.lower():
            current_section = "measures"
            continue
        if "column_name:" in stripped and not stripped.startswith("#"):
            col_name = stripped.split("column_name:", 1)[1].strip()
            col_meta = col_map.get(col_name, {})
            if col_meta.get("exclude") is True:
                continue
            if current_section == "dimensions":
                dimensions_raw.append(col_name)
            elif current_section == "measures":
                measures_raw.append(col_name)

    if not dimensions_raw and not measures_raw:
        print(
            f"WARNING: {path.name} lacks '# ── Dimensions' / '# ── Measures' comment markers.\n"
            "         All non-excluded columns will be listed as unclassified dimensions.\n"
            "         Add comment markers to enable proper classification."
        )
        dimensions_raw = [
            c.get("column_name", "") for c in all_columns
            if not c.get("exclude") and c.get("column_name")
        ]

    # Filter columns: dimensions where enable_entity_matching is set
    filter_cols = [
        name for name in dimensions_raw
        if col_map.get(name, {}).get("enable_entity_matching") is True
    ]

    # Time columns: columns with "date" or "time" in the name (not excluded)
    time_cols = [
        name for name in dimensions_raw + measures_raw
        if ("date" in name.lower() or "time" in name.lower() or name == "date")
        and not col_map.get(name, {}).get("exclude")
    ]

    return dimensions_raw, measures_raw, filter_cols, time_cols, source_identifier


def load_geniecode_context(kit_root: Path) -> Dict[str, str]:
    """Read geniecode/ knowledge files. Missing files are silently skipped."""
    geniecode_dir = kit_root / "genie" / "context"
    context: Dict[str, str] = {}
    for fname in ["KNOWLEDGE_BASE.md", "DOMAIN_RULES.md", "TABLE_SCHEMAS.md"]:
        fpath = geniecode_dir / fname
        if fpath.exists():
            context[fname] = fpath.read_text(encoding="utf-8")
    return context


def extract_metric_logic_from_geniecode(context: Dict[str, str]) -> List[str]:
    """Extract concise rule summaries from DOMAIN_RULES.md (## Rule N: Title lines)."""
    dr_text = context.get("DOMAIN_RULES.md", "")
    rules: List[str] = []
    for line in dr_text.splitlines():
        stripped = line.strip()
        if stripped.startswith("## Rule "):
            parts = stripped.split(":", 1)
            if len(parts) > 1:
                rules.append(parts[1].strip())
            elif len(stripped) > 8:
                rules.append(stripped[3:].strip())
    return rules[:6]


def extract_use_cases_from_geniecode(context: Dict[str, str]) -> List[str]:
    """Extract candidate use cases from the Query Decision Heuristic table in KNOWLEDGE_BASE.md."""
    kb_text = context.get("KNOWLEDGE_BASE.md", "")
    use_cases: List[str] = []
    in_heuristic = False
    for line in kb_text.splitlines():
        stripped = line.strip()
        if "Query Decision Heuristic" in stripped and stripped.startswith("##"):
            in_heuristic = True
            continue
        if in_heuristic and stripped.startswith("##"):
            break
        if in_heuristic and stripped.startswith("|") and "---" not in stripped:
            parts = [p.strip() for p in stripped.split("|") if p.strip()]
            if parts and "Question intent" not in parts[0]:
                # Strip surrounding quotes if present
                use_cases.append(parts[0].strip('"\''))
    return use_cases[:6]


def extract_grain_from_geniecode(context: Dict[str, str]) -> str:
    """Extract grain info from KNOWLEDGE_BASE.md Source Table section."""
    kb_text = context.get("KNOWLEDGE_BASE.md", "")
    in_source = False
    for line in kb_text.splitlines():
        stripped = line.strip()
        if "Source Table" in stripped and stripped.startswith("##"):
            in_source = True
            continue
        if in_source and stripped.startswith("##"):
            break
        if in_source and stripped.startswith("|") and "---" not in stripped:
            parts = [p.strip() for p in stripped.split("|") if p.strip()]
            if parts and "Table" not in parts[0]:
                # Return the Date Col cell if available
                if len(parts) >= 3:
                    return f"date column: {parts[2]}"
                return parts[-1]
    return "See KNOWLEDGE_BASE.md Source Table section."


def build_domain_profiles_genie_kit(
    kit_root: Path, blueprint: Dict
) -> Tuple[List[DomainProfile], Dict]:
    """Build domain profiles from the genie_kit deployment kit format."""
    room = load_room_genie_kit(kit_root)
    geniecode_ctx = load_geniecode_context(kit_root)
    profiles: List[DomainProfile] = []

    columns_dir = kit_root / "genie" / "source" / "metadata" / "columns"
    if not columns_dir.exists():
        raise FileNotFoundError(
            f"metadata/columns/ directory not found at {columns_dir}.\n"
            "This directory is required for the genie_kit format."
        )

    col_files = [f for f in columns_dir.glob("*.yml") if f.stem != "README"]
    if not col_files:
        raise FileNotFoundError(
            f"No column metadata files (*.yml) found in {columns_dir}.\n"
            "Create at least one file: metadata/columns/<table_name>.yml"
        )

    metric_logic = extract_metric_logic_from_geniecode(geniecode_ctx)
    use_cases = extract_use_cases_from_geniecode(geniecode_ctx)
    grain = extract_grain_from_geniecode(geniecode_ctx)

    # Room description for business purpose
    raw_desc = room.get("description", "") or ""
    room_description = normalize_text(raw_desc)[:300]

    snapshot = load_snapshot(kit_root)  # optional — empty dict if absent

    for base_name, scenario in blueprint["domains"].items():
        # Match column metadata file by name similarity
        matching_file = _find_column_file(base_name, col_files)
        if matching_file is None:
            if len(col_files) == 1:
                matching_file = col_files[0]
                print(
                    f"INFO: Single column file {col_files[0].name} assumed for domain '{base_name}'."
                )
            else:
                raise FileNotFoundError(
                    f"Cannot find column metadata file for domain '{base_name}'.\n"
                    f"Files found: {[f.name for f in col_files]}\n"
                    "The domain key in the blueprint must partially match a metadata filename.\n"
                    "Rename the domain key or rename the metadata file to establish the match."
                )

        dimensions, measures, filter_cols, time_cols, source_identifier = \
            parse_column_metadata_sections(matching_file)

        metric_view_identifier = (
            snapshot.get(base_name, {}).get("identifier")
            or source_identifier
            or f"{base_name}_metric_view"
        )
        metric_view_description = snapshot.get(base_name, {}).get("description", "")

        contract_sections: Dict[str, List[str]] = {
            "Likely Business Purpose": [room_description] if room_description else [],
            "Likely Grain": [grain],
            "Important Dimensions": [f"`{d}`" for d in dimensions[:12]],
            "Important Measures / Metrics": [f"`{m}`" for m in measures[:12]],
            "Likely Filter Columns": [f"`{f}`" for f in filter_cols[:8]],
            "Likely Time Columns": [f"`{t}`" for t in time_cols[:4]],
            "Metric-View Specific Logic": metric_logic,
            "Candidate Genie Use Cases": use_cases,
        }

        profiles.append(DomainProfile(
            base_name=base_name,
            display_name=scenario["display_name"],
            question_category=scenario["question_category"],
            metric_view_identifier=metric_view_identifier,
            metric_view_description=metric_view_description,
            source_identifier=source_identifier,
            yaml_comment=room_description[:100],
            dimensions=[{"name": d} for d in dimensions],
            measures=[{"name": m} for m in measures],
            contract_sections=contract_sections,
            scenario=scenario,
        ))

    return profiles, room


def _find_column_file(base_name: str, col_files: List[Path]) -> Optional[Path]:
    """Find the column metadata file that best matches a domain base_name."""
    base_lower = base_name.lower()
    # Exact stem match
    for f in col_files:
        if f.stem.lower() == base_lower:
            return f
    # Partial match: base_name contained in filename or vice-versa
    for f in col_files:
        stem_lower = f.stem.lower()
        if base_lower in stem_lower or stem_lower in base_lower:
            return f
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Playbook content builders (shared between both formats)
# ─────────────────────────────────────────────────────────────────────────────

def build_domain_playbook_spec(profile: DomainProfile) -> Dict:
    scenario = profile.scenario
    kpis_covered = scenario.get("kpis_covered") or [
        {"name": name, "description": ""} for name in profile.key_measures
    ]
    interpretation_rules = scenario.get("interpretation_rules") or []
    scenarios = scenario.get("scenarios") or [
        {
            "letter": "A",
            "title": scenario.get("scenario_title", "KPI Deterioration"),
            "symptoms": [
                scenario.get("scenario_trigger", "KPI trend degradation detected."),
                f"Primary KPI focus includes {', '.join(profile.key_measures[:5])}.",
            ],
            "likely_causes": scenario.get("likely_causes", []),
            "action_plan_recommendations": [
                {"heading": "Immediate actions (today-48h)", "actions": scenario.get("immediate_actions", [])},
                {"heading": "Short-term actions (1-4 weeks)", "actions": scenario.get("short_term_actions", [])},
            ],
            "measurement_targets": scenario.get("targets", []),
        }
    ]
    action_cards = scenario.get("action_cards") or [
        {
            "title": scenario.get("action_card_title", "Fast Containment"),
            "trigger": scenario.get("action_card_trigger", "KPI threshold breached."),
            "actions": scenario.get("action_card_actions", []),
            "expected_impact": "improved KPI stability after targeted intervention",
        }
    ]
    example_plans = scenario.get("example_plans") or []
    playbook_note = scenario.get(
        "playbook_note",
        f"Generated from the deployment kit using the {profile.display_name} metadata and geniecode context.",
    )
    return {
        "playbook_title": scenario.get("playbook_title", f"{profile.display_name} Operations Playbook"),
        "playbook_subtitle": scenario.get(
            "playbook_subtitle", "Action Plan Recommendations for KPI-Driven Trend Analysis"
        ),
        "playbook_note": playbook_note,
        "intro_text": scenario.get(
            "intro_text",
            "This playbook is organized around common operational patterns and designed for vector-search retrieval.",
        ),
        "kpis_covered": kpis_covered,
        "interpretation_rules": interpretation_rules,
        "scenarios": scenarios,
        "action_cards": action_cards,
        "example_plans": example_plans,
    }


def build_domain_markdown(blueprint: Dict, room: Dict, profile: DomainProfile) -> str:
    spec = build_domain_playbook_spec(profile)
    room_title = room.get("title") or room.get("room_name") or "Genie Room"
    parts: List[str] = []
    parts.append(f"# {spec['playbook_title']}")
    parts.append("")
    parts.append(f"## {spec['playbook_subtitle']}")
    parts.append("")
    parts.append(f"*({spec['playbook_note']})*")
    parts.append("")
    parts.append("---")
    parts.append("")
    parts.append("## 1) KPI Reference and How to Interpret Shifts")
    parts.append("")
    parts.append(spec["intro_text"])
    parts.append("")
    parts.append("**KPIs covered**")
    parts.append("")
    for item in spec["kpis_covered"]:
        parts.append(f"- {item['name']} : {item.get('description', '')}")
    parts.append("")
    parts.append("**General interpretation rules**")
    parts.append("")
    for rule in spec["interpretation_rules"]:
        parts.append(f"- {rule}")
    parts.append(f"- Grain context: {profile.grain_summary}.")
    parts.append(f"- Common filters include {', '.join(profile.filter_columns)}.")
    for rule in profile.metric_logic:
        parts.append(f"- {rule}")
    parts.append("")
    parts.append("## 2) Scenario Playbooks (Symptoms -> Likely Causes -> Action Plans)")
    parts.append("")
    for scenario in spec["scenarios"]:
        parts.append(f"### Scenario {scenario['letter']} - {scenario['title']}")
        parts.append("")
        parts.append("**Symptoms**")
        parts.append("")
        for symptom in scenario["symptoms"]:
            parts.append(f"- {symptom}")
        parts.append("")
        parts.append("**Likely causes**")
        parts.append("")
        for cause in scenario["likely_causes"]:
            parts.append(f"- {cause}")
        parts.append("")
        parts.append("**Action plan recommendations**")
        parts.append("")
        for idx, section in enumerate(scenario["action_plan_recommendations"], 1):
            parts.append(f"{idx}. {section['heading']}")
            for action in section["actions"]:
                parts.append(f"   - {action}")
            parts.append("")
        parts.append("**Measurement targets**")
        parts.append("")
        for target in scenario["measurement_targets"]:
            parts.append(f"- {target}")
        parts.append("")
    parts.append("## 3) Recommendation Templates (Vector-Friendly Snippets)")
    parts.append("")
    parts.append("These are short, reusable action cards designed for embedding and retrieval.")
    parts.append("")
    for action_card in spec["action_cards"]:
        parts.append(f"### Action Card: {action_card['title']}")
        parts.append("")
        parts.append(f"Trigger: {action_card['trigger']}")
        parts.append("")
        parts.append("**Actions:**")
        parts.append("")
        for action in action_card["actions"]:
            parts.append(f"- {action}")
        parts.append("")
        parts.append(f"Expected impact: {action_card['expected_impact']}")
        parts.append("")
    parts.append('## 4) Putting It Together: Example "Recommended Plan" Outputs')
    parts.append("")
    for example in spec["example_plans"]:
        parts.append(f"### Example Plan {example['number']} ({example['title']})")
        parts.append("")
        parts.append(f"Observed trend: {example['observed_trend']}")
        parts.append("")
        parts.append("**Plan:**")
        parts.append("")
        for action in example["plan"]:
            parts.append(f"- {action}")
        parts.append("")
        parts.append(f"Success metrics: {example['success_metrics']}")
        parts.append("")
    return "\n".join(parts).strip() + "\n"


def build_markdown(blueprint: Dict, room: Dict, profiles: List[DomainProfile]) -> str:
    title = blueprint["playbook"]["title"]
    source_name = blueprint["playbook"]["source_name"]
    description = normalize_text(blueprint["playbook"]["description"])
    room_title = room.get("title") or room.get("room_name") or "Genie Room"

    parts: List[str] = []
    parts.append(f"# {title}")
    parts.append("")
    parts.append("Generated draft playbook for retrieval-augmented action planning.")
    parts.append("")
    parts.append(f"- Source room: `{room_title}`")
    parts.append(f"- Generated from: `{source_name}`")
    parts.append(f"- Purpose: {description}")
    parts.append("- Important: This is a generated draft and should be SME-reviewed before production use.")
    parts.append("")
    parts.append("## 1) Room Source Reference and Interpretation Rules")
    parts.append("")
    for profile in profiles:
        parts.append(f"### {profile.display_name}")
        parts.append("")
        parts.append(f"- Question category: `{profile.question_category}`")
        parts.append(f"- Metric view: `{profile.metric_view_identifier}`")
        parts.append(f"- Underlying source: `{profile.source_identifier}`")
        if profile.metric_view_description:
            parts.append(f"- Description: {profile.metric_view_description}")
        parts.append(f"- Grain: {profile.grain_summary}")
        parts.append(f"- Core measures: {format_list_inline(profile.key_measures)}")
        parts.append(f"- Core dimensions: {format_list_inline(profile.key_dimensions)}")
        parts.append(f"- Likely filters: {format_list_inline(profile.filter_columns)}")
        if profile.time_columns:
            parts.append(f"- Time columns: {format_list_inline(profile.time_columns)}")
        if profile.metric_logic:
            parts.append("- Metric-view specific logic:")
            parts.append(bullets(profile.metric_logic))
        if profile.use_cases:
            parts.append("- Good retrieval/use-case anchors:")
            parts.append(bullets(profile.use_cases))
        parts.append("")
    parts.append("## 2) Domain Scenario Playbooks")
    parts.append("")
    for profile in profiles:
        scenario = profile.scenario
        parts.append(f"### {scenario.get('scenario_title', profile.display_name)}")
        parts.append("")
        parts.append(f"**Domain:** {profile.display_name}")
        parts.append("")
        trigger = scenario.get("scenario_trigger", "")
        if trigger:
            parts.append("**Trigger**")
            parts.append(trigger)
            parts.append("")
        parts.append("**Symptoms and analytical cues**")
        cue_lines = [
            f"Look first at {format_list_inline(profile.key_measures[:5])}.",
            f"Cut by {format_list_inline(profile.filter_columns[:5])}.",
        ]
        if profile.time_columns:
            cue_lines.append(f"Trend on {format_list_inline(profile.time_columns[:3])}.")
        parts.append(bullets(cue_lines))
        parts.append("")
        likely_causes = scenario.get("likely_causes", [])
        if likely_causes:
            parts.append("**Likely causes**")
            parts.append(bullets(likely_causes))
            parts.append("")
        immediate = scenario.get("immediate_actions", [])
        if immediate:
            parts.append("**Immediate actions (24-48h)**")
            parts.append(bullets(immediate))
            parts.append("")
        short_term = scenario.get("short_term_actions", [])
        if short_term:
            parts.append("**Short-term actions (1-4 weeks)**")
            parts.append(bullets(short_term))
            parts.append("")
        targets = scenario.get("targets", [])
        if targets:
            parts.append("**Measurement targets**")
            parts.append(bullets(targets))
            parts.append("")
    parts.append("## 3) Recommendation Templates")
    parts.append("")
    parts.append("These vector-friendly action cards are intended to be retrieved directly by the action-plan pipeline.")
    parts.append("")
    for profile in profiles:
        scenario = profile.scenario
        action_card_title = scenario.get("action_card_title", f"{profile.display_name} Fast Containment")
        action_card_trigger = scenario.get("action_card_trigger", "")
        action_card_actions = scenario.get("action_card_actions", [])
        parts.append(f"### Action Card: {action_card_title}")
        parts.append("")
        parts.append(f"- Category: `{profile.question_category}`")
        if action_card_trigger:
            parts.append(f"- Trigger: {action_card_trigger}")
        if action_card_actions:
            parts.append("- Actions:")
            parts.append(bullets(action_card_actions))
        parts.append("")
    parts.append("## 4) Putting It Together: Example Recommended Plans")
    parts.append("")
    for example in blueprint.get("example_plans", []):
        parts.append(f"### Example Plan: {example['title']}")
        parts.append("")
        parts.append(f"- Category: `{example['question_category']}`")
        parts.append(f"- Observed trend: {example['observed_trend']}")
        parts.append("- Plan:")
        parts.append(bullets(example["plan"]))
        parts.append("- Success metrics:")
        parts.append(bullets(example["success_metrics"]))
        parts.append("")

    return "\n".join(parts).strip() + "\n"


def append_chunk(
    chunks: List[Dict], title: str, body_lines: List[str], question_category: str, source: str
) -> None:
    text = "\n".join(body_lines).strip()
    chunks.append({
        "chunk_id": len(chunks) + 1,
        "title": title,
        "text": f"[Section: {title}]\n\n{text}",
        "source": source,
        "question_category": question_category,
    })


def build_domain_chunks(room: Dict, profile: DomainProfile, source_name: str) -> List[Dict]:
    spec = build_domain_playbook_spec(profile)
    chunks: List[Dict] = []

    append_chunk(
        chunks,
        "KPI Reference and How to Interpret Shifts",
        [
            spec["intro_text"],
            "KPIs covered:",
            *[f"- {item['name']}: {item.get('description', '')}" for item in spec["kpis_covered"]],
            "General interpretation rules:",
            *[f"- {item}" for item in spec["interpretation_rules"]],
            f"- Grain context: {profile.grain_summary}",
            f"Metric view: {profile.metric_view_identifier}",
            f"Underlying source: {profile.source_identifier}",
            f"Primary filters: {', '.join(profile.filter_columns)}",
            *[f"- {item}" for item in profile.metric_logic],
        ],
        profile.question_category,
        source_name,
    )

    for scenario in spec["scenarios"]:
        body_lines = [
            "Symptoms:",
            *[f"- {item}" for item in scenario["symptoms"]],
            "Likely causes:",
            *[f"- {item}" for item in scenario["likely_causes"]],
            "Action plan recommendations:",
        ]
        for idx, section in enumerate(scenario["action_plan_recommendations"], 1):
            body_lines.append(f"{idx}. {section['heading']}")
            body_lines.extend([f"- {item}" for item in section["actions"]])
        body_lines.extend([
            "Measurement targets:",
            *[f"- {item}" for item in scenario["measurement_targets"]],
        ])
        append_chunk(
            chunks,
            f"Scenario {scenario['letter']} - {scenario['title']}",
            body_lines,
            profile.question_category,
            source_name,
        )

    for action_card in spec["action_cards"]:
        append_chunk(
            chunks,
            f"Action Card: {action_card['title']}",
            [
                f"Trigger: {action_card['trigger']}",
                "Actions:",
                *[f"- {item}" for item in action_card["actions"]],
                f"Expected impact: {action_card['expected_impact']}",
            ],
            profile.question_category,
            source_name,
        )

    for example in spec["example_plans"]:
        append_chunk(
            chunks,
            f"Example Plan {example['number']} - {example['title']}",
            [
                f"Observed trend: {example['observed_trend']}",
                "Plan:",
                *[f"- {item}" for item in example["plan"]],
                f"Success metrics: {example['success_metrics']}",
            ],
            profile.question_category,
            source_name,
        )

    return chunks


def build_chunks(blueprint: Dict, room: Dict, profiles: List[DomainProfile]) -> List[Dict]:
    room_title = room.get("title") or room.get("room_name") or "room"
    source = f"{room_title}_action_playbook.md"
    chunks: List[Dict] = []

    append_chunk(
        chunks,
        "Playbook Overview",
        [
            f"Room title: {room_title}",
            f"Generated from: {blueprint['playbook']['source_name']}",
            normalize_text(blueprint["playbook"]["description"]),
        ],
        "cross_source_playbook",
        source,
    )

    for profile in profiles:
        domain_chunks = build_domain_chunks(room, profile, source)
        chunks.extend(domain_chunks)

    # Re-assign globally unique chunk IDs
    for i, chunk in enumerate(chunks, start=1):
        chunk["chunk_id"] = i

    return chunks


# ─────────────────────────────────────────────────────────────────────────────
# PDF rendering
# ─────────────────────────────────────────────────────────────────────────────

def _build_bullet_block(items: List[str], bullet_char: str = "-", width: int = 78) -> str:
    rendered: List[str] = []
    for item in items:
        wrapped = textwrap.wrap(item, width=width) or [item]
        rendered.append(f"{bullet_char}&nbsp;&nbsp;{escape(wrapped[0])}")
        for continuation in wrapped[1:]:
            rendered.append(f"&nbsp;&nbsp;&nbsp;&nbsp;&nbsp;{escape(continuation)}")
        rendered.append("")
    return "<br/>".join(rendered[:-1]) if rendered else ""


def render_domain_pdf(room: Dict, profile: DomainProfile, pdf_path: Path) -> None:
    import hashlib
    original_md5 = hashlib.md5

    def compat_md5(*args, **kwargs):
        kwargs.pop("usedforsecurity", None)
        return original_md5(*args, **kwargs)

    hashlib.md5 = compat_md5

    from reportlab.lib import colors
    from reportlab.lib.enums import TA_LEFT
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
    from reportlab.lib.units import mm
    from reportlab.platypus import HRFlowable, PageBreak, Paragraph, SimpleDocTemplate, Spacer

    spec = build_domain_playbook_spec(profile)
    styles = getSampleStyleSheet()

    for style_name, parent_name, kwargs in [
        ("PlaybookTitle",    "Title",    {"fontName": "Helvetica-Bold", "fontSize": 26, "leading": 30, "spaceAfter": 14, "alignment": TA_LEFT}),
        ("PlaybookSubtitle", "Heading1", {"fontName": "Helvetica-Bold", "fontSize": 19, "leading": 24, "spaceAfter": 18, "alignment": TA_LEFT}),
        ("PlaybookNote",     "Italic",   {"fontName": "Helvetica-Oblique", "fontSize": 13, "leading": 18, "spaceAfter": 18}),
        ("SectionHeading",   "Heading1", {"fontName": "Helvetica-Bold", "fontSize": 18, "leading": 22, "spaceBefore": 8, "spaceAfter": 12, "keepWithNext": True}),
        ("SubHeading",       "Heading2", {"fontName": "Helvetica-Bold", "fontSize": 13.5, "leading": 18, "spaceBefore": 6, "spaceAfter": 6, "keepWithNext": True}),
        ("ScenarioHeading",  "Heading2", {"fontName": "Helvetica-Bold", "fontSize": 14, "leading": 18, "spaceBefore": 8, "spaceAfter": 8, "keepWithNext": True}),
        ("Body",             "BodyText", {"fontName": "Helvetica", "fontSize": 12.5, "leading": 17, "spaceAfter": 8}),
        ("NumberHeading",    "BodyText", {"fontName": "Helvetica-Bold", "fontSize": 12.5, "leading": 17, "leftIndent": 0, "spaceBefore": 4, "spaceAfter": 4, "keepWithNext": True}),
        ("SubAction",        "BodyText", {"fontName": "Helvetica", "fontSize": 12.5, "leading": 17, "leftIndent": 24, "spaceAfter": 0}),
    ]:
        styles.add(ParagraphStyle(name=style_name, parent=styles[parent_name], **kwargs))

    from reportlab.lib.pagesizes import A4
    doc = SimpleDocTemplate(
        str(pdf_path), pagesize=A4,
        leftMargin=20 * mm, rightMargin=20 * mm, topMargin=18 * mm, bottomMargin=18 * mm,
    )

    def draw_footer(canvas, document):
        canvas.saveState()
        canvas.setStrokeColor(colors.HexColor("#D6DCE4"))
        canvas.line(document.leftMargin, 11 * mm, A4[0] - document.rightMargin, 11 * mm)
        canvas.setFillColor(colors.HexColor("#52606D"))
        canvas.setFont("Helvetica", 8)
        canvas.drawString(document.leftMargin, 7 * mm, "Contact Center New-Hire Intelligence | Synthetic data")
        canvas.drawRightString(A4[0] - document.rightMargin, 7 * mm, f"Page {document.page}")
        canvas.restoreState()

    story = []
    story.append(Paragraph(escape(spec["playbook_title"]), styles["PlaybookTitle"]))
    story.append(Paragraph(escape(spec["playbook_subtitle"]), styles["PlaybookSubtitle"]))
    story.append(Paragraph(escape(f"({spec['playbook_note']})"), styles["PlaybookNote"]))
    story.append(HRFlowable(width="100%", thickness=1, color=colors.HexColor("#888888")))
    story.append(Spacer(1, 16))

    story.append(Paragraph("1) KPI Reference and How to Interpret Shifts", styles["SectionHeading"]))
    story.append(Paragraph(escape(spec["intro_text"]), styles["Body"]))
    story.append(Spacer(1, 4))
    story.append(Paragraph("KPIs covered", styles["SubHeading"]))
    story.append(Paragraph(
        _build_bullet_block([f"{item['name']}: {item.get('description', '')}" for item in spec["kpis_covered"]]),
        styles["Body"],
    ))
    story.append(Spacer(1, 6))
    story.append(Paragraph("General interpretation rules", styles["SubHeading"]))
    story.append(Paragraph(
        _build_bullet_block(
            spec["interpretation_rules"]
            + [f"Grain context: {profile.grain_summary}.", f"Common filters include {', '.join(profile.filter_columns)}."]
            + profile.metric_logic
        ),
        styles["Body"],
    ))
    story.append(Spacer(1, 12))

    story.append(PageBreak())
    story.append(Paragraph("2) Scenario Playbooks (Symptoms to Likely Causes to Action Plans)", styles["SectionHeading"]))
    for scenario in spec["scenarios"]:
        story.append(Paragraph(f"Scenario {scenario['letter']} - {escape(scenario['title'])}", styles["ScenarioHeading"]))
        story.append(Paragraph("Symptoms", styles["SubHeading"]))
        story.append(Paragraph(_build_bullet_block(scenario["symptoms"]), styles["Body"]))
        story.append(Spacer(1, 6))
        story.append(Paragraph("Likely causes", styles["SubHeading"]))
        story.append(Paragraph(_build_bullet_block(scenario["likely_causes"]), styles["Body"]))
        story.append(Spacer(1, 6))
        story.append(Paragraph("Action plan recommendations", styles["SubHeading"]))
        for idx, section in enumerate(scenario["action_plan_recommendations"], 1):
            story.append(Paragraph(f"{idx}. {escape(section['heading'])}", styles["NumberHeading"]))
            story.append(Paragraph(_build_bullet_block(section["actions"], bullet_char="-", width=74), styles["SubAction"]))
            story.append(Spacer(1, 4))
        story.append(Paragraph("Measurement targets", styles["SubHeading"]))
        story.append(Paragraph(_build_bullet_block(scenario["measurement_targets"]), styles["Body"]))
        story.append(Spacer(1, 10))

    story.append(PageBreak())
    story.append(Paragraph("3) Recommendation Templates (Vector-Friendly Snippets)", styles["SectionHeading"]))
    story.append(Paragraph("These are short, reusable action cards designed for embedding and retrieval.", styles["Body"]))
    for action_card in spec["action_cards"]:
        story.append(Paragraph(f"Action Card: {escape(action_card['title'])}", styles["ScenarioHeading"]))
        story.append(Paragraph(f"Trigger: {escape(action_card['trigger'])}", styles["Body"]))
        story.append(Paragraph("Actions:", styles["SubHeading"]))
        story.append(Paragraph(_build_bullet_block(action_card["actions"]), styles["Body"]))
        story.append(Spacer(1, 6))
        story.append(Paragraph(f"Expected impact: {escape(action_card['expected_impact'])}", styles["Body"]))
        story.append(Spacer(1, 8))

    story.append(PageBreak())
    story.append(Paragraph('4) Putting It Together: Example "Recommended Plan" Outputs', styles["SectionHeading"]))
    for example in spec["example_plans"]:
        story.append(Paragraph(f"Example Plan {example['number']} ({escape(example['title'])})", styles["ScenarioHeading"]))
        story.append(Paragraph(f"Observed trend: {escape(example['observed_trend'])}", styles["Body"]))
        story.append(Paragraph("Plan:", styles["SubHeading"]))
        story.append(Paragraph(_build_bullet_block(example["plan"]), styles["Body"]))
        story.append(Spacer(1, 6))
        story.append(Paragraph(f"Success metrics: {escape(example['success_metrics'])}", styles["Body"]))
        story.append(Spacer(1, 8))

    try:
        doc.build(story, onFirstPage=draw_footer, onLaterPages=draw_footer)
    finally:
        hashlib.md5 = original_md5


# ─────────────────────────────────────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = build_cli()
    args = parser.parse_args()

    kit_root = args.kit_root.resolve()
    output_dir = args.output_dir.resolve()

    # Resolve config path: absolute if given as absolute, else relative to this script's dir
    config_arg = Path(args.config)
    config_path = config_arg if config_arg.is_absolute() else Path(__file__).resolve().parent / config_arg

    # Resolve PDF output dir: relative values go inside output_dir
    pdf_arg = Path(args.pdf_output_dir)
    pdf_output_dir = pdf_arg if pdf_arg.is_absolute() else output_dir / pdf_arg

    if not kit_root.exists():
        raise FileNotFoundError(f"Deployment kit not found: {kit_root}")
    if not config_path.exists():
        raise FileNotFoundError(
            f"Blueprint config not found: {config_path}\n"
            "Run with --config to specify the correct path."
        )

    blueprint = load_yaml(config_path)

    if args.kit_format == "genie_kit":
        profiles, room = build_domain_profiles_genie_kit(kit_root, blueprint)
    else:
        profiles, room = build_domain_profiles_legacy_contract(kit_root, blueprint)

    room_name = (room.get("room_name") or room.get("title") or "room").replace(" ", "_")

    markdown = build_markdown(blueprint, room, profiles)
    chunks = build_chunks(blueprint, room, profiles)

    output_dir.mkdir(parents=True, exist_ok=True)
    pdf_output_dir.mkdir(parents=True, exist_ok=True)

    playbook_path = output_dir / f"{room_name}_action_playbook.md"
    chunks_path = output_dir / f"{room_name}_action_playbook_chunks.json"
    summary_path = output_dir / "generation_summary.json"

    playbook_path.write_text(markdown, encoding="utf-8")
    chunks_path.write_text(json.dumps(chunks, indent=2, ensure_ascii=False), encoding="utf-8")

    # Per-domain PDFs
    pdf_paths: List[str] = []
    for profile in profiles:
        pdf_name = f"{room_name}_{profile.question_category}_action_playbook.pdf"
        pdf_path = pdf_output_dir / pdf_name
        print(f"  Rendering PDF: {pdf_path}")
        render_domain_pdf(room, profile, pdf_path)
        pdf_paths.append(pdf_path.resolve().relative_to(kit_root).as_posix())

    domain_output_root = output_dir / "by_domain"
    domain_output_root.mkdir(parents=True, exist_ok=True)
    domain_summaries = []

    for profile in profiles:
        domain_dir = domain_output_root / profile.question_category
        domain_dir.mkdir(parents=True, exist_ok=True)

        domain_markdown = build_domain_markdown(blueprint, room, profile)
        domain_source_name = f"{profile.question_category}_action_playbook.md"
        domain_chunks = build_domain_chunks(room, profile, domain_source_name)

        domain_playbook_path = domain_dir / domain_source_name
        domain_chunks_path = domain_dir / f"{profile.question_category}_action_playbook_chunks.json"
        domain_summary_path = domain_dir / "generation_summary.json"

        domain_playbook_path.write_text(domain_markdown, encoding="utf-8")
        domain_chunks_path.write_text(json.dumps(domain_chunks, indent=2, ensure_ascii=False), encoding="utf-8")

        domain_summary = {
            "kit_root": ".",
            "room_name": room_name,
            "domain": profile.display_name,
            "question_category": profile.question_category,
            "playbook_path": domain_playbook_path.resolve().relative_to(kit_root).as_posix(),
            "chunks_path": domain_chunks_path.resolve().relative_to(kit_root).as_posix(),
            "chunk_count": len(domain_chunks),
        }
        domain_summary_path.write_text(json.dumps(domain_summary, indent=2), encoding="utf-8")
        domain_summaries.append(domain_summary)

    summary = {
        "kit_root": ".",
        "kit_format": args.kit_format,
        "room_name": room_name,
        "playbook_title": blueprint["playbook"]["title"],
        "playbook_path": playbook_path.resolve().relative_to(kit_root).as_posix(),
        "chunks_path": chunks_path.resolve().relative_to(kit_root).as_posix(),
        "pdf_output_dir": pdf_output_dir.resolve().relative_to(kit_root).as_posix(),
        "pdf_paths": pdf_paths,
        "domain_count": len(profiles),
        "chunk_count": len(chunks),
        "question_categories": sorted({chunk["question_category"] for chunk in chunks}),
    }
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print(f"\nPlaybook : {playbook_path}")
    print(f"Chunks   : {chunks_path}")
    print(f"Summary  : {summary_path}")
    print(f"PDFs     : {pdf_output_dir}/")
    print(f"Domains  : {len(profiles)} | Chunks: {len(chunks)}")
    print(
        "\nNext step: upload PDF(s) to your UC Volume (or commit generated/pdfs/ to the repo),\n"
        "then run the action pipeline's index_operating_playbook task on Databricks."
    )


if __name__ == "__main__":
    main()
