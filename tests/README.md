# Tests and live evidence

`test_artifact_contracts.py` protects cross-module contracts: dashboard inventory,
dataset references, forecast-filter compatibility, Genie benchmark counts, and
portable playbook-generation metadata. Run it with `python -m pytest -q`.

Executable source gates also live under `scripts/quality/`, while live Genie
behavioral evaluation lives under `scripts/genie/run_benchmarks.py`. Raw live
outputs are ignored because they contain workspace identifiers and generated SQL;
publication-safe aggregate evidence is maintained in `docs/validation_results.md`.
