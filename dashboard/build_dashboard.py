#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def field(name, expression=None):
    return {"name": name, "expression": expression or f"`{name}`"}


def query(dataset, fields, disaggregated=False):
    return [{"name": "main_query", "query": {"datasetName": dataset, "fields": fields, "disaggregated": disaggregated}}]


def counter(name, title, dataset, metric_name, expression):
    return {"name": name, "queries": query(dataset, [field(metric_name, expression)]), "spec": {"version": 2, "frame": {"title": title, "showTitle": True}, "widgetType": "counter", "encodings": {"value": {"fieldName": metric_name}}, "data": {"queryName": "main_query"}}}


def chart(name, title, widget_type, dataset, fields, encodings, disaggregated=False, version=3):
    return {"name": name, "queries": query(dataset, fields, disaggregated), "spec": {"version": version, "frame": {"title": title, "showTitle": True}, "widgetType": widget_type, "encodings": encodings, "data": {"queryName": "main_query"}}}


def table(name, title, dataset, names):
    return {"name": name, "queries": query(dataset, [field(value) for value in names], True), "spec": {"version": 2, "frame": {"title": title, "showTitle": True}, "widgetType": "table", "encodings": {"columns": [{"fieldName": value} for value in names]}, "data": {"queryName": "main_query"}}}


def selector(name, title, bindings):
    queries, encodings = [], []
    for dataset, field_name in bindings:
        query_name = f"{name}_{dataset}"
        queries.append({"name": query_name, "query": {"datasetName": dataset, "fields": [field(field_name), field(f"{field_name}_associativity", "COUNT_IF(`associative_filter_predicate_group`)")], "disaggregated": False}})
        encodings.append({"displayName": title, "fieldName": field_name, "queryName": query_name})
    return {"name": name, "queries": queries, "spec": {"version": 2, "frame": {"title": title, "showTitle": True, "showDescription": False}, "widgetType": "filter-single-select", "encodings": {"fields": encodings}}}


def item(widget, x, y, width, height):
    return {"widget": widget, "position": {"x": x, "y": y, "width": width, "height": height}}


def filters(datasets, *, no_cohort=(), include_people=False, include_agent=False, date_field=None):
    widgets = [item(selector("filter_program", "Service program", [(d, "service_program") for d in datasets]), 0, 0, 2, 2)]
    cohort_bindings = [(d, "cohort_name") for d in datasets if d not in set(no_cohort)]
    if cohort_bindings:
        widgets.append(item(selector("filter_cohort", "Cohort", cohort_bindings), 2, 0, 2, 2))
    widgets.append(item(selector("filter_kpi", "KPI", [(d, "kpi") for d in datasets]), 4, 0, 2, 2))
    if include_agent:
        widgets.append(item(selector("filter_agent", "Agent", [(d, "agent_label") for d in datasets if d in {"ramp", "agent_series"}]), 6, 0, 2, 2))
    if include_people:
        widgets.extend([
            item(selector("filter_channel", "Channel", [(d, "channel") for d in datasets if d in {"ramp", "agent_series"}]), 0, 2, 2, 2),
            item(selector("filter_language", "Language", [(d, "language") for d in datasets if d in {"ramp", "agent_series"}]), 2, 2, 2, 2),
            item(selector("filter_site", "Site", [(d, "site") for d in datasets if d in {"ramp", "agent_series"}]), 4, 2, 2, 2),
        ])
    if date_field:
        date_bindings = date_field if isinstance(date_field, list) else [date_field]
        field_name = date_bindings[0][1]
        widgets.append(item(selector(f"filter_{field_name}", "Date", date_bindings), 6, 2 if include_people else 0, 2, 2))
    return widgets


