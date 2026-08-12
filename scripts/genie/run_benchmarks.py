#!/usr/bin/env python3
"""Execute the repository's Genie benchmark suite against a deployed space."""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import tempfile
import time
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
TERMINAL = {"COMPLETED", "FAILED", "CANCELLED"}

# These gates intentionally test semantic choices, not exact formatting or aliases.
# A pipe separates equivalent governed terms; satisfying one term in each group is enough.
SQL_GATES: dict[str, tuple[str, ...]] = {
    "01_kpi_by_tenure_week": ("mv_new_hire_kpi_daily", "tenure_week", "sum(", "denominator"),
    "02_target_attainment_day_60": ("at_static_target", "tenure_day", "group by", "kpi"),
    "03_fastest_qa_cohort": ("mv_learning_curve_best", "days_to_target", "qa score", "order by"),
    "04_aht_directionality": ("mv_new_hire_kpi_daily", "aht", "order by", "asc"),
    "05_inconclusive_curves": ("mv_learning_curve_best", "r_squared", "0.30"),
    "06_future_forecast": ("mv_kpi_forecast", "is_actual", "false", "forecast_lower", "forecast_upper"),
    "07_distinct_new_hires": ("count(distinct", "agent_id", "mv_new_hire_kpi_daily"),
    "08_sigma_exceptions": ("mv_sigma_band_comparison", "target_1_sigma", "below_1_sigma", "max(period)"),
    "09_curve_explanation": ("mv_learning_curve_best", "interpretation", "r_squared", "qa pass rate"),
    "10_training_vs_static_target": ("training_target", "static_target", "aht", "service_program"),
    "11_volume_reliability": ("volume_bin", "denominator", "count(distinct", "qa score"),
    "12_cohort_scorecard": ("mv_cohort_scorecard", "static_target_attainment_rate", "days_to_target", "best_model_r_squared|r_squared"),
}


def api(cli: str, method: str, endpoint: str, profile: str, payload: dict | None = None) -> dict:
    command = [cli, "api", method, endpoint]
    payload_path: Path | None = None
    if payload is not None:
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", encoding="utf-8", delete=False) as handle:
            json.dump(payload, handle)
            payload_path = Path(handle.name)
        command.extend(["--json", f"@{payload_path}"])
    command.extend(["--profile", profile, "--output", "json"])
    try:
        result = subprocess.run(command, capture_output=True, text=True)
        if result.returncode:
            raise RuntimeError(result.stderr.strip() or result.stdout.strip() or "Databricks API call failed")
        return json.loads(result.stdout)
    finally:
        if payload_path:
            payload_path.unlink(missing_ok=True)


def normalized_sql(sql: str) -> str:
    return re.sub(r"\s+", " ", sql.lower()).strip()


def evaluate(cli: str, profile: str, space_id: str, benchmark: dict, timeout: int) -> dict:
    base = f"/api/2.0/genie/spaces/{space_id}"
    started = api(cli, "post", f"{base}/start-conversation", profile, {"content": benchmark["question"]})
    conversation_id = started["conversation"].get("conversation_id") or started["conversation"]["id"]
    message = started["message"]
    message_id = message["id"]
    deadline = time.monotonic() + timeout
    while message.get("status") not in TERMINAL and time.monotonic() < deadline:
        time.sleep(3)
        message = api(cli, "get", f"{base}/conversations/{conversation_id}/messages/{message_id}", profile)

    attachments = message.get("attachments") or []
    queries = [item["query"] for item in attachments if item.get("query")]
    generated_sql = queries[0].get("query") if queries else None
    sql_text = normalized_sql(generated_sql or "")
    stem = benchmark["_path"].stem
    required = SQL_GATES[stem]
    missing = [term for term in required if not any(option in sql_text for option in term.split("|"))]
    status = message.get("status", "TIMEOUT")
    passed = status == "COMPLETED" and bool(generated_sql) and not missing
    return {
        "id": benchmark["id"],
        "benchmark": stem,
        "question": benchmark["question"],
        "status": status,
        "passed": passed,
        "missing_sql_gates": missing,
        "generated_sql": generated_sql,
        "conversation_id": conversation_id,
        "message_id": message_id,
        "error": message.get("error"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Run all repository Genie benchmarks")
    parser.add_argument("--profile", required=True)
    parser.add_argument("--space-id", required=True)
    parser.add_argument("--databricks-cli", default=os.environ.get("DATABRICKS_CLI_PATH", "databricks"))
    parser.add_argument("--timeout", type=int, default=180, help="seconds allowed per question")
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--benchmark",
        action="append",
        help="run only this benchmark filename stem; repeat to select more than one",
    )
    args = parser.parse_args()

    benchmarks = []
    for path in sorted((ROOT / "genie" / "source" / "benchmarks").glob("*.yml")):
        benchmark = yaml.safe_load(path.read_text(encoding="utf-8"))
        benchmark["_path"] = path
        benchmarks.append(benchmark)
    if args.benchmark:
        requested = set(args.benchmark)
        available = {item["_path"].stem for item in benchmarks}
        unknown = requested - available
        if unknown:
            parser.error(f"unknown benchmark(s): {', '.join(sorted(unknown))}")
        benchmarks = [item for item in benchmarks if item["_path"].stem in requested]

    results = []
    for index, benchmark in enumerate(benchmarks, start=1):
        print(f"[{index:02d}/{len(benchmarks):02d}] {benchmark['question']}", flush=True)
        result = evaluate(args.databricks_cli, args.profile, args.space_id, benchmark, args.timeout)
        results.append(result)
        print("  PASS" if result["passed"] else f"  FAIL ({result['status']})", flush=True)

    report = {
        "space_id": args.space_id,
        "total": len(results),
        "passed": sum(item["passed"] for item in results),
        "failed": sum(not item["passed"] for item in results),
        "results": results,
    }
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("total", "passed", "failed")}, indent=2))
    return 0 if report["failed"] == 0 and report["total"] == len(benchmarks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
