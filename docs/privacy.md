# Data privacy and synthetic-data contract

The confidential workbook under the workspace-level `legacy/` folder is a schema reference only. This public example follows these rules:

1. No source row is copied, sampled, transformed, uploaded, or embedded.
2. No real organization, program, employee name, class ID, agent ID, or curriculum ID is retained.
3. Agent labels are pseudonymous (`Agent 0001`, `Agent 0002`, and so on).
4. Service-program names explicitly contain `(Fictional)`.
5. Dates, volumes, KPI scores, targets, and model coefficients are generated from seeded probability distributions.
6. Public assets must pass `scripts/quality/privacy_scan.py` before publication.
7. The confidential workbook remains outside the Git repository.

The synthetic generator is deterministic with seed `20260812`, making the demo reproducible without depending on the confidential file.