def build():
    quantitative = {"type": "quantitative"}
    categorical = {"type": "categorical"}
    temporal = {"type": "temporal"}

    executive = filters(["ramp", "scorecard"], date_field=("ramp", "performance_date")) + [
        item(counter("new_hires", "New Hires Represented", "ramp", "distinct_new_hires", "COUNT(DISTINCT `agent_id`)"), 0, 2, 2, 3),
        item(counter("days_to_target", "Average Days to Target", "scorecard", "days_to_target", "AVG(`days_to_target`)"), 2, 2, 2, 3),
        item(counter("target_attainment", "Static Target Attainment (%)", "ramp", "attainment_rate", "COUNT_IF(`at_static_target`) * 100.0 / NULLIF(COUNT(*), 0)"), 4, 2, 2, 3),
        item(counter("training_attainment", "Training Target Attainment (%)", "ramp", "training_rate", "COUNT_IF(`at_training_target`) * 100.0 / NULLIF(COUNT(*), 0)"), 6, 2, 2, 3),
        item(chart("ramp_trend", "Static Target Attainment by Tenure Week and KPI (%)", "line", "ramp", [field("kpi"), field("tenure_week"), field("attainment_rate", "COUNT_IF(`at_static_target`) * 100.0 / NULLIF(COUNT(*), 0)")], {"x": {"fieldName": "tenure_week", "scale": quantitative}, "y": {"fieldName": "attainment_rate", "scale": quantitative}, "color": {"fieldName": "kpi", "scale": categorical}}), 0, 5, 5, 7),
        item(chart("program_attainment", "Target Attainment by Service Program (%)", "bar", "scorecard", [field("service_program"), field("static_target_attainment_rate", "AVG(`static_target_attainment_rate`) * 100.0")], {"x": {"fieldName": "static_target_attainment_rate", "scale": quantitative}, "y": {"fieldName": "service_program", "scale": categorical}}), 5, 5, 3, 7),
    ]

    actions = [
        item(counter("action_plan_count", "Current Action Plans", "actions", "plan_count", "COUNT(`analysis_id`)"), 0, 0, 2, 3),
        item(counter("action_warning_count", "Research Warnings", "actions", "warning_count", "COUNT(`warning`)"), 2, 0, 2, 3),
        item(counter("retrieved_context", "Retrieved Context Characters", "actions", "context_size", "COALESCE(SUM(`retrieved_context_characters`), 0)"), 4, 0, 2, 3),
        item(table("insight_feed", "Action Intelligence Status and Latest Insight", "actions", ["module_status", "generated_at", "question_category", "question", "insight_summary", "warning"]), 0, 3, 8, 6),
        item(table("action_feed", "Evidence-Grounded Recommended Action Plan", "actions", ["module_status", "generated_at", "recommended_action_plan", "model_endpoint", "retrieved_context_characters"]), 0, 9, 8, 9),
    ]

    learning = filters(["curves", "learning_series", "volume_progression"]) + [
        item(counter("average_r2", "Average Selected-Model R-squared", "curves", "average_r2", "AVG(`r_squared`)"), 0, 2, 2, 3),
        item(counter("average_days", "Average Days to Target", "curves", "average_days", "AVG(`days_to_target`)"), 2, 2, 2, 3),
        item(chart("observed_fitted_curve", "Observed vs Selected Learning Curve (Target Index)", "line", "learning_series", [field("series_name"), field("tenure_day"), field("target_index", "AVG(`target_index`)")], {"x": {"fieldName": "tenure_day", "scale": quantitative}, "y": {"fieldName": "target_index", "scale": quantitative}, "color": {"fieldName": "series_name", "scale": categorical}}), 0, 5, 5, 8),
        item(chart("weekly_volume_curve", "Average Weekly Volume per Agent by Tenure Week", "line", "volume_progression", [field("tenure_week"), field("average_weekly_volume_per_agent", "AVG(`average_weekly_volume_per_agent`)")], {"x": {"fieldName": "tenure_week", "scale": quantitative}, "y": {"fieldName": "average_weekly_volume_per_agent", "scale": quantitative}}), 5, 5, 3, 8),
        item(chart("cumulative_volume_curve", "Average Cumulative Volume per Agent", "line", "volume_progression", [field("tenure_week"), field("average_cumulative_volume_per_agent", "AVG(`average_cumulative_volume_per_agent`)")], {"x": {"fieldName": "tenure_week", "scale": quantitative}, "y": {"fieldName": "average_cumulative_volume_per_agent", "scale": quantitative}}), 0, 13, 4, 7),
        item(chart("days_by_cohort", "Days to Target by Cohort", "bar", "curves", [field("cohort_name"), field("days_to_target", "AVG(`days_to_target`)")], {"x": {"fieldName": "days_to_target", "scale": quantitative}, "y": {"fieldName": "cohort_name", "scale": categorical}}), 4, 13, 4, 7),
        item(table("curve_models", "Governed Learning-Curve Results", "curves", ["service_program", "cohort_name", "kpi", "model_type", "r_squared", "days_to_target", "registered_model_version", "interpretation"]), 0, 20, 8, 7),
    ]

    drivers = filters(["driver", "tenure_regression", "volume_regression"]) + [
        item(counter("tenure_correlation", "Average |Tenure–KPI Correlation|", "driver", "tenure_r", "AVG(`abs_tenure_correlation`)"), 0, 2, 2, 3),
        item(counter("volume_correlation", "Average |Volume–KPI Correlation|", "driver", "volume_r", "AVG(`abs_volume_correlation`)"), 2, 2, 2, 3),
        item(chart("tenure_regression", "KPI Target Index vs Tenure with Regression Fit", "line", "tenure_regression", [field("series_name"), field("average_tenure_day"), field("series_value", "AVG(`series_value`)")], {"x": {"fieldName": "average_tenure_day", "scale": quantitative}, "y": {"fieldName": "series_value", "scale": quantitative}, "color": {"fieldName": "series_name", "scale": categorical}}), 0, 5, 4, 8),
        item(chart("volume_regression", "KPI Target Index vs Average Daily Volume", "scatter", "volume_regression", [field("series_name"), field("average_daily_volume"), field("series_value", "AVG(`series_value`)")], {"x": {"fieldName": "average_daily_volume", "scale": quantitative}, "y": {"fieldName": "series_value", "scale": quantitative}, "color": {"fieldName": "series_name", "scale": categorical}}), 4, 5, 4, 8),
        item(chart("volume_attainment", "Target Attainment vs Average Daily Volume", "scatter", "driver", [field("kpi"), field("average_daily_volume"), field("target_attainment_rate", "AVG(`target_attainment_rate`) * 100.0")], {"x": {"fieldName": "average_daily_volume", "scale": quantitative}, "y": {"fieldName": "target_attainment_rate", "scale": quantitative}, "color": {"fieldName": "kpi", "scale": categorical}}), 0, 13, 4, 7),
        item(table("driver_detail", "Volume-Aware Regression Diagnostics", "driver", ["service_program", "cohort_name", "kpi", "tenure_week", "average_tenure_day", "average_daily_volume", "average_cumulative_volume", "target_index", "target_attainment_rate", "tenure_correlation", "volume_correlation", "agent_count", "observation_count"]), 4, 13, 4, 7),
    ]

    process = filters(["process", "process_series", "lss"], date_field=[("process", "period"), ("process_series", "period")]) + [
        item(counter("special_causes", "Adverse >3 Sigma Signals", "process", "special_causes", "COUNT_IF(`special_cause_flag`)"), 0, 2, 2, 3),
        item(counter("first_pass_yield", "First-Pass Yield (%)", "lss", "yield_pct", "SUM(`opportunity_count` - `defect_count`) * 100.0 / NULLIF(SUM(`opportunity_count`), 0)"), 2, 2, 2, 3),
        item(counter("dpmo", "DPMO", "lss", "dpmo", "SUM(`defect_count`) * 1000000.0 / NULLIF(SUM(`opportunity_count`), 0)"), 4, 2, 2, 3),
        item(chart("control_chart", "Direction-Aware Process Control Chart", "line", "process_series", [field("series_name"), field("period"), field("series_value", "AVG(`series_value`)")], {"x": {"fieldName": "period", "scale": temporal}, "y": {"fieldName": "series_value", "scale": quantitative}, "color": {"fieldName": "series_name", "scale": categorical}}), 0, 5, 5, 8),
        item(chart("defects_by_kpi", "Readiness Defects by KPI", "bar", "lss", [field("kpi"), field("defect_count", "SUM(`defect_count`)")], {"x": {"fieldName": "defect_count", "scale": quantitative}, "y": {"fieldName": "kpi", "scale": categorical}}), 5, 5, 3, 8),
        item(table("control_detail", "Special-Cause and Control Detail", "process", ["period", "service_program", "cohort_name", "kpi", "directional_z_score", "control_status", "cohort_score", "centerline", "process_std", "agent_count", "total_volume"]), 0, 13, 8, 7),
    ]

    outliers = filters(["outliers"]) + [
        item(counter("adverse_outliers", "Adverse Agent-Week Outliers", "outliers", "outlier_count", "COUNT_IF(`adverse_outlier`)"), 0, 2, 2, 3),
        item(counter("outlier_rate", "Adverse Outlier Rate (%)", "outliers", "outlier_rate", "COUNT_IF(`adverse_outlier`) * 100.0 / NULLIF(COUNT(*), 0)"), 2, 2, 2, 3),
        item(chart("outlier_volume", "Directional Z-score vs Weekly Volume", "scatter", "outliers", [field("outlier_status"), field("total_volume"), field("directional_z_score", "AVG(`directional_z_score`)")], {"x": {"fieldName": "total_volume", "scale": quantitative}, "y": {"fieldName": "directional_z_score", "scale": quantitative}, "color": {"fieldName": "outlier_status", "scale": categorical}}), 0, 5, 5, 8),
        item(chart("outliers_by_kpi", "Adverse Outliers by KPI", "bar", "outliers", [field("kpi"), field("adverse_count", "COUNT_IF(`adverse_outlier`)")], {"x": {"fieldName": "adverse_count", "scale": quantitative}, "y": {"fieldName": "kpi", "scale": categorical}}), 5, 5, 3, 8),
        item(table("outlier_detail", "Z-score and IQR Agent-Week Diagnostics", "outliers", ["agent_label", "service_program", "cohort_name", "kpi", "tenure_week", "agent_score", "total_volume", "z_score", "directional_z_score", "iqr_lower_bound", "iqr_upper_bound", "z_score_outlier", "iqr_outlier", "adverse_outlier", "outlier_status"]), 0, 13, 8, 8),
    ]

    cohorts = filters(["scorecard"]) + [
        item(counter("cohort_agents", "Agents Represented", "scorecard", "agents", "SUM(`agent_count`) / NULLIF(COUNT(DISTINCT `kpi`), 0)"), 0, 2, 2, 3),
        item(counter("cohort_attainment", "Average Target Attainment (%)", "scorecard", "attainment", "AVG(`static_target_attainment_rate`) * 100.0"), 2, 2, 2, 3),
        item(chart("cohort_rank", "Cohort Target Attainment (%)", "bar", "scorecard", [field("cohort_name"), field("attainment", "AVG(`static_target_attainment_rate`) * 100.0")], {"x": {"fieldName": "attainment", "scale": quantitative}, "y": {"fieldName": "cohort_name", "scale": categorical}}), 0, 5, 4, 7),
        item(table("cohort_detail", "Cohort Readiness Scorecard", "scorecard", ["service_program", "cohort_name", "kpi", "agent_count", "weighted_score", "static_target_attainment_rate", "days_to_target", "best_model_r_squared"]), 4, 2, 4, 10),
    ]

    forecast = filters(["forecast", "forecast_series"], no_cohort={"forecast", "forecast_series"}, date_field=[("forecast", "period"), ("forecast_series", "period")]) + [
        item(chart("forecast_trend", "Prophet Forecast with 80% Interval", "line", "forecast_series", [field("series_name"), field("period"), field("series_value", "AVG(`series_value`)")], {"x": {"fieldName": "period", "scale": temporal}, "y": {"fieldName": "series_value", "scale": quantitative}, "color": {"fieldName": "series_name", "scale": categorical}}), 0, 2, 5, 7),
        item(table("forecast_interval", "80% Forecast Interval", "forecast", ["period", "service_program", "kpi", "forecast_value", "forecast_lower", "forecast_upper", "is_actual", "model_type"]), 5, 2, 3, 7),
    ]

    agents = filters(["ramp", "agent_series"], include_people=True, include_agent=True) + [
        item(counter("agent_count", "Pseudonymous Agents", "ramp", "agents", "COUNT(DISTINCT `agent_id`)"), 6, 2, 2, 3),
        item(chart("agent_trajectory", "Agent Score versus Static and Training Targets", "line", "agent_series", [field("series_name"), field("tenure_day"), field("series_value", "AVG(`series_value`)")], {"x": {"fieldName": "tenure_day", "scale": quantitative}, "y": {"fieldName": "series_value", "scale": quantitative}, "color": {"fieldName": "series_name", "scale": categorical}}), 0, 5, 5, 8),
        item(table("agent_detail", "Pseudonymous Agent Drill-through", "ramp", ["performance_date", "agent_label", "service_program", "cohort_name", "channel", "language", "tenure_day", "kpi", "agent_score", "volume", "cumulative_volume", "volume_bin", "static_target", "training_target", "at_static_target"]), 5, 5, 3, 8),
    ]

    return {
        "datasets": [
            {"name": "ramp", "displayName": "New-Hire Daily KPI", "asset_name": "workspace.contact_center_gold.mv_new_hire_kpi_daily"},
            {"name": "curves", "displayName": "Best Learning Curves", "asset_name": "workspace.contact_center_gold.mv_learning_curve_best"},
            {"name": "learning_series", "displayName": "Observed and Fitted Learning Curves", "asset_name": "workspace.contact_center_gold.mv_learning_curve_series"},
            {"name": "volume_progression", "displayName": "Ramp Volume Progression", "asset_name": "workspace.contact_center_gold.mv_ramp_volume_progression"},
            {"name": "driver", "displayName": "KPI Driver Regression", "asset_name": "workspace.contact_center_gold.mv_kpi_driver_regression"},
            {"name": "tenure_regression", "displayName": "Tenure Regression Series", "asset_name": "workspace.contact_center_gold.mv_tenure_regression_series"},
            {"name": "volume_regression", "displayName": "Volume Regression Series", "asset_name": "workspace.contact_center_gold.mv_volume_regression_series"},
            {"name": "process", "displayName": "Process Control", "asset_name": "workspace.contact_center_gold.mv_process_control"},
            {"name": "process_series", "displayName": "Process Control Series", "asset_name": "workspace.contact_center_gold.mv_process_control_series"},
            {"name": "lss", "displayName": "Lean Six Sigma Summary", "asset_name": "workspace.contact_center_gold.mv_lean_six_sigma_summary"},
            {"name": "outliers", "displayName": "Agent Weekly Outliers", "asset_name": "workspace.contact_center_gold.mv_agent_weekly_outliers"},
            {"name": "actions", "displayName": "Action Intelligence Dashboard", "asset_name": "workspace.contact_center_gold.mv_action_intelligence_dashboard"},
            {"name": "scorecard", "displayName": "Cohort Scorecard", "asset_name": "workspace.contact_center_gold.mv_cohort_scorecard"},
            {"name": "forecast", "displayName": "Prophet KPI Forecast", "asset_name": "workspace.contact_center_gold.mv_kpi_forecast"},
            {"name": "forecast_series", "displayName": "Forecast Interval Series", "asset_name": "workspace.contact_center_gold.mv_kpi_forecast_series"},
            {"name": "agent_series", "displayName": "Agent Score and Target Series", "asset_name": "workspace.contact_center_gold.mv_agent_target_series"},
        ],
        "pages": [
            {"name": "executive", "displayName": "Executive Summary", "layout": executive},
            {"name": "actions", "displayName": "Insight & Action Center", "layout": actions},
            {"name": "learning", "displayName": "Learning & Volume", "layout": learning},
            {"name": "drivers", "displayName": "Drivers & Regression", "layout": drivers},
            {"name": "process", "displayName": "Process Control", "layout": process},
            {"name": "outliers", "displayName": "Outliers", "layout": outliers},
            {"name": "cohorts", "displayName": "Cohort Comparison", "layout": cohorts},
            {"name": "forecast", "displayName": "Forecast", "layout": forecast},
            {"name": "agents", "displayName": "Agent Detail", "layout": agents},
        ],
        "uiSettings": {"theme": {"widgetHeaderAlignment": "ALIGNMENT_UNSPECIFIED"}, "applyModeEnabled": False},
    }


if __name__ == "__main__":
    dashboard = build()
    output = ROOT / "contact_center_new_hire_ramp.lvdash.json"
    output.write_text(json.dumps(dashboard, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {output.name}: {len(dashboard['pages'])} pages, {sum(len(page['layout']) for page in dashboard['pages'])} widgets, {len(dashboard['datasets'])} datasets")
