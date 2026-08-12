# Acceptance matrix

This is the release contract. “Verified” requires a repository artifact and live
Databricks evidence; source code existence alone is not enough.

| Area | Acceptance evidence | Status |
|---|---|---|
| Privacy | Repository/value-domain scan passes; confidential workbook and identifiers are excluded | Verified |
| Synthetic data | Seed `20260812`; five fictional programs, 15 cohorts, 300 agents, eight KPIs | Verified |
| Bronze | Four Delta sources contain load metadata and feed Silver without row loss | Verified |
| Silver | Typed fact, SCD2 agent, effective target, and training-class dimensions; overlap/join gates pass | Verified |
| Gold | Enriched daily fact, monthly populations, baselines, curve results, and forecasts return rows | Verified |
| Reliability | Volume bins remain in 1-4 and cumulative volume is published for interpretation | Verified |
| Targets | Static/training targets are direction- and format-aware | Verified |
| Sigma | Higher/lower-is-better 1/2/3 sigma boundaries are materialized and queried by live benchmarks | Verified |
| Learning curves | Four candidates and exactly one winner per program/cohort/KPI | Verified |
| ML governance | Candidate runs contain parameters/metrics; winners are packaged in a registered UC portfolio model | Verified |
| Forecasting | Six future Prophet periods; lower <= point <= upper | Verified |
| Semantic layer | Five Genie views plus governed action, learning, volume, regression, process-control, outlier, forecast, and agent presentation views return rows | Verified |
| Genie deployment | Bundle read-back shows 5 tables, 6 examples, 5 filters, 5 measures, and 12 benchmarks | Verified |
| Genie evaluation | 12/12 questions completed with SQL and passed source-specific gates | Verified |
| Dashboard inventory | 9 pages, 74 widgets, 16 datasets generated and deployed | Verified |
| Dashboard interactions | Program filter changed rendered counts and measures; page-level filters compile only against compatible datasets | Verified |
| Dashboard advanced visuals | Observed/fitted learning curve, volume progression, KPI-tenure and KPI-volume regression, process-control, outlier, forecast interval, and target overlays rendered with live data | Verified |
| In-dashboard Genie | Native Ask Genie surface renders on the dashboard and the governed Genie space is separately linked | Verified |
| Core automation | Bootstrap, daily, weekly ML, and monthly forecast workflows validate; dev schedules are paused | Verified |
| Action intelligence | Idempotent VS indexing, Genie Deep Research, retrieval, LLM generation, and Delta persistence completed in one live run | Verified |
| Performance | Representative filtered dashboard aggregation uses Photon, predicate/dictionary pushdown, adaptive aggregation, and complete table statistics | Verified |
| Documentation | Architecture, deployment, privacy, acceptance, and walkthrough agree with the reorganized repo | Verified |
| Open-source configuration | Demo and customer example configurations pass local validation | Verified |
| Customer adapter | Four source mappings render canonical Bronze tables with runtime fail-fast contract checks | Verified |
| Deployable build | Catalog/schema references render into an immutable generated repository; customer mode replaces synthetic ingestion | Verified |
| Independent BYOD rehearsal | External-shaped fixture ran through generated adapter, medallion, ML, forecast, serving, and fail-fast acceptance in isolated namespaces | Verified |
| Declarative convergence | Direct-engine plan reports six managed resources unchanged after deployment, including native Genie | Verified |

## Verified live evidence

- Core and expanded ML, serving, forecast, and fail-fast acceptance workflows succeeded.
- Genie evaluation completed with 12 passed and 0 failed benchmarks.
- The three-task action-intelligence workflow completed and persisted its action plan.
- Dashboard query-plan review was fully Photon-supported with pushed service-program
  and new-hire filters.
- The independent customer-mode rehearsal produced 150,034 fact rows, 288 learning-
  curve candidates, 72 winners, and 144 future forecast rows without demo ingestion.

Workspace, run, statement, and conversation identifiers are deliberately omitted
from the public repository. Maintainers retain private execution evidence for release
verification.

## Completion rule

All release-contract rows above are verified. Workspace-specific schedules remain
paused by design until a production owner explicitly enables them.
