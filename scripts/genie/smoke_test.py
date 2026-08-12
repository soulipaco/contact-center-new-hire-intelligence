#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import tempfile
import time
from pathlib import Path


def api(method: str, endpoint: str, profile: str, payload: dict | None = None) -> dict:
    command = ["databricks", "api", method, endpoint]
    payload_path = None
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


def main() -> int:
    parser = argparse.ArgumentParser(description="Run one Genie conversation smoke test")
    parser.add_argument("--profile", required=True)
    parser.add_argument("--space-id", required=True)
    parser.add_argument("--question", default="How many distinct synthetic new hires are in the data?")
    args = parser.parse_args()

    base = f"/api/2.0/genie/spaces/{args.space_id}"
    started = api("post", f"{base}/start-conversation", args.profile, {"content": args.question})
    conversation_id = started["conversation"].get("conversation_id") or started["conversation"]["id"]
    message_id = started["message"]["id"]
    message = started["message"]
    for _ in range(30):
        if message["status"] in {"COMPLETED", "FAILED", "CANCELLED"}:
            break
        time.sleep(3)
        message = api("get", f"{base}/conversations/{conversation_id}/messages/{message_id}", args.profile)

    query_attachments = [item for item in (message.get("attachments") or []) if item.get("query")]
    print(json.dumps({
        "status": message["status"],
        "attachment_count": len(message.get("attachments") or []),
        "generated_sql": query_attachments[0]["query"].get("query") if query_attachments else None,
        "error": message.get("error"),
    }, indent=2))
    return 0 if message["status"] == "COMPLETED" and query_attachments else 1


if __name__ == "__main__":
    raise SystemExit(main())
