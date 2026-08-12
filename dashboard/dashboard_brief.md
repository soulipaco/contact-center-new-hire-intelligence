# AI/BI dashboard brief

## Purpose

**Contact Center New-Hire Ramp Intelligence** is a nine-page decision product for
understanding readiness, learning speed, production exposure, abnormal variation,
and the operational actions that should follow. Every label and observation is
fictional synthetic data.

## Shared interaction contract

- Service program, cohort, KPI, channel, and language filters are repeated only on
  pages whose datasets contain the corresponding fields.
- Date, tenure, and forecast filters remain page-specific because their grains differ.
- `target_index` makes unlike KPIs comparable: higher-is-better scores use
  `score / target * 100`; lower-is-better scores use `target / score * 100`.
  Therefore 100 is the static target for every KPI.

## Page and visual map

| Page | Decision question | Primary evidence |
|---|---|---|
| Executive Summary | Are new hires ready, and where is the largest gap? | weighted score, attainment, model confidence, tenure trend, program comparison |
| Insight & Action Center | What did the action-intelligence workflow recommend? | latest grounded insight/action plan, parser warning, retrieval provenance |
| Learning & Volume | How do skill and production exposure develop together? | observed-versus-selected-fit 90-day curve, weekly volume, cumulative volume, days to target |
| Drivers & Regression | How are KPI attainment, tenure, and handled volume related? | tenure regression, volume regression, KPI-volume scatter, slopes and correlations |
| Process Control | Which KPI gaps exceed normal tenured variation? | direction-aware 3-sigma chart, first-pass yield, DPMO, special-cause detail |
| Outliers | Which agent-weeks are unusual by robust or parametric rules? | z-score/IQR flags, volume-versus-z scatter, KPI defect count, diagnostic table |
| Cohort Comparison | Which cohorts and programs differ materially? | comparable target-index and readiness views |
| Forecast | What is the six-month planning range? | actual/forecast series with lower and upper 80 percent bounds |
| Agent Detail | Which pseudonymous records explain the aggregate? | daily score, target, volume, cumulative volume, and tenure-band distribution |

## Statistical interpretation

- Regression is descriptive association, not causal evidence. Slopes and Pearson
  correlations are shown with sample sizes and should be interpreted with the plots.
- Process-control z-scores compare new-hire results with the rolling tenured baseline
  and reverse the sign for lower-is-better KPIs, so negative values always mean worse.
- A portfolio “defect” is a direction-aware static-target miss. First-pass yield is
  non-defects divided by opportunities; DPMO is target misses per million observations.
  These are operational analytics definitions, not a claim of Six Sigma certification
  or process capability (`Cpk`).
- Outlier fences are calculated at cohort, KPI, and tenure-week peer grain. An adverse
  outlier is direction-aware z-score below -3 or an IQR breach on the unfavorable side.

The generated `contact_center_new_hire_ramp.lvdash.json` is the deployable source of
truth; Databricks is the runtime and presentation surface.
