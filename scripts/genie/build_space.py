#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(Path(__file__).resolve().parent))

from assemble_space import assemble_payload  # noqa: E402


def main() -> int:
    payload = assemble_payload("bundle-managed", "/bundle-managed")
    serialized = json.loads(payload["serialized_space"])
    output_dir = ROOT / "genie" / "serialized"
    output_dir.mkdir(exist_ok=True)
    output = output_dir / "contact_center_new_hire.geniespace.json"
    output.write_text(json.dumps(serialized, indent=2) + "\n", encoding="utf-8")
    print(
        f"Wrote {output.name}: "
        f"{len(serialized['data_sources']['tables'])} tables, "
        f"{len(serialized['instructions']['example_question_sqls'])} examples, "
        f"{len(serialized['benchmarks']['questions'])} benchmarks"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
