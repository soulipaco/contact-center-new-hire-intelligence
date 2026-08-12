# Contact Center New-Hire Readiness Action Playbook

Generated draft playbook for retrieval-augmented action planning.

- Source room: `Contact Center New-Hire Ramp Intelligence`
- Generated from: `contact-center-new-hire-intelligence`
- Purpose: A Git-reviewed operating layer that converts governed cohort diagnostics into evidence-aware actions for fictional contact-center programs.
- Important: This is a generated draft and should be SME-reviewed before production use.

## 1) Room Source Reference and Interpretation Rules

### New-Hire Readiness

- Question category: `new_hire_readiness`
- Metric view: `workspace.contact_center_gold.mv_cohort_scorecard`
- Underlying source: `workspace.contact_center_gold.mv_cohort_scorecard`
- Grain: date column: `performance_date`
- Core measures: `agent_count`, `weighted_score`, `static_target_attainment_rate`, `training_target_attainment_rate`, `best_model_type`, `best_model_r_squared`, `days_to_target`, `learning_curve_interpretation`
- Core dimensions: `service_program`, `cohort_id`, `cohort_name`, `kpi`, `normal`
- Likely filters: `service_program`, `cohort_id`, `cohort_name`, `kpi`
- Metric-view specific logic:
- Preserve weighted KPI math
- Respect KPI direction
- Gate weak learning curves
- Carry reliability context
- Treat forecasts as scenarios
- Good retrieval/use-case anchors:
- Daily or weekly ramp, targets, agents, or volume reliability
- Model type, fit confidence, interpretation, or days to target
- Cross-cohort readiness comparison
- Tenured statistical benchmark or sigma exception
- Future planning or uncertainty interval

## 2) Domain Scenario Playbooks

### New-Hire Readiness

**Domain:** New-Hire Readiness

**Symptoms and analytical cues**
- Look first at `agent_count`, `weighted_score`, `static_target_attainment_rate`, `training_target_attainment_rate`, `best_model_type`.
- Cut by `service_program`, `cohort_id`, `cohort_name`, `kpi`.

## 3) Recommendation Templates

These vector-friendly action cards are intended to be retrieved directly by the action-plan pipeline.

### Action Card: New-Hire Readiness Fast Containment

- Category: `new_hire_readiness`

## 4) Putting It Together: Example Recommended Plans
