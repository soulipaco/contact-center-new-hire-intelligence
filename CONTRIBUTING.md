# Contributing

Thank you for helping make Contact Center New-Hire Intelligence easier to adopt, verify, and extend.

## Good places to contribute

- Source adapters and canonical-contract compatibility
- KPI semantics, reliability, learning-curve, or process-control tests
- Genie metadata, benchmark questions, and semantic safeguards
- Dashboard accessibility and evidence-backed visual improvements
- Deployment portability, documentation, and fictional examples

Open an issue before significant metric, contract, or architecture changes. Small documentation corrections can go directly to a focused pull request.

## Development workflow

1. Fork the repository and create a focused branch.
2. Use only fictional or fully redacted test data.
3. Update tests and documentation with every behavioral change.
4. Run the local quality gates below.
5. Complete the pull-request template, including data/metric contract impact.

Never include customer data, direct identifiers, workspace credentials, local environment files, or generated `build/` output.

## Local quality gates

```powershell
python -m pip install -r requirements-dev.txt
python scripts/project/cli.py validate
python scripts/project/cli.py validate --config config/project.customer.example.yml
python scripts/project/cli.py validate --config examples/fictional_customer/config.yml
python scripts/genie/materialize.py
python scripts/genie/build_space.py
python dashboard/build_dashboard.py
python scripts/quality/validate_repository.py
python scripts/quality/privacy_scan.py
python -m compileall -q lakehouse scripts dashboard action_intelligence
python -m pytest -q
```

If the change affects generated dashboard, Genie, or playbook artifacts, regenerate them and include the resulting source-controlled diff.

## Metric-contract changes

Pull requests that change KPI semantics must state:

- Row grain and affected time window
- Numerator and denominator behavior
- Higher-is-better or lower-is-better direction
- Static and training-target behavior
- Reliability, model, dashboard, and Genie impact
- Backward-compatibility or migration implications

## Pull-request scope

Keep pull requests reviewable. Separate formatting-only work from behavioral changes where practical, and explain any generated-file diff. All submissions must follow the [Code of Conduct](CODE_OF_CONDUCT.md) and [privacy boundary](docs/privacy.md).
