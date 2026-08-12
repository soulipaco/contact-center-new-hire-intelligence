#!/usr/bin/env python3
from __future__ import annotations

import sys
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
TEXT_SUFFIXES = {".md", ".py", ".sql", ".yml", ".yaml", ".json"}
FORBIDDEN = {
    "teleperformance",
    "mercedes-benz",
    "mercedesbenz",
    "delivery hero",
    "dhero",
    "samsung",
    "deliveroo",
    "vodafone",
    "49106",
    "datawrhs-qa",
}
FORBIDDEN_PATTERNS = {
    "absolute Windows user path": re.compile(r"[a-z]:[\\\\/]users[\\\\/]", re.IGNORECASE),
    "Databricks token": re.compile(r"\bdapi[a-z0-9]{20,}\b", re.IGNORECASE),
    "GitHub token": re.compile(r"\b(?:ghp|github_pat)_[a-z0-9_]{20,}\b", re.IGNORECASE),
}

findings = []
for path in ROOT.rglob("*"):
    if not path.is_file() or path.suffix.lower() not in TEXT_SUFFIXES:
        continue
    if any(part in {"build", ".git", ".local", ".venv", "__pycache__"} for part in path.relative_to(ROOT).parts):
        continue
    if path.resolve() == Path(__file__).resolve():
        continue
    text = path.read_text(encoding="utf-8", errors="ignore").lower()
    for term in sorted(FORBIDDEN):
        if term in text:
            findings.append((path.relative_to(ROOT), term))
    for label, pattern in FORBIDDEN_PATTERNS.items():
        if pattern.search(text):
            findings.append((path.relative_to(ROOT), label))

if findings:
    print("FAIL: potentially identifying legacy values found")
    for path, term in findings:
        print(f"  {path}: {term}")
    sys.exit(1)

print("PASS: no forbidden legacy identifiers found in public example assets")
