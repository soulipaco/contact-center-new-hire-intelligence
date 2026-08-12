# Validation results

Validation date: 12 August 2026 (Europe/Athens)

## Local source gates

| Gate | Result |
|---|---|
| Demo configuration | Valid |
| Customer example configuration | Valid; canonical source mappings complete |
| Customer deployable build | Pass - namespace rendered and synthetic ingestion replaced by generated adapter |
| Genie materialization | 6 examples, 5 filters, 5 measures |
| Genie serialized artifact | 5 tables, 6 examples, 12 benchmarks |
| Repository structure and IDs | 5 tables, 33 globally unique IDs |
| Privacy scan | Pass - no forbidden legacy identifiers in public assets |
| Dashboard generation | 9 pages, 74 widgets, 16 datasets |
| Python compilation | Pass |
| Databricks bundle validation | Pass |
| Operating playbook generation | 1 domain, 9 retrieval chunks, 1 PDF |
| Operating playbook visual QA | Pass - 8 A4 pages, no clipping/overlap, stable footer and page numbers |
| Artifact contract tests | 5 passed |

## Independent customer-mode clean room

The public fixture uses different source table and column names, a separate seed,
three service programs, nine cohorts, and isolated Bronze/Silver/Gold/model schemas.
It does not call the demo generator.

| Gate | Result |
|---|---|
| External-shaped source fixture | 150,034 KPI observations; 126 assignments; 144 target rows; 9 class rows |
| Generated customer adapter and medallion build | Success |
| Learning-curve portfolio | 288 candidates; exactly 72 winners |
| Forecast horizon | 144 future rows |
| Advanced serving surfaces | 19,440 learning-series rows; 11,232 weekly outlier rows |
| Fail-fast customer acceptance | Success; zero violations |
| Direct-engine bundle deployment | Success; dashboard, native Genie, and four jobs managed as code |
| Post-deploy convergence | 0 add, 0 change, 0 delete; 6 resources unchanged |
| Customer-mode Genie evaluation | 12 passed, 0 failed; generic customer-language spot check 2 passed, 0 failed |

## Live Databricks gates

| Gate | Result |
|---|---|
| Learning-curve training | Success |
| Serving-view refresh | Success |
| Fail-fast data/model acceptance | Success |
| Native Genie deployment | Success with valid SQL warehouse |
| Genie benchmark suite | 12 passed, 0 failed |
| AI/BI dashboard deployment | Success |
| Dashboard rendered interactions | Pass - 9 pages render; observed/fitted learning, volume, regression, process-control, outlier, forecast, and drill-through visuals render |
| Dashboard query health | Pass - 97 recent dashboard queries inspected, 0 failed |
| Action insight rendering | Pass - persisted grounded action text renders when the separately parsed research summary is blank |
| Expanded serving and acceptance | Success - serving and fail-fast checks passed |
| Action-intelligence pipeline | Success - 3/3 tasks passed and action-plan write completed |
| Representative dashboard query plan | Success - fully Photon-supported, pushed filters, adaptive aggregation, full table statistics |

Workspace-specific raw benchmark output is intentionally ignored because it
contains conversation identifiers and generated SQL. This document records only
publication-safe aggregate evidence.
