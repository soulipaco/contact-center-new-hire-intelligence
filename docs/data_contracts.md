# Canonical data contracts

Customer source systems differ; the analytics core does not. The adapter boundary
normalizes four source tables into stable Bronze contracts.

| Contract | Required grain | Purpose |
|---|---|---|
| Observations | date × agent × KPI | weighted KPI score and handled volume |
| Agents | agent × assignment-effective date | cohort, program, production start, and SCD2 attributes |
| Targets | program × cohort × KPI × version | direction-aware, effective-dated performance targets |
| Training classes | cohort | class identity and start date |

Machine-readable definitions are in [`contracts/`](../contracts/). Important rules:

- `numerator / denominator` must equal the KPI score. Do not provide a pre-averaged
  score with an unrelated denominator.
- Percentage values use a zero-to-one scale.
- `direction` accepts `higher_is_better`, `lower_is_better`, `1`, or `-1`.
- Agent and cohort identifiers must currently be integer-compatible.
- Agent labels must be pseudonymous. If `agent_label` is omitted, the adapter creates
  a deterministic SHA-256-derived label.
- Assignment and target effective-date intervals must not overlap.
- Customer mode does not ingest names, email addresses, phone numbers, transcripts,
  comments, or other free text.

The adapter writes only the canonical fields plus load metadata. Source tables stay
owned by the customer and are referenced through Unity Catalog.

