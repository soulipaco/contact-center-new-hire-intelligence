from __future__ import annotations

import json
from pathlib import Path

import yaml

from dashboard.build_dashboard import build
from scripts.project.cli import build_deployable, load_config, render_customer_adapter, validate_config


ROOT = Path(__file__).resolve().parents[1]


def test_dashboard_inventory_and_dataset_references() -> None:
    dashboard = build()
    dataset_names = {dataset["name"] for dataset in dashboard["datasets"]}
    assert len(dashboard["pages"]) == 9
    assert len(dataset_names) == 16
    assert sum(len(page["layout"]) for page in dashboard["pages"]) == 74
    assert {"actions", "learning", "drivers", "process", "outliers"}.issubset(
        {page["name"] for page in dashboard["pages"]}
    )

    for page in dashboard["pages"]:
        for item in page["layout"]:
            for query in item["widget"].get("queries", []):
                assert query["query"]["datasetName"] in dataset_names


def test_forecast_filter_uses_only_available_dimensions() -> None:
    dashboard = build()
    forecast = next(page for page in dashboard["pages"] if page["name"] == "forecast")
    assert all(item["widget"]["name"] != "filter_cohort" for item in forecast["layout"])


def test_genie_and_playbook_generated_contracts() -> None:
    genie = json.loads(
        (ROOT / "genie/serialized/contact_center_new_hire.geniespace.json").read_text(encoding="utf-8")
    )
    summary = json.loads(
        (ROOT / "action_intelligence/playbook_generator/generated/generation_summary.json").read_text(encoding="utf-8")
    )
    assert len(genie["data_sources"]["tables"]) == 5
    assert len(genie["benchmarks"]["questions"]) == 12
    assert summary["domain_count"] == 1
    assert summary["chunk_count"] == 9
    assert summary["kit_root"] == "."
    assert all(":" not in path for path in summary["pdf_paths"])


def test_demo_and_customer_configuration_contracts() -> None:
    demo = load_config(ROOT / "config/project.yml")
    customer = load_config(ROOT / "config/project.customer.example.yml")
    clean_room = load_config(ROOT / "examples/fictional_customer/config.yml")
    assert validate_config(demo) == []
    assert validate_config(customer) == []
    assert validate_config(clean_room) == []

    broken = yaml.safe_load(yaml.safe_dump(customer))
    del broken["source"]["mappings"]["observations"]["volume"]
    errors = validate_config(broken)
    assert any("observations.volume" in error for error in errors)


def test_customer_adapter_and_deployable_build(tmp_path: Path) -> None:
    customer = load_config(ROOT / "config/project.customer.example.yml")
    customer["project"]["catalog"] = "analytics"
    customer["project"]["schemas"]["bronze"] = "ramp_bronze"
    customer["project"]["schemas"]["silver"] = "ramp_silver"
    customer["project"]["schemas"]["gold"] = "ramp_gold"
    customer["project"]["schemas"]["models"] = "ramp_models"
    customer["analytics"]["new_hire_days"] = 84
    customer["analytics"]["tenured_baseline_min_days"] = 85
    customer["analytics"]["learning_curve_max_days"] = 84
    customer["analytics"]["forecast_periods"] = 9
    customer["analytics"]["forecast_interval_width"] = 0.9
    customer["analytics"]["outliers"]["z_score_threshold"] = 2.5
    customer["analytics"]["outliers"]["iqr_multiplier"] = 2.0

    adapter = render_customer_adapter(customer)
    assert "`analytics`.`ramp_bronze`.`bronze_agent_kpi_daily_raw`" in adapter
    assert "`company_operations`.`performance`.`agent_kpi_daily`" in adapter
    assert "metric_numerator" in adapter

    output = build_deployable(customer, tmp_path / "deployable")
    jobs = (output / "infrastructure/databricks/resources/jobs.yml").read_text(encoding="utf-8")
    serving = (output / "lakehouse/notebooks/05_create_serving_views.sql").read_text(encoding="utf-8")
    medallion = (output / "lakehouse/notebooks/02_build_medallion.sql").read_text(encoding="utf-8")
    forecast = (output / "lakehouse/notebooks/04_forecast_prophet.py").read_text(encoding="utf-8")
    learning = (output / "lakehouse/notebooks/03_train_learning_curves.py").read_text(encoding="utf-8")
    assert "00_customer_adapter.sql" in jobs
    assert "analytics.ramp_gold" in serving
    assert "workspace.contact_center_gold" not in serving
    assert "tenure_day <= 84" in medallion
    assert "periods=9" in forecast and "interval_width=0.9" in forecast
    assert "EXPLODE(SEQUENCE(1, 84))" in serving
    assert "ABS(z_score) >= 2.5" in serving
    assert "d.q1 - 2.0 *" in serving
    assert 'MODEL_SCHEMA = f"{CATALOG}.ramp_models"' in learning
    assert '/Shared/my-contact-center-ramp-intelligence_learning_curves' in learning
    assert '/Shared/my-contact-center-ramp-intelligence_forecasts' in forecast
    assert "name: my-contact-center-ramp-intelligence" in (output / "databricks.yml").read_text(encoding="utf-8")
    assert not (output / "infrastructure/databricks/resources/action_intelligence.yml").exists()
    assert not (output / "examples").exists()
