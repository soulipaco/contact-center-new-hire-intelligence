# Dashboard visual audit

Audit date: 13 August 2026 (Europe/Athens)

## Scope and goal

The audit covered the published customer-mode AI/BI dashboard as a portfolio and
open-source product surface. The goal was to verify that a first-time reviewer can
understand readiness, inspect learning and volume, evaluate statistical drivers,
and distinguish optional Action Intelligence state from a failed dashboard.

## Evidence-backed walkthrough

1. **Executive Summary — healthy.** Four high-signal KPIs precede tenure and
   service-program breakdowns. Global program, cohort, KPI, and date filters are
   visible before the analysis. Evidence: `01-executive-summary.png`.
2. **Learning & Volume — healthy.** The observed and selected learning curve is
   explicit, includes the target index, and sits beside weekly volume progression.
   Model confidence and days-to-target remain visible. Evidence:
   `02-learning-and-volume.png`.
3. **Drivers & Regression — healthy after correction.** The live audit exposed
   blank correlation cards even though the governed view contained non-null values.
   Precomputed absolute correlations now render as 0.95 for tenure and 0.24 for
   volume beside fitted visuals. Evidence: `04-drivers-and-regression.png`.
4. **Process Control — healthy after copy correction.** Direction-aware control
   limits, first-pass yield, DPMO, and defects by KPI are visible together. The DPMO
   title was shortened to prevent card-value truncation. Evidence:
   `03-process-control.png`.
5. **Insight & Action Center — truthful optional state.** Customer mode deliberately
   disables Action Intelligence. The page now publishes an explicit “Optional
   module not enabled for this deployment” row rather than an ambiguous blank feed.

## Findings resolved during the audit

- Removed the duplicated development prefix from dashboard and Genie resource names.
- Replaced unsupported nested correlation expressions in counters with governed
  precomputed absolute-correlation columns.
- Added a dashboard-safe Action Intelligence status view without fabricating data.
- Shortened the DPMO card label to keep the value legible at the live viewport.

## Accessibility and evidence limits

Visible headings, filters, tabs, tables, and controls expose semantic roles in the
captured DOM. Screenshots alone cannot establish keyboard traversal order, focus
visibility across every widget, screen-reader announcements for query refreshes,
color contrast ratios, or zoom/reflow compliance. Those require a dedicated manual
and assistive-technology test before claiming WCAG conformance.
