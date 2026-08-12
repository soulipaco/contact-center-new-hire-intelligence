#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def cli_api(method: str, endpoint: str, payload: dict, profile: str) -> dict:
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", encoding="utf-8", delete=False) as handle:
        json.dump(payload, handle)
        payload_path = Path(handle.name)
    try:
        command = ["databricks", "api", method, endpoint, "--json", f"@{payload_path}", "--profile", profile, "--output", "json"]
        completed = subprocess.run(command, check=True, capture_output=True, text=True)
        return json.loads(completed.stdout) if completed.stdout.strip() else {}
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"Databricks dashboard API failed: {exc.stderr.strip()}") from exc
    finally:
        payload_path.unlink(missing_ok=True)


def main() -> int:
    parser = argparse.ArgumentParser(description="Deploy the contact-center AI/BI dashboard")
    parser.add_argument("--profile", required=True)
    parser.add_argument("--warehouse-id", required=True)
    parser.add_argument("--parent-path", required=True)
    parser.add_argument("--dashboard-id")
    parser.add_argument("--publish", action="store_true")
    args = parser.parse_args()

    serialized = (ROOT / "contact_center_new_hire_ramp.lvdash.json").read_text(encoding="utf-8")
    payload = {
        "display_name": "Contact Center New-Hire Ramp Intelligence",
        "warehouse_id": args.warehouse_id,
        "parent_path": args.parent_path,
        "serialized_dashboard": serialized,
    }
    method = "patch" if args.dashboard_id else "post"
    endpoint = "/api/2.0/lakeview/dashboards" + (f"/{args.dashboard_id}" if args.dashboard_id else "")
    result = cli_api(method, endpoint, payload, args.profile)
    dashboard_id = args.dashboard_id or result.get("dashboard_id")
    if not dashboard_id:
        raise RuntimeError("Dashboard API did not return a dashboard ID.")
    print(f"Dashboard deployed. Dashboard ID: {dashboard_id}")
    if args.publish:
        cli_api("post", f"/api/2.0/lakeview/dashboards/{dashboard_id}/published", {"embed_credentials": False, "warehouse_id": args.warehouse_id}, args.profile)
        print("Dashboard published with viewer credentials (embed_credentials=false).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
